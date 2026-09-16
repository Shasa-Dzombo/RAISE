"""Personal-use Gradio dashboard -- a read-only window onto everything RAISE
has actually built and exercised this build, so the state of Scout/Outreach/
Inbox/Data Room/canon_facts can be seen without hand-querying Postgres or
digging through Gmail/Drive.

Hard rule: this file never writes to Postgres, Gmail, or Drive. Every query
is a SELECT; every "live action" tab calls a pure function (render_lib.
check_question, classify_thread.classify) directly, never classify_thread.
main() or gmail_client/drive_client. Same safety-by-construction pattern as
the rest of RAISE -- a demo tool must not be able to leave side effects.

Usage:
    python scripts/dashboard.py
"""

import os
import pathlib
import sys

import gradio as gr
import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_lib import check_question, load_facts  # noqa: E402
from classify_thread import classify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")
FOUNDER_EMAIL = os.environ.get("FOUNDER_EMAIL", "founder@example.com")

if not DATABASE_URL:
    print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
    sys.exit(1)


def _connect():
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _query(sql, params=None):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        headers = [d.name for d in cur.description]
    return [[str(v) if v is not None else "" for v in row] for row in rows], headers


TABLES = [
    ("investor_file", "🏦", "SELECT * FROM investor_file ORDER BY id"),
    ("canon_facts", "🔢", "SELECT * FROM canon_facts ORDER BY id"),
    ("question_bank", "❓", "SELECT * FROM question_bank ORDER BY id"),
    ("drafts", "📝", "SELECT * FROM drafts ORDER BY id DESC"),
    ("outreach_touches", "📤", "SELECT * FROM outreach_touches ORDER BY id DESC"),
    ("data_room_links", "🔗", "SELECT * FROM data_room_links ORDER BY id DESC"),
    ("data_room_files", "📄", "SELECT * FROM data_room_files ORDER BY id DESC"),
    ("data_room_views", "👁️", "SELECT * FROM data_room_views ORDER BY id DESC"),
    ("activity_log", "📜", "SELECT * FROM activity_log ORDER BY occurred_at DESC LIMIT 100"),
]

SPECIALISTS = [
    {"num": 1, "name": "Scout", "icon": "🔭", "status": "verified",
     "detail": "5 African/Africa-focused funds researched and inserted via add_investor.py; all 5 approved by founder."},
    {"num": 2, "name": "Outreach", "icon": "📤", "status": "verified",
     "detail": "4 capital-type templates; a real first-note draft was created and sent (Accion Ventures test), "
               "outreach_touches marked sent, investor_file.process_stage &rarr; contacted."},
    {"num": 3, "name": "Inbox", "icon": "📥", "status": "verified",
     "detail": "classify_thread.py handling ladder run against a real reply; correctly escalated with no question_bank match."},
    {"num": 4, "name": "Diligence", "icon": "📋", "status": "partial",
     "detail": "question_bank (41 questions) + drift_test.py exist and are exercised by Inbox; no standalone "
               "escalation-review/approval script yet."},
    {"num": 5, "name": "Data Room", "icon": "🗂️", "status": "gap",
     "detail": "Drive folders, PDF watermarking, and restricted per-firm sharing verified live. View-tracking "
               "(data_room.py report) does not work for personal Gmail viewers &mdash; documented in "
               "DATA_ROOM_PROCEDURE.md."},
    {"num": 6, "name": "Scheduler", "icon": "📅", "status": "none", "detail": "No script exists yet."},
    {"num": 7, "name": "Pipeline", "icon": "📊", "status": "none",
     "detail": "investor_file.process_stage tracks stage, but no board/weekly-report script exists yet."},
    {"num": 8, "name": "Terms", "icon": "📄", "status": "none", "detail": "No script exists yet."},
]

STATUS_BADGE = {
    "verified": ("Built &amp; verified", "badge-green"),
    "partial": ("Partially built", "badge-amber"),
    "gap": ("Verified &mdash; known gap", "badge-amber"),
    "none": ("Not built", "badge-gray"),
}

CLASSIFICATION_ICON = {
    "known_question_draft": "✅",
    "thread_locked_skip": "🔒",
    "do_not_contact_skip": "⛔",
    "legal_price_personal_escalate": "⚠️",
    "meeting_request_flag": "📅",
    "data_room_request_flag": "🗂️",
    "unknown_question_escalate": "🚩",
}

