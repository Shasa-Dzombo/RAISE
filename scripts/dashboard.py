"""Founder-facing Gradio dashboard for RAISE -- a working tool, not a build
status page. Landing view is "Today": what needs a decision, what happened
since you last looked. Pipeline/Firms/Fact Sheet give the founder's actual
mental model of a raise. "Behind the scenes" keeps the old build-status +
raw-table view for when the engineering picture is what's needed.

Write surface is deliberately narrow and every mutation is the founder
explicitly initiating something they'd otherwise type as a CLI command,
never RAISE deciding to act on its own: approve/pass a fund and mark an
outreach touch as sent (scripts/founder_actions.py, reusing
scripts/outreach.py's mark_sent), and granting Data Room access
(reusing scripts/data_room.py's grant_access -- creates a Drive folder,
watermarks and uploads the deck, shares it with exactly the email the
founder typed in, and registers a tracking link, exactly as the CLI
does). No draft/send capability exists here or anywhere in this
codebase -- Gmail has no send/reply function defined, full stop. Every
other query in this file is a plain SELECT.

Usage:
    python scripts/dashboard.py
"""

import datetime
import os
import pathlib
import sys

import gradio as gr
import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_lib import check_question, load_facts  # noqa: E402
from classify_thread import classify  # noqa: E402
import outreach  # noqa: E402
import founder_actions  # noqa: E402
import data_room  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")
FOUNDER_EMAIL = os.environ.get("FOUNDER_EMAIL", "founder@example.com")
FOUNDER_DISPLAY_NAME = os.environ.get("FOUNDER_DISPLAY_NAME", "Gift")

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


CAPITAL_TYPE_LABEL = {
    "africa_focused_vc": "Africa-focused VC",
    "global_vc_africa_portfolio": "Global VC (Africa portfolio)",
    "dfi_impact": "DFI / Impact",
    "local_angel_syndicate": "Local angel / syndicate",
}

HEAT_ICON = {"hot": "🔥", "warm": "🌤️", "cold": "❄️"}

STAGE_ORDER = [
    ("target", "Target"), ("contacted", "Contacted"), ("replied", "Replied"),
    ("diligence", "Diligence"), ("term_sheet", "Term Sheet"),
    ("closed_won", "Closed Won"), ("closed_lost", "Closed Lost"),
    ("passed", "Passed"), ("do_not_contact", "Do Not Contact"),
]

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
     "detail": "investor_file.process_stage tracks stage; the Pipeline tab above now visualizes it, but there's "
               "still no weekly-review/report script."},
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
.chain-row { display: flex; align-items: stretch; gap: 6px; flex-wrap: wrap; }
.chain-card {
    flex: 1 1 220px;
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 14px 16px;
    background: var(--background-fill-secondary);
}
.chain-card h4 { margin: 0 0 8px 0; font-size: 0.95em; }
.chain-card p { margin: 3px 0; font-size: 0.85em; color: var(--body-text-color-subdued); line-height: 1.4; }
.chain-empty { color: var(--body-text-color-subdued); font-style: italic; font-size: 0.9em; }
.table-caption { color: var(--body-text-color-subdued); font-size: 0.85em; margin: 0 0 6px 0; }
.demo-output {
    border: 1px solid var(--border-color-primary);
    border-radius: 10px;
    padding: 12px 16px;
    background: var(--background-fill-secondary);
    min-height: 24px;
}
.today-sub { color: var(--body-text-color-subdued); font-size: 0.95em; margin: 0 0 14px 0; }
.today-card {
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 12px 16px;
    margin-bottom: 8px;
    background: var(--background-fill-secondary);
}
.today-card h4 { margin: 0 0 4px 0; font-size: 0.95em; }
.today-card p { margin: 3px 0; font-size: 0.85em; line-height: 1.4; }
.today-meta { color: var(--body-text-color-subdued); font-size: 0.78em !important; }
.activity-line {
    font-size: 0.88em;
    padding: 6px 2px;
    border-bottom: 1px solid var(--border-color-primary);
    margin: 0 !important;
}
.pipeline-row { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 10px; }
.pipeline-column { min-width: 190px; flex-shrink: 0; }
.pipeline-column h4 { font-size: 0.85em; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.03em; color: var(--body-text-color-subdued); }
.pipeline-card {
    border: 1px solid var(--border-color-primary);
    border-radius: 10px;
    padding: 10px 12px;
    margin-bottom: 8px;
    background: var(--background-fill-secondary);
    font-size: 0.85em;
}
.factsheet-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 8px; margin-bottom: 18px; }
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


