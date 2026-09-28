"""Standalone Scout orchestrator, driven by an open-weights model 
 -- the same OPEN_WEIGHT_* gateway
llm_orchestrator.py uses for Inbox, applied to Scout's fund-research job.

Real difference from Inbox's orchestrator, worth being upfront about:
Inbox's model only sequences calls to deterministic tools and never
produces free text of its own (classify_thread does all the actual
classification/drafting). Scout's whole job is synthesizing free text
from open-ended web research -- there is no way around the model
actually writing the note fields (thesis, why_them, etc). The safety
story still holds: nothing this orchestrator produces can act on
anyone. It only ever calls propose_investor, which inserts a candidate
investor_file row with approved = FALSE, exactly like interactive Scout
work -- Outreach still cannot touch a firm until the founder approves it
by hand. Every proposed row's notes are also prefixed
"[AI-drafted -- verify sources before approving]" so it gets more
scrutiny than a Claude-researched entry, not less.

Search: Tavily (api.tavily.com), a search API built for LLM tool-calling
-- plain synchronous HTTP via `requests`, no SDK. Needs TAVILY_API_KEY.

Usage:
    python scripts/scout_orchestrator.py --capital-type africa_focused_vc
"""

import argparse
import json
import os
import pathlib
import re
import sys

import psycopg
import requests
from dotenv import load_dotenv
from openai import OpenAI

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import add_investor  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

CAPITAL_TYPES = ["africa_focused_vc", "global_vc_africa_portfolio", "dfi_impact", "local_angel_syndicate"]

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information about VC/DFI/angel funds. Returns titles, URLs, snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and extract the full text of one URL -- use to actually read a fund's portfolio page or a press release, not just a search snippet.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_existing_firm",
            "description": "Check whether a firm is already in investor_file. Call this before propose_investor.",
            "parameters": {
                "type": "object",
                "properties": {"firm_name": {"type": "string"}},
                "required": ["firm_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_investor",
            "description": (
                "Insert one candidate fund into investor_file (approved=FALSE -- founder must still "
                "approve before Outreach can act). Refused if the firm is already approved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "firm_name": {"type": "string"},
                    "partner_name": {"type": "string"},
                    "partner_email": {"type": "string"},
                    "thesis": {"type": "string"},
                    "check_size_min": {"type": "number"},
                    "check_size_max": {"type": "number"},
                    "check_size_currency": {"type": "string"},
                    "domicile": {"type": "string"},
                    "deployment_markets": {"type": "array", "items": {"type": "string"}},
                    "domicile_blocker": {"type": "boolean"},
                    "warm_path": {"type": "string"},
                    "working_language": {"type": "string"},
                    "heat": {"type": "string", "enum": ["cold", "warm", "hot"]},
                    "source": {"type": "string", "description": "URL or named publication the claim came from"},
                    "source_date": {"type": "string", "description": "YYYY-MM-DD, the real date on the source -- never invented"},
                    "notes": {"type": "string"},
                    "stage_fit": {"type": "string"},
                    "portfolio_examples": {"type": "string"},
                    "conflicts": {"type": "string"},
                    "why_them": {"type": "string"},
                },
                "required": ["firm_name", "thesis", "source", "source_date", "why_them"],
            },
        },
    },
]