CSS = """
.app-header h1 {
    font-size: 1.9em;
    margin: 0 0 4px 0;
    background: linear-gradient(90deg, #10b981, #059669);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    font-weight: 700;
    display: inline-block;
}
.app-header p {
    margin: 0 0 6px 0;
    color: var(--body-text-color-subdued);
    font-size: 0.95em;
}
.specialist-card {
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 10px;
    background: var(--background-fill-secondary);
}
.specialist-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 6px;
}
.specialist-icon { font-size: 1.4em; line-height: 1; }
.specialist-title { font-weight: 600; font-size: 1.02em; flex-grow: 1; }
.specialist-detail {
    color: var(--body-text-color-subdued);
    font-size: 0.9em;
    line-height: 1.5;
    margin-left: 2.4em;
}
.badge {
    padding: 3px 11px;
    border-radius: 999px;
    font-size: 0.72em;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    white-space: nowrap;
}
.badge-green { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.4); }
.badge-amber { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.4); }
.badge-gray  { background: rgba(148,163,184,0.15); color: #94a3b8; border: 1px solid rgba(148,163,184,0.4); }
.chain-row {
    display: flex;
    align-items: stretch;
    gap: 6px;
    flex-wrap: wrap;
}
.chain-card {
    flex: 1 1 220px;
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 14px 16px;
    background: var(--background-fill-secondary);
}
.chain-card h4 {
    margin: 0 0 8px 0;
    font-size: 0.95em;
}
.chain-card p {
    margin: 3px 0;
    font-size: 0.85em;
    color: var(--body-text-color-subdued);
    line-height: 1.4;
}
.chain-arrow {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4em;
    color: var(--body-text-color-subdued);
    padding: 0 2px;
    min-width: 24px;
}
.chain-empty { color: var(--body-text-color-subdued); font-style: italic; font-size: 0.9em; }
.table-caption { color: var(--body-text-color-subdued); font-size: 0.85em; margin: 0 0 6px 0; }
.demo-output {
    border: 1px solid var(--border-color-primary);
    border-radius: 10px;
    padding: 12px 16px;
    background: var(--background-fill-secondary);
    min-height: 24px;
}
"""

THEME = gr.themes.Soft(primary_hue="emerald", secondary_hue="teal", neutral_hue="slate")


def render_specialist_cards():
    cards = []
    for s in SPECIALISTS:
        label, cls = STATUS_BADGE[s["status"]]
        cards.append(
            '<div class="specialist-card">'
            '<div class="specialist-row">'
            '<span class="specialist-icon">{icon}</span>'
            '<span class="specialist-title">{num}. {name}</span>'
            '<span class="badge {cls}">{label}</span>'
            '</div>'
            '<div class="specialist-detail">{detail}</div>'
            '</div>'.format(icon=s["icon"], num=s["num"], name=s["name"], cls=cls, label=label, detail=s["detail"])
        )
    return "".join(cards)


def _chain_card(icon, title, lines):
    body = "".join("<p>{}</p>".format(line) for line in lines)
    return '<div class="chain-card"><h4>{} {}</h4>{}</div>'.format(icon, title, body)