def get_question_choices():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT question FROM question_bank ORDER BY id")
        return [r[0] for r in cur.fetchall()]


CLASSIFICATION_EXPLAIN = {
    "known_question_draft": "Matched an approved answer and drafted a reply from canon_facts.",
    "unknown_question_escalate": "No question_bank match -- RAISE won't guess, so this goes to you.",
    "legal_price_personal_escalate": "Legal, price, or personal language -- always escalated, never auto-answered.",
    "meeting_request_flag": "Meeting request -- Scheduler isn't built yet, so this is flagged for you.",
    "data_room_request_flag": "Data room request -- flagged for you to grant access.",
    "thread_locked_skip": "You already replied in this thread -- RAISE stays out.",
    "do_not_contact_skip": "This sender is on the do-not-contact list.",
}

VC_EXAMPLES = [
    ("💰 Ask about ARR", "Hi, what's your current ARR?"),
    ("⚖️ Ask about valuation", "What valuation are you raising at?"),
    ("📅 Ask for a call", "Could we set up a call this week?"),
    ("🗂️ Ask for data room access", "Can you share data room access?"),
    ("❓ Ask something unusual", "What is your favorite programming language?"),
]


def send_vc_message(vc_text, chat_history, thread_state):
    if not vc_text or not vc_text.strip():
        return chat_history or [], thread_state or {"messages": [], "counter": 0}, vc_text

    chat_history = list(chat_history or [])
    thread_state = dict(thread_state or {"messages": [], "counter": 0})
    thread_state["messages"] = list(thread_state.get("messages", []))
    thread_state["counter"] = thread_state.get("counter", 0) + 1

    msg_id = "demo-{}".format(thread_state["counter"])
    ts = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(minutes=thread_state["counter"])
    thread_state["messages"].append(
        {"id": msg_id, "sender": "vc@example.com", "date": ts.isoformat(), "plaintextBody": vc_text}
    )
    thread = {"id": "demo-conversation", "messages": thread_state["messages"]}

    with _connect() as conn, conn.cursor() as cur:
        facts = load_facts(cur)
        cur.execute("SELECT id, question, answer_template FROM question_bank ORDER BY id")
        questions = [{"id": r[0], "question": r[1], "answer_template": r[2]} for r in cur.fetchall()]

    decision = classify(thread, msg_id, FOUNDER_EMAIL, None, facts, questions)
    explain = CLASSIFICATION_EXPLAIN.get(decision["classification"], "")

    chat_history.append({"role": "user", "content": vc_text})
    if decision["classification"] == "known_question_draft":
        reply = decision["draft_text"]
        if explain:
            reply += "\n\n*{}*".format(explain)
        chat_history.append({"role": "assistant", "content": reply})
    else:
        icon = CLASSIFICATION_ICON.get(decision["classification"], "•")
        label = decision["classification"].replace("_", " ")
        note = "{} **Escalated to you &mdash; {}**\n\n{}".format(icon, label, explain)
        if decision.get("notes"):
            note += "\n\n*{}*".format(decision["notes"])
        chat_history.append({"role": "assistant", "content": note})

    return chat_history, thread_state, ""


def reset_conversation():
    return [], {"messages": [], "counter": 0}, ""


def _greeting():
    hour = datetime.datetime.now().hour
    part = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
    return part, datetime.date.today().strftime("%A, %B %d")


