"""Shared canon_facts template-rendering logic.

Extracted from drift_test.py so Stage 2's inbox classifier renders answers
the exact same way the drift test validates them -- one source of truth for
"how a {{field_key}} template becomes real text," per SOUL's "one record, or
nothing."
"""

import datetime
import re

PLACEHOLDER_RE = re.compile(r"\{\{([a-z0-9_]+)\}\}")
RAW_NUMBER_RE = re.compile(r"\d")


def strip_placeholders(template):
    return PLACEHOLDER_RE.sub("", template)


def check_question(template, facts):
    placeholders = PLACEHOLDER_RE.findall(template)
    result = {
        "placeholders": placeholders,
        "hygiene_errors": [],
        "findings": [],
        "renderable": True,
    }

    text_without_placeholders = strip_placeholders(template)
    if RAW_NUMBER_RE.search(text_without_placeholders):
        result["hygiene_errors"].append(
            "template contains a raw number outside a {{field_key}} placeholder"
        )

    today = datetime.date.today()
    rendered = template
    for field_key in placeholders:
        fact = facts.get(field_key)
        if fact is None:
            result["hygiene_errors"].append(
                "field '{}' referenced by this question does not exist in canon_facts".format(field_key)
            )
            result["renderable"] = False
            continue

        if fact["value"] is None:
            result["findings"].append("field '{}': MISSING (no value set)".format(field_key))
            result["renderable"] = False
            continue

        if fact["refresh_by"] is not None and fact["refresh_by"] < today:
            result["findings"].append(
                "field '{}': STALE (refresh_by {} has passed)".format(field_key, fact["refresh_by"])
            )
            result["renderable"] = False

        if not fact["agent_quotable"]:
            result["findings"].append(
                "field '{}': NOT QUOTABLE (agent_quotable = false, must never be cited)".format(field_key)
            )
            result["renderable"] = False

        rendered = rendered.replace("{{" + field_key + "}}", str(fact["value"]))

    result["rendered"] = rendered if result["renderable"] else None
    return result


def load_facts(cur):
    """Load all canon_facts into an in-memory dict keyed by field_key."""
    cur.execute("SELECT field_key, value, refresh_by, agent_quotable FROM canon_facts")
    return {
        row[0]: {"value": row[1], "refresh_by": row[2], "agent_quotable": row[3]}
        for row in cur.fetchall()
    }