def load_recent_chain():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.firm_name, o.touch_number, o.template_capital_type, o.status, o.sent_at
            FROM outreach_touches o JOIN investor_file i ON i.id = o.investor_id
            ORDER BY o.created_at DESC LIMIT 1
            """
        )
        outreach_row = cur.fetchone()

        cur.execute(
            """
            SELECT gmail_thread_id, classification, investor_id, notes, created_at
            FROM drafts ORDER BY created_at DESC LIMIT 1
            """
        )
        draft_row = cur.fetchone()

        cur.execute(
            """
            SELECT i.firm_name, l.tier, l.expiry_date, l.created_at
            FROM data_room_links l JOIN investor_file i ON i.id = l.investor_id
            ORDER BY l.created_at DESC LIMIT 1
            """
        )
        data_room_row = cur.fetchone()

    if outreach_row:
        firm, touch_number, capital_type, status, sent_at = outreach_row
        outreach_card = _chain_card("📤", "Outreach", [
            "<b>{}</b> &mdash; touch #{} ({})".format(firm, touch_number, capital_type),
            "status={}, sent_at={}".format(status, sent_at or "not yet"),
        ])
    else:
        outreach_card = _chain_card("📤", "Outreach", ['<span class="chain-empty">No touches yet.</span>'])

    if draft_row:
        thread_id, classification, investor_id, notes, created_at = draft_row
        investor_note = (
            "investor_id={}".format(investor_id) if investor_id else
            "investor_id=NULL &mdash; sender email didn't match partner_email (known self-test limitation)"
        )
        inbox_card = _chain_card("📥", "Inbox", [
            "thread <code>{}</code>".format(thread_id),
            "classified <b>{}</b>".format(classification),
            investor_note,
            notes or "",
        ])
    else:
        inbox_card = _chain_card("📥", "Inbox", ['<span class="chain-empty">No classifications yet.</span>'])

    if data_room_row:
        firm, tier, expiry_date, created_at = data_room_row
        data_room_card = _chain_card("🗂️", "Data Room", [
            "<b>{}</b> granted <b>{}</b> tier".format(firm, tier),
            "expires {}, granted {}".format(expiry_date, created_at),
        ])
    else:
        data_room_card = _chain_card("🗂️", "Data Room", ['<span class="chain-empty">No grants yet.</span>'])

    arrow = '<div class="chain-arrow">&rarr;</div>'
    return '<div class="chain-row">{}{}{}{}{}</div>'.format(outreach_card, arrow, inbox_card, arrow, data_room_card)


def render_question(question_text):
    with _connect() as conn, conn.cursor() as cur:
        facts = load_facts(cur)
        cur.execute("SELECT answer_template FROM question_bank WHERE question = %s", (question_text,))
        row = cur.fetchone()
    if row is None:
        return "No such question in question_bank."
    result = check_question(row[0], facts)
    if result["renderable"]:
        return "✅ **Rendered:**\n\n{}".format(result["rendered"])
    return "⚠️ **NOT RENDERABLE:**\n\n" + "\n".join(result["findings"] + result["hygiene_errors"])


def classify_pasted_message(body_text):
    if not body_text.strip():
        return "Paste a message body first."
    with _connect() as conn, conn.cursor() as cur:
        facts = load_facts(cur)
        cur.execute("SELECT id, question, answer_template FROM question_bank ORDER BY id")
        questions = [{"id": r[0], "question": r[1], "answer_template": r[2]} for r in cur.fetchall()]

    thread = {
        "id": "demo-thread",
        "messages": [{
            "id": "demo-message",
            "sender": "demo@example.com",
            "date": "2026-01-01T00:00:00Z",
            "plaintextBody": body_text,
        }],
    }
    decision = classify(thread, "demo-message", FOUNDER_EMAIL, None, facts, questions)

    icon = CLASSIFICATION_ICON.get(decision["classification"], "•")
    lines = ["{} **classification**: `{}`".format(icon, decision["classification"])]
    if decision.get("notes"):
        lines.append("**notes**: {}".format(decision["notes"]))
    if decision.get("draft_text"):
        lines.append("\n**draft_text**:\n\n{}".format(decision["draft_text"]))
    lines.append("\n_(demo only -- nothing written to drafts or activity_log)_")
    return "\n".join(lines)


def get_question_choices():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT question FROM question_bank ORDER BY id")
        return [r[0] for r in cur.fetchall()]


with gr.Blocks(title="RAISE Dashboard") as demo:
    with gr.Column(elem_classes=["app-header"]):
        gr.HTML(
            "<h1>RAISE</h1>"
            "<p>What's actually built, live. Read-only &mdash; nothing here sends mail, "
            "drafts a message, shares a file, or writes to Postgres.</p>"
        )

    with gr.Tab("🧭 Pipeline Overview"):
        gr.Markdown("### The 8 specialists")
        gr.HTML(render_specialist_cards())

        gr.Markdown("### Most recent activity per stage")
        chain_html = gr.HTML(load_recent_chain())
        chain_refresh = gr.Button("🔄 Refresh chain", size="sm")
        chain_refresh.click(fn=load_recent_chain, outputs=chain_html)

    with gr.Tab("🗄️ Live Data Browser"):
        for table_name, icon, sql in TABLES:
            with gr.Tab("{} {}".format(icon, table_name)):
                rows0, headers0 = _query(sql)
                gr.Markdown("_{} row(s)_".format(len(rows0)), elem_classes=["table-caption"])
                df = gr.Dataframe(headers=headers0, value=rows0, wrap=True)
                btn = gr.Button("🔄 Refresh", size="sm")

                def _make_refresh(sql=sql):
                    def _refresh():
                        rows, headers = _query(sql)
                        return gr.Dataframe(headers=headers, value=rows)
                    return _refresh

                btn.click(fn=_make_refresh(), outputs=df)

    with gr.Tab("🧪 Interactive Demo"):
        with gr.Group():
            gr.Markdown("## Render a question_bank answer live")
            gr.Markdown(
                "Pulls the current `answer_template` and renders it against live `canon_facts`, the same "
                "way `classify_thread.py` does &mdash; no drift possible, since nothing is hardcoded."
            )
            question_dd = gr.Dropdown(choices=get_question_choices(), label="Question")
            render_btn = gr.Button("Render", variant="primary")
            render_out = gr.Markdown(elem_classes=["demo-output"])
            render_btn.click(fn=render_question, inputs=question_dd, outputs=render_out)

        with gr.Group():
            gr.Markdown("## Classify a pasted message")
            gr.Markdown(
                "Runs the real Inbox handling ladder (`classify_thread.classify`) against pasted text. "
                "Read-only demo &mdash; nothing is written to `drafts` or `activity_log`."
            )
            message_in = gr.Textbox(label="Message body", lines=6, placeholder="Paste an inbound-style message here...")
            classify_btn = gr.Button("Classify", variant="primary")
            classify_out = gr.Markdown(elem_classes=["demo-output"])
            classify_btn.click(fn=classify_pasted_message, inputs=message_in, outputs=classify_out)


if __name__ == "__main__":
    demo.launch(share=False, theme=THEME, css=CSS)