def get_escalated_items(limit=10):
    sql = """
        SELECT d.gmail_thread_id, d.classification, d.notes, d.created_at, i.firm_name
        FROM drafts d LEFT JOIN investor_file i ON i.id = d.investor_id
        WHERE d.classification NOT IN ('known_question_draft', 'thread_locked_skip', 'do_not_contact_skip')
        ORDER BY d.created_at DESC LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (limit,))
        return cur.fetchall()


def get_pending_approvals():
    sql = """
        SELECT id, firm_name, capital_type, thesis, source, source_date
        FROM investor_file
        WHERE approved = FALSE AND process_stage NOT IN ('passed', 'do_not_contact')
        ORDER BY created_at
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def get_followups_due(lookahead_days=2):
    sql = """
        SELECT o.investor_id, i.firm_name, o.touch_number, o.status, o.sent_at
        FROM outreach_touches o JOIN investor_file i ON i.id = o.investor_id
        ORDER BY o.investor_id, o.touch_number
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    by_investor = {}
    for investor_id, firm_name, touch_number, status, sent_at in rows:
        entry = by_investor.setdefault(investor_id, {"firm_name": firm_name, "touches": {}})
        entry["touches"][touch_number] = {"status": status, "sent_at": sent_at}

    now = datetime.datetime.now(datetime.timezone.utc)
    window = datetime.timedelta(days=lookahead_days)
    due = []
    for info in by_investor.values():
        touches = info["touches"]
        t1 = touches.get(1)
        if t1 and t1["status"] == "sent" and t1["sent_at"] and 2 not in touches:
            due_date = t1["sent_at"] + datetime.timedelta(days=4)
            if now >= due_date - window:
                due.append({"firm": info["firm_name"], "label": "Day-4 follow-up",
                            "due_date": due_date, "overdue": now >= due_date})
        if t1 and t1["status"] == "sent" and t1["sent_at"] and 2 in touches and 3 not in touches:
            due_date = t1["sent_at"] + datetime.timedelta(days=11)
            if now >= due_date - window:
                due.append({"firm": info["firm_name"], "label": "Day-11 follow-up",
                            "due_date": due_date, "overdue": now >= due_date})
    return due


def _detail(details, key, default=""):
    return details.get(key, default) if isinstance(details, dict) else default


def describe_activity(actor, action_type, details):
    firm = _detail(details, "firm", "")
    if action_type == "outbound_sent":
        return "📤 Sent a note to {}".format(firm or "a firm")
    if action_type == "outbound_drafted":
        return "📝 Drafted a note to {} ({})".format(firm or "a firm", _detail(details, "capital_type", ""))
    if action_type == "inbound_classified":
        sender = _detail(details, "sender", "someone")
        return "📥 {} replied &mdash; classified as {}".format(sender, _detail(details, "classification", ""))
    if action_type == "link_granted":
        return "🗂️ Granted {} data room access to {}".format(_detail(details, "tier", ""), firm or "a firm")
    if action_type == "investor_added":
        return "🔭 Scout found {}".format(firm or "a new firm")
    if action_type == "approval":
        return "✅ You {} {}".format(_detail(details, "decision", "decided on"), firm or "a firm")
    if action_type == "draft_survival_measured":
        return "📊 Measured draft survival for a sent note"
    return "• {} &mdash; {}".format(actor, action_type)


def get_recent_activity(limit=8):
    sql = """
        SELECT actor, action_type, details, occurred_at
        FROM activity_log WHERE action_type != 'number_quoted'
        ORDER BY occurred_at DESC LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (limit,))
        return cur.fetchall()