SYSTEM_PROMPT_TEMPLATE = """You are the RAISE Scout agent, researching {capital_type} funds only this run.

Read this Scout job description carefully -- it is your entire mandate:
{scout_section}

Africa-specific operating knowledge that shapes how you research and score:
{africa_knowledge}

This company's specific targeting instructions (geography, check size, exclusions, do-not-contact):
{targeting}

Your tools: web_search, web_fetch, check_existing_firm, propose_investor.

Procedure for each candidate fund:
  1. web_search to find candidates matching {capital_type} and the targeting
     instructions above.
  2. check_existing_firm(firm_name) BEFORE proposing anything -- if it already
     exists and is approved, skip it and move to a different firm.
  3. web_fetch one or more search results to actually read the fund's thesis,
     portfolio, and stated geography -- never propose from a snippet alone.
  4. propose_investor with every field you can source. Every claim needs a
     real source (a URL or named publication) and source_date -- the exact
     date on the page/article you actually read, never estimated or invented.

Hard rules, no exceptions:
- Stop after proposing {max_candidates} candidates (propose_investor refuses
  once the cap is hit) and summarize what you found.
- Never invent a source or a date.
- Distinguish stated geography from actual deployment -- many funds claim
  pan-African coverage and have only invested in two markets. Say so in
  why_them/notes if there's a gap.
- Flag domicile blockers explicitly (domicile_blocker=true) rather than
  silently proposing a fund that cannot invest in our structure.
- Never propose a firm on the do-not-contact list above.
- why_them must be recipient-appropriate (two sentences, specific, no
  internal reasoning about our own process) -- notes is where internal-only
  commentary belongs, never why_them.
- You never send anything, draft anything, or contact anyone -- you only
  ever call propose_investor, which inserts an unapproved candidate row.
  Nothing acts on your output until the founder approves it by hand.
"""


def _tavily_headers():
    return {"Authorization": "Bearer {}".format(os.environ["TAVILY_API_KEY"]), "Content-Type": "application/json"}


