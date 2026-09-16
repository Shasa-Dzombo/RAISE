"""First-note templates by capital type (agents/SPECIALISTS.md #2 OUTREACH,
agents/IDENTITY.md Africa-specific operating knowledge).

Never one template across all four types:
  - Africa-focused commercial VC: traction and velocity.
  - Global fund w/ African portfolio: contextualize the market, then us.
  - DFI / impact investor: evidence and outcome measurement, no velocity language.
  - Local/regional angel syndicate: assumes a warm intro, reads differently.

Every function takes (fund: dict from investor_file, facts: dict from
render_lib.load_facts) and returns (subject, body). Numbers come from facts
only -- never hardcoded -- same discipline as question_bank templates.
"""


def _v(facts, key):
    fact = facts.get(key)
    if fact is None or fact["value"] is None:
        raise ValueError("canon_facts.{} is missing -- cannot draft a note that cites it".format(key))
    return fact["value"]


def africa_focused_vc(fund, facts):
    subject = "Mazao Analytics -- seed round, live in {}".format(_v(facts, "markets_operating_in"))
    body = (
        "Hi {partner},\n\n"
        "Mazao Analytics is at {arr} USD ARR, live in {markets}, growing "
        "{growth} month over month. {why_them}\n\n"
        "Raising a {stage} round -- deck attached. Open to a call if this is "
        "in your wheelhouse.\n\n"
        "Regards,\nGift"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        arr=_v(facts, "arr_usd"), markets=_v(facts, "markets_operating_in"),
        growth=_v(facts, "mom_growth_rate_pct"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
    )
    return subject, body


def global_vc_africa_portfolio(fund, facts):
    subject = "Mazao Analytics -- agritech for smallholder farmers, East Africa"
    body = (
        "Hi {partner},\n\n"
        "Quick context: East Africa took a significant share of agritech deal "
        "value this year, and smallholder-farmer-facing companies are still "
        "underserved relative to processing/logistics. Mazao Analytics gives "
        "smallholder farmers real-time crop pricing and buyer matching over "
        "SMS -- current ARR {arr} USD, live in {markets}. {why_them}\n\n"
        "Raising a {stage} round -- deck attached. Worth a conversation?\n\n"
        "Regards,\nGift"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        arr=_v(facts, "arr_usd"), markets=_v(facts, "markets_operating_in"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
    )
    return subject, body


def dfi_impact(fund, facts):
    subject = "Mazao Analytics -- smallholder farmer income outcomes, East Africa"
    body = (
        "Hi {partner},\n\n"
        "Mazao Analytics works with smallholder farmers across {markets}, "
        "giving them real-time crop pricing and direct buyer access over SMS "
        "-- current ARR {arr} USD. {why_them}\n\n"
        "Raising a {stage} round to extend into {targeting}. Deck attached, "
        "happy to share farmer-level outcome data on a call.\n\n"
        "Regards,\nGift"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        markets=_v(facts, "markets_operating_in"), arr=_v(facts, "arr_usd"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"), targeting=_v(facts, "markets_targeting"),
    )
    return subject, body


def local_angel_syndicate(fund, facts):
    subject = "Mazao Analytics -- intro via {}".format(fund.get("warm_path") or "[warm intro needed]")
    body = (
        "Hi {partner},\n\n"
        "{warm_path_line}Mazao Analytics -- agritech for smallholder farmers, "
        "{arr} USD ARR, live in {markets}. {why_them}\n\n"
        "Raising a {stage} round -- deck attached. Would value your take.\n\n"
        "Regards,\nGift"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        warm_path_line=("{} suggested I reach out. ".format(fund["warm_path"]) if fund.get("warm_path") else ""),
        arr=_v(facts, "arr_usd"), markets=_v(facts, "markets_operating_in"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
    )
    return subject, body


TEMPLATES = {
    "africa_focused_vc": africa_focused_vc,
    "global_vc_africa_portfolio": global_vc_africa_portfolio,
    "dfi_impact": dfi_impact,
    "local_angel_syndicate": local_angel_syndicate,
}


def draft_first_note(fund, facts):
    template_fn = TEMPLATES.get(fund["capital_type"])
    if template_fn is None:
        raise ValueError("no template for capital_type={}".format(fund["capital_type"]))
    return template_fn(fund, facts)