def render_today():
    part, today_str = _greeting()
    escalated = get_escalated_items()
    pending = get_pending_approvals()
    followups = get_followups_due()
    need_count = len(escalated) + len(pending) + len(followups)

    header = (
        '<h2>Good {part}, {name}</h2>'
        '<p class="today-sub">{date} &middot; {n} thing{s} need{es} you</p>'
    ).format(
        part=part, name=FOUNDER_DISPLAY_NAME, date=today_str, n=need_count,
        s="" if need_count == 1 else "s", es="s" if need_count == 1 else "",
    )

    cards = []
    for thread_id, classification, notes, created_at, firm_name in escalated:
        label = classification.replace("_", " ")
        cards.append(
            '<div class="today-card"><h4>🚩 {firm} needs your read</h4>'
            '<p>{label}{notes}</p><p class="today-meta">thread {thread} &middot; {when}</p></div>'
            .format(firm=firm_name or "Someone", label=label,
                    notes=(" &mdash; " + notes) if notes else "", thread=thread_id, when=created_at)
        )
    for investor_id, firm_name, capital_type, thesis, source, source_date in pending:
        cards.append(
            '<div class="today-card"><h4>📋 {firm} awaiting your approval</h4>'
            '<p>{capital_type} &middot; {thesis}</p>'
            '<p class="today-meta">source: {source} ({date})</p></div>'
            .format(firm=firm_name, capital_type=CAPITAL_TYPE_LABEL.get(capital_type, capital_type),
                    thesis=(thesis or "")[:160], source=source or "unknown", date=source_date or "")
        )
    for item in followups:
        status = "overdue" if item["overdue"] else "due soon"
        cards.append(
            '<div class="today-card"><h4>⏰ {label} for {firm} &mdash; {status}</h4>'
            '<p class="today-meta">due {due}</p></div>'
            .format(label=item["label"], firm=item["firm"], status=status, due=item["due_date"].date())
        )

    top_html = header + ("".join(cards) if cards else '<p class="chain-empty">Nothing waiting on you right now.</p>')

    activity_rows = get_recent_activity()
    if activity_rows:
        activity_html = "".join(
            '<p class="activity-line">{} <span class="today-meta">&middot; {}</span></p>'.format(
                describe_activity(actor, action_type, details), occurred_at)
            for actor, action_type, details, occurred_at in activity_rows
        )
    else:
        activity_html = '<p class="chain-empty">Nothing logged yet.</p>'

    return top_html, activity_html


def get_drafted_touches_choices():
    sql = """
        SELECT o.id, i.firm_name, o.touch_number
        FROM outreach_touches o JOIN investor_file i ON i.id = o.investor_id
        WHERE o.status = 'drafted' ORDER BY o.drafted_at
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [("{} -- touch #{}".format(firm, touch_number), touch_id) for touch_id, firm, touch_number in rows]


def do_mark_sent(touch_id):
    if touch_id is None:
        top, activity = render_today()
        return "Pick a drafted note first.", top, activity, gr.Dropdown(choices=get_drafted_touches_choices())
    with _connect() as conn:
        investor_id = outreach.mark_sent(conn, int(touch_id))
    top, activity = render_today()
    status = "✅ Marked as sent (investor_file.id={} now contacted).".format(investor_id)
    return status, top, activity, gr.Dropdown(choices=get_drafted_touches_choices())


def render_pipeline():
    sql = """
        SELECT firm_name, capital_type, process_stage, heat, last_touch_at, next_action
        FROM investor_file ORDER BY firm_name
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    by_stage = {stage: [] for stage, _ in STAGE_ORDER}
    for firm_name, capital_type, process_stage, heat, last_touch_at, next_action in rows:
        by_stage.setdefault(process_stage, []).append(
            (firm_name, capital_type, heat, last_touch_at, next_action)
        )

    columns_html = []
    for stage, label in STAGE_ORDER:
        firms = by_stage.get(stage, [])
        if firms:
            cards = "".join(
                '<div class="pipeline-card"><b>{icon} {firm}</b>'
                '<div class="today-meta">{capital_type}</div>{touch}{action}</div>'.format(
                    icon=HEAT_ICON.get(heat, "•"), firm=firm_name,
                    capital_type=CAPITAL_TYPE_LABEL.get(capital_type, capital_type),
                    touch='<div class="today-meta">last touch: {}</div>'.format(last_touch_at) if last_touch_at else "",
                    action='<div class="today-meta">next: {}</div>'.format(next_action) if next_action else "",
                )
                for firm_name, capital_type, heat, last_touch_at, next_action in firms
            )
        else:
            cards = '<p class="chain-empty">No firms</p>'
        columns_html.append(
            '<div class="pipeline-column"><h4>{label} ({n})</h4>{cards}</div>'.format(
                label=label, n=len(firms), cards=cards)
        )
    return '<div class="pipeline-row">{}</div>'.format("".join(columns_html))