def web_search(query, max_results=8):
    resp = requests.post(
        TAVILY_SEARCH_URL, headers=_tavily_headers(),
        json={"query": query, "max_results": max_results, "search_depth": "basic"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "results": [
            {"title": r.get("title"), "url": r.get("url"), "content": r.get("content"),
             "published_date": r.get("published_date")}
            for r in data.get("results", [])
        ]
    }


def web_fetch(url):
    resp = requests.post(TAVILY_EXTRACT_URL, headers=_tavily_headers(), json={"urls": [url]}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        return {"error": "could not extract content", "failed": data.get("failed_results", [])}
    raw = results[0].get("raw_content") or ""
    return {"url": results[0].get("url"), "raw_content": raw[:8000]}


def _extract_section(text, header):
    """Extract one '## Header' section's body from a markdown file's raw
    text -- read at runtime rather than paraphrased, so the orchestrator's
    prompt can't silently drift from the actual source of truth."""
    pattern = re.compile(r"^## " + re.escape(header) + r"\s*$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        raise ValueError("section '## {}' not found".format(header))
    return m.group(1).strip()


def build_system_prompt(capital_type, max_candidates):
    identity_text = (ROOT / "identity" / "IDENTITY.md").read_text(encoding="utf-8")
    user_text = (ROOT / "identity" / "USER.md").read_text(encoding="utf-8")
    specialists_text = (ROOT / "agents" / "SPECIALISTS.md").read_text(encoding="utf-8")

    scout_section = _extract_section(specialists_text, "1. SCOUT")
    africa_knowledge = _extract_section(identity_text, "Africa-specific operating knowledge")
    targeting = _extract_section(user_text, "Targeting instructions for Scout")

    return SYSTEM_PROMPT_TEMPLATE.format(
        capital_type=capital_type, max_candidates=max_candidates,
        scout_section=scout_section, africa_knowledge=africa_knowledge, targeting=targeting,
    )


def make_tool_impls(cur, capital_type, proposals_state):
    def check_existing_firm(firm_name):
        cur.execute(
            "SELECT id, approved, process_stage FROM investor_file WHERE lower(firm_name) = lower(%s)",
            (firm_name,),
        )
        row = cur.fetchone()
        if row is None:
            return {"exists": False}
        return {"exists": True, "id": row[0], "approved": row[1], "process_stage": row[2]}

    def propose_investor(**fields):
        firm_name = fields.get("firm_name")
        if not firm_name:
            return {"error": "firm_name is required"}

        cur.execute("SELECT approved FROM investor_file WHERE lower(firm_name) = lower(%s)", (firm_name,))
        row = cur.fetchone()
        if row is not None and row[0]:
            return {"error": "{} is already approved -- refusing to overwrite. Move on to a different firm.".format(firm_name)}

        if proposals_state["count"] >= proposals_state["max"]:
            return {"error": "candidate cap ({}) reached -- stop and summarize now.".format(proposals_state["max"])}

        fields = dict(fields)
        fields["capital_type"] = capital_type
        fields["notes"] = "[AI-drafted -- verify sources before approving] " + (fields.get("notes") or "")

        try:
            row_id = add_investor.add_investor(cur.connection, **fields)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

        proposals_state["count"] += 1
        return {"proposed": True, "investor_file_id": row_id, "firm_name": firm_name}

    return {
        "web_search": web_search,
        "web_fetch": web_fetch,
        "check_existing_firm": check_existing_firm,
        "propose_investor": propose_investor,
    }


def run(capital_type, max_candidates=5, max_turns=30, verbose=True):
    """Run one Scout research pass. Returns a result dict so callers other
    than the CLI (e.g. the dashboard's Scout tab) can render structured
    output instead of scraping stdout:
    {"proposed": [...], "final_message": str|None, "hit_max_turns": bool}
    Raises RuntimeError if required env vars are missing -- callers decide
    how to surface that (CLI exits 1, dashboard shows it in the UI).
    """
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    open_weight_key = os.environ.get("OPEN_WEIGHT_API_KEY")
    open_weight_url = os.environ.get("OPEN_WEIGHT_BASE_URL")
    model = os.environ.get("OPEN_WEIGHT_MODEL", "gpt-oss:120b")
    tavily_key = os.environ.get("TAVILY_API_KEY")

    missing = [n for n, v in [
        ("DATABASE_URL", database_url), ("OPEN_WEIGHT_API_KEY", open_weight_key),
        ("OPEN_WEIGHT_BASE_URL", open_weight_url), ("TAVILY_API_KEY", tavily_key),
    ] if not v]
    if missing:
        raise RuntimeError("Missing env vars: " + ", ".join(missing))

    client = OpenAI(api_key=open_weight_key, base_url=open_weight_url)
    system_prompt = build_system_prompt(capital_type, max_candidates)

    final_message = None
    hit_max_turns = False

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            proposals_state = {"count": 0, "max": max_candidates, "items": []}
            tool_impls = make_tool_impls(cur, capital_type, proposals_state)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Find up to {} new {} funds now.".format(max_candidates, capital_type)},
            ]

            for turn in range(max_turns):
                response = client.chat.completions.create(
                    model=model, messages=messages, tools=TOOLS, tool_choice="auto",
                )
                choice = response.choices[0]
                messages.append(choice.message.model_dump(exclude_none=True))

                if not choice.message.tool_calls:
                    final_message = choice.message.content or ""
                    if verbose:
                        print("\n[model] " + final_message)
                    break

                for tool_call in choice.message.tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if verbose:
                        print("[tool call] {}({})".format(name, {k: v for k, v in args.items() if k != "raw_content"}))

                    impl = tool_impls.get(name)
                    if impl is None:
                        result = {"error": "no such tool: {}".format(name)}
                    else:
                        try:
                            result = impl(**args)
                        except Exception as exc:  # noqa: BLE001
                            result = {"error": str(exc)}

                    if result.get("proposed"):
                        proposals_state["items"].append(result)

                    if verbose:
                        print("[tool result] {}".format(json.dumps(result, default=str)[:300]))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    })
            else:
                hit_max_turns = True
                if verbose:
                    print("Hit max_turns ({}) without the model finishing on its own.".format(max_turns), file=sys.stderr)

            if verbose:
                print("\nProposed {} candidate(s) this run.".format(proposals_state["count"]))

            return {
                "proposed": proposals_state["items"],
                "final_message": final_message,
                "hit_max_turns": hit_max_turns,
            }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital-type", required=True, choices=CAPITAL_TYPES)
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--max-turns", type=int, default=30)
    args = parser.parse_args()
    try:
        run(args.capital_type, args.max_candidates, args.max_turns)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