def get_firm_choices():
    sql = "SELECT id, firm_name, capital_type FROM investor_file ORDER BY firm_name"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [("{} ({})".format(name, CAPITAL_TYPE_LABEL.get(ct, ct)), id_) for id_, name, ct in rows]


def render_firm_profile(investor_id):
    if investor_id is None:
        return "Pick a firm above and click View profile.", gr.update(visible=False)

    sql = """
        SELECT firm_name, partner_name, partner_email, capital_type, thesis, stage_fit,
               check_size_min, check_size_max, check_size_currency, domicile, domicile_blocker,
               deployment_markets, warm_path, why_them, portfolio_examples, conflicts, heat,
               process_stage, source, source_date, notes, approved
        FROM investor_file WHERE id = %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (investor_id,))
        row = cur.fetchone()
        if row is None:
            return "Firm not found.", gr.update(visible=False)
        (firm_name, partner_name, partner_email, capital_type, thesis, stage_fit,
         check_min, check_max, check_currency, domicile, domicile_blocker,
         deployment_markets, warm_path, why_them, portfolio_examples, conflicts, heat,
         process_stage, source, source_date, notes, approved) = row

        cur.execute(
            "SELECT touch_number, status, template_capital_type, drafted_at, sent_at "
            "FROM outreach_touches WHERE investor_id = %s ORDER BY touch_number",
            (investor_id,),
        )
        touches = cur.fetchall()

        cur.execute(
            "SELECT classification, notes, created_at FROM drafts WHERE investor_id = %s ORDER BY created_at DESC",
            (investor_id,),
        )
        drafts_rows = cur.fetchall()

        cur.execute(
            "SELECT tier, expiry_date, created_at FROM data_room_links WHERE investor_id = %s ORDER BY created_at DESC",
            (investor_id,),
        )
        dr_rows = cur.fetchall()

    check_size = "-"
    if check_min or check_max:
        check_size = "{} - {} {}".format(check_min or "?", check_max or "?", check_currency or "")

    fields = [
        ("Partner", "{} ({})".format(partner_name or "-", partner_email or "no email on file")),
        ("Capital type", CAPITAL_TYPE_LABEL.get(capital_type, capital_type)),
        ("Stage", process_stage),
        ("Heat", "{} {}".format(HEAT_ICON.get(heat, "•"), heat or "unknown")),
        ("Thesis", thesis or "-"),
        ("Stage fit", stage_fit or "-"),
        ("Check size", check_size),
        ("Domicile", "{}{}".format(domicile or "-", " -- BLOCKER" if domicile_blocker else "")),
        ("Deployment markets", ", ".join(deployment_markets) if deployment_markets else "-"),
        ("Warm path", warm_path or "none"),
        ("Why them", why_them or "-"),
        ("Portfolio examples", portfolio_examples or "-"),
        ("Conflicts", conflicts or "none noted"),
        ("Source", "{} ({})".format(source or "unknown", source_date or "")),
        ("Notes", (notes or "-").replace("\n", "<br>")),
    ]
    field_html = "".join("<p><b>{}:</b> {}</p>".format(k, v) for k, v in fields)

    touch_html = "".join(
        '<p class="today-meta">Touch #{}: {} ({}) -- drafted {}{}</p>'.format(
            n, status, tct, drafted, (", sent " + str(sent)) if sent else "")
        for n, status, tct, drafted, sent in touches
    ) or '<p class="chain-empty">No outreach yet.</p>'

    draft_html = "".join(
        '<p class="today-meta">{}: {}{}</p>'.format(created, cls, (" -- " + n) if n else "")
        for cls, n, created in drafts_rows
    ) or '<p class="chain-empty">No inbound classified yet.</p>'

    dr_html = "".join(
        '<p class="today-meta">{} tier, expires {}, granted {}</p>'.format(tier, exp, created)
        for tier, exp, created in dr_rows
    ) or '<p class="chain-empty">No data room access granted yet.</p>'

    status_badge = (
        '<span class="badge badge-green">APPROVED</span>' if approved
        else '<span class="badge badge-amber">AWAITING APPROVAL</span>'
    )

    html = (
        '<div class="specialist-card">'
        '<div class="specialist-row"><span class="specialist-title">{firm}</span>{badge}</div>'
        '{fields}<h4>Outreach</h4>{touches}<h4>Inbox</h4>{drafts}<h4>Data Room</h4>{dr}'
        '</div>'
    ).format(firm=firm_name, badge=status_badge, fields=field_html, touches=touch_html, drafts=draft_html, dr=dr_html)

    return html, gr.update(visible=not approved)


def do_approve(investor_id):
    if investor_id is None:
        return "Pick a firm first.", "", gr.update(visible=False)
    with _connect() as conn:
        firm = founder_actions.approve_investor(conn, int(investor_id))
    html, vis = render_firm_profile(investor_id)
    return "✅ Approved {}.".format(firm), html, vis


def do_pass(investor_id, reason):
    if investor_id is None:
        return "Pick a firm first.", "", gr.update(visible=False)
    with _connect() as conn:
        firm = founder_actions.pass_investor(conn, int(investor_id), reason or None)
    html, vis = render_firm_profile(investor_id)
    return "Passed on {}.".format(firm), html, vis


def do_grant_access(investor_id, tier, email, deck_path, expiry_days):
    if investor_id is None:
        return "Pick a firm first.", "", gr.update(visible=False)
    if not email or not email.strip():
        return "Enter a recipient email first.", "", gr.update(visible=False)
    if not deck_path:
        return "Upload a deck PDF first.", "", gr.update(visible=False)
    try:
        with _connect() as conn:
            result = data_room.grant_access(
                conn, int(investor_id), tier, email.strip(), deck_path,
                int(expiry_days) if expiry_days else data_room.DEFAULT_EXPIRY_DAYS,
            )
    except Exception as exc:
        html, vis = render_firm_profile(investor_id)
        return "⚠️ {}".format(exc), html, vis
    html, vis = render_firm_profile(investor_id)
    status = "✅ Granted {} tier -- share this link: {}".format(tier, result["share_url"])
    return status, html, vis


def render_fact_sheet():
    sql = """
        SELECT field_key, field_label, category, value, unit, as_of_date, source, refresh_by, agent_quotable
        FROM canon_facts ORDER BY category, field_label
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    today = datetime.date.today()
    by_category = {}
    for field_key, field_label, category, value, unit, as_of_date, source, refresh_by, agent_quotable in rows:
        by_category.setdefault(category, []).append(
            (field_label, value, unit, as_of_date, source, refresh_by, agent_quotable)
        )

    sections = []
    for category in sorted(by_category):
        cards = []
        for field_label, value, unit, as_of_date, source, refresh_by, agent_quotable in by_category[category]:
            if value is None:
                badge = '<span class="badge badge-gray">NOT SET</span>'
            elif not agent_quotable:
                badge = '<span class="badge badge-gray">INTERNAL ONLY</span>'
            elif refresh_by and refresh_by < today:
                badge = '<span class="badge badge-amber">STALE</span>'
            else:
                badge = '<span class="badge badge-green">FRESH</span>'
            value_line = "{}{}".format(value if value is not None else "-", (" " + unit) if unit else "")
            cards.append(
                '<div class="today-card"><div class="specialist-row"><b>{label}</b>{badge}</div>'
                '<p>{value}</p><p class="today-meta">as of {as_of} &middot; source: {source}</p></div>'
                .format(label=field_label, badge=badge, value=value_line,
                        as_of=as_of_date or "-", source=source or "unknown")
            )
        sections.append(
            '<h3>{}</h3><div class="factsheet-grid">{}</div>'.format(category.title(), "".join(cards))
        )
    return "".join(sections)


with gr.Blocks(title="RAISE Dashboard") as demo:
    with gr.Column(elem_classes=["app-header"]):
        gr.HTML("<h1>RAISE</h1><p>Your fundraise, one place. A person still hits send.</p>")

    with gr.Tab("☀️ Today"):
        _today_top0, _today_activity0 = render_today()
        today_top = gr.HTML(_today_top0)

        with gr.Group():
            gr.Markdown("### Mark a note as sent")
            gr.Markdown(
                "After you've actually hit send in Gmail, record it here so the pipeline stays accurate. "
                "This never sends anything -- it only updates the record."
            )
            sent_dd = gr.Dropdown(choices=get_drafted_touches_choices(), label="Drafted note")
            sent_btn = gr.Button("Mark as sent", variant="primary")
            sent_status = gr.Markdown()

        gr.Markdown("### Recently happened")
        today_activity = gr.HTML(_today_activity0)
        today_refresh = gr.Button("🔄 Refresh", size="sm")

        def _refresh_today():
            top, activity = render_today()
            return top, activity, gr.Dropdown(choices=get_drafted_touches_choices())

        today_refresh.click(fn=_refresh_today, outputs=[today_top, today_activity, sent_dd])
        sent_btn.click(fn=do_mark_sent, inputs=sent_dd, outputs=[sent_status, today_top, today_activity, sent_dd])

    with gr.Tab("📊 Pipeline"):
        gr.Markdown(
            "Grouped by `investor_file.process_stage` -- narrower than SPECIALISTS.md's aspirational stage "
            "list, this reflects what's actually queryable today."
        )
        pipeline_html = gr.HTML(render_pipeline())
        pipeline_refresh = gr.Button("🔄 Refresh", size="sm")
        pipeline_refresh.click(fn=render_pipeline, outputs=pipeline_html)

    with gr.Tab("🏢 Firms"):
        firm_dd = gr.Dropdown(choices=get_firm_choices(), label="Firm")
        firm_view_btn = gr.Button("View profile", variant="primary")
        firm_profile_html = gr.HTML()
        with gr.Group(visible=False) as approve_group:
            gr.Markdown("This firm is awaiting your approval.")
            with gr.Row():
                approve_btn = gr.Button("✅ Approve", variant="primary")
                pass_btn = gr.Button("Pass")
            pass_reason = gr.Textbox(label="Pass reason (optional)")
            firm_action_status = gr.Markdown()

        with gr.Group():
            gr.Markdown("### Grant Data Room access")
            gr.Markdown(
                "Creates a per-firm Drive folder, watermarks the deck, uploads it, shares it with "
                "exactly the email below, and registers a tracking link -- the same "
                "`data_room.grant_access()` the CLI uses. `full` tier is refused unless the firm is "
                "approved."
            )
            with gr.Row():
                grant_tier = gr.Dropdown(choices=["teaser", "standard", "full"], value="teaser", label="Tier")
                grant_email = gr.Textbox(label="Recipient email")
                grant_expiry = gr.Number(label="Expiry (days)", value=data_room.DEFAULT_EXPIRY_DAYS, precision=0)
            grant_deck = gr.File(label="Deck PDF", type="filepath", file_types=[".pdf"])
            grant_btn = gr.Button("Grant access", variant="primary")
            grant_status = gr.Markdown()

        firm_view_btn.click(fn=render_firm_profile, inputs=firm_dd, outputs=[firm_profile_html, approve_group])
        approve_btn.click(fn=do_approve, inputs=firm_dd,
                           outputs=[firm_action_status, firm_profile_html, approve_group])
        pass_btn.click(fn=do_pass, inputs=[firm_dd, pass_reason],
                        outputs=[firm_action_status, firm_profile_html, approve_group])
        grant_btn.click(fn=do_grant_access, inputs=[firm_dd, grant_tier, grant_email, grant_deck, grant_expiry],
                         outputs=[grant_status, firm_profile_html, approve_group])

    with gr.Tab("📑 Fact Sheet"):
        factsheet_html = gr.HTML(render_fact_sheet())
        factsheet_refresh = gr.Button("🔄 Refresh", size="sm")
        factsheet_refresh.click(fn=render_fact_sheet, outputs=factsheet_html)

    with gr.Tab("🧪 Try it"):
        gr.Markdown(
            "## Have a conversation with RAISE\n"
            "Play the VC: type a message and send it, or click an example below. RAISE runs the exact "
            "same handling ladder Inbox uses on a real reply (`classify_thread.classify`) against what "
            "you type, live against your real `canon_facts` and `question_bank` &mdash; nothing is "
            "hardcoded or scripted for the demo. **A known question gets a drafted reply.** Anything "
            "about legal terms, price, a meeting ask, a data-room ask, or simply not in the question "
            "bank gets **escalated to you instead** &mdash; exactly what would happen with a real reply, "
            "no draft, no guess. Keep going: it's a real back-and-forth, and each message is judged on "
            "its own. Nothing here is sent, drafted into Gmail, or written to your database."
        )
        vc_chat = gr.Chatbot(label="Conversation", height=380, buttons=["copy"])
        vc_input = gr.Textbox(label="Type as the VC", placeholder="e.g. What's your current ARR?", lines=2)
        with gr.Row():
            for _label, _text in VC_EXAMPLES:
                _ex_btn = gr.Button(_label, size="sm")
                _ex_btn.click(fn=(lambda t=_text: t), outputs=vc_input)
        with gr.Row():
            send_btn = gr.Button("Send", variant="primary")
            reset_btn = gr.Button("Reset conversation")
        thread_state = gr.State({"messages": [], "counter": 0})

        send_btn.click(fn=send_vc_message, inputs=[vc_input, vc_chat, thread_state],
                        outputs=[vc_chat, thread_state, vc_input])
        vc_input.submit(fn=send_vc_message, inputs=[vc_input, vc_chat, thread_state],
                         outputs=[vc_chat, thread_state, vc_input])
        reset_btn.click(fn=reset_conversation, outputs=[vc_chat, thread_state, vc_input])

        gr.Markdown("---")
        with gr.Group():
            gr.Markdown("## Or just check one answer")
            gr.Markdown(
                "A lighter lookup, no conversation needed: pick a question from the bank and see exactly "
                "what RAISE would say right now. Try one whose fact is missing or stale (Fact Sheet tab) "
                "to see it refuse to answer rather than guess."
            )
            question_dd = gr.Dropdown(choices=get_question_choices(), label="Question")
            render_btn = gr.Button("Render", variant="primary")
            render_out = gr.Markdown(elem_classes=["demo-output"])
            render_btn.click(fn=render_question, inputs=question_dd, outputs=render_out)

    with gr.Tab("⚙️ Behind the scenes"):
        gr.Markdown("### Build status")
        gr.HTML(render_specialist_cards())

        gr.Markdown("### Most recent chain activity")
        chain_html = gr.HTML(load_recent_chain())
        chain_refresh = gr.Button("🔄 Refresh chain", size="sm")
        chain_refresh.click(fn=load_recent_chain, outputs=chain_html)

        gr.Markdown("### Raw tables")
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


if __name__ == "__main__":
    demo.launch(share=False, theme=THEME, css=CSS)
