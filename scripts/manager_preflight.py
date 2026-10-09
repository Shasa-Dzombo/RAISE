"""Reusable Manager pre-send checks.

This module is intentionally deterministic and side-effect-light. It validates
an already prepared outbound action; callers decide whether the result becomes
a Gmail draft or an approved human action. It never sends mail.
"""

import datetime
import json


def _escalate(cur, thread_ref, investor_id, reason, escalation_type="preflight_failure"):
    cur.execute(
        """
        INSERT INTO escalations
            (thread_ref, investor_id, escalation_type, reason, created_by)
        VALUES (%s, %s, %s, %s, 'Manager')
        RETURNING id
        """,
        (thread_ref, investor_id, escalation_type, reason),
    )
    return cur.fetchone()[0]


def preflight(
    conn,
    *,
    thread_ref,
    investor_id,
    recipient_email,
    draft_text,
    cited_fact_keys=(),
    recipient_language="en",
    recipient_seniority="unknown",
    build_stage=4,
    outbound_kind="first_note",
    sender_mailbox_id=None,
    sender_provider=None,
):
    """Run Manager checks and return a structured decision.

    `cited_fact_keys` must be supplied by the renderer that created the draft.
    This avoids trying to infer numbers from arbitrary prose.
    Sender metadata is optional for legacy callers; when supplied, it must
    resolve to an active mailbox and match the selected provider.
    """
    failures = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(founder_locked, FALSE), COALESCE(preflight_failures, 0)
            FROM thread_controls WHERE thread_ref = %s
            """,
            (thread_ref,),
        )
        control = cur.fetchone()
        if control and control[0]:
            failures.append("founder-lock: thread is permanently locked")

        cur.execute(
            """
            SELECT do_not_contact, partner_email, working_language, partner_seniority
            FROM investor_file WHERE id = %s
            """,
            (investor_id,),
        )
        investor = cur.fetchone()
        if investor is None:
            failures.append("do-not-contact: investor record does not exist")
        else:
            do_not_contact, partner_email, working_language, partner_seniority = investor
            if do_not_contact:
                failures.append("do-not-contact: investor is blocked")
            if recipient_email and partner_email and recipient_email.lower() != partner_email.lower():
                cur.execute(
                    """
                    SELECT 1
                    FROM contact_identities
                    WHERE investor_id = %s
                      AND normalized_email = lower(%s)
                      AND active = TRUE
                    """,
                    (investor_id, recipient_email),
                )
                if cur.fetchone() is None:
                    failures.append("recipient: email is not an active contact for this investor")
            if recipient_language and working_language and recipient_language.lower() != working_language.lower():
                failures.append("language: recipient language does not match investor record")
            if recipient_seniority == "unknown":
                recipient_seniority = partner_seniority

        if sender_mailbox_id is not None or sender_provider is not None:
            cur.execute(
                """
                SELECT provider, active
                FROM sender_mailboxes
                WHERE id = %s
                """,
                (sender_mailbox_id,),
            )
            mailbox = cur.fetchone()
            if mailbox is None or not mailbox[1]:
                failures.append("sender: selected mailbox does not exist or is inactive")
            elif sender_provider and mailbox[0] != sender_provider:
                failures.append("sender: selected provider does not match mailbox metadata")

        today = datetime.date.today()
        for field_key in sorted(set(cited_fact_keys)):
            cur.execute(
                """
                SELECT value, source, as_of_date, refresh_by, agent_quotable
                FROM canon_facts WHERE field_key = %s
                """,
                (field_key,),
            )
            fact = cur.fetchone()
            if fact is None:
                failures.append("number: {} is not in canon_facts".format(field_key))
                continue
            value, source, as_of_date, refresh_by, agent_quotable = fact
            if value is None or not source or not as_of_date:
                failures.append("number: {} is missing value, source, or date".format(field_key))
            if refresh_by is not None and refresh_by < today:
                failures.append("staleness: {} passed refresh_by".format(field_key))
            if not agent_quotable:
                failures.append("number: {} is not agent-quotable".format(field_key))

            cur.execute(
                """
                SELECT DISTINCT value_snapshot
                FROM outbound_fact_quotes
                WHERE field_key = %s
                  AND value_snapshot <> %s::jsonb
                LIMIT 1
                """,
                (field_key, json.dumps(value)),
            )
            if cur.fetchone() is not None:
                failures.append("consistency: {} differs from a prior quoted value".format(field_key))

        # Stage 4 never sends. Stage 5 only permits cold first notes, and this
        # function still leaves the final action to the caller.
        if build_stage < 5 and outbound_kind != "draft":
            failures.append("autonomy: current build stage permits drafts only")
        if recipient_seniority in ("partner", "principal") and outbound_kind != "draft":
            failures.append("seniority: partner-level mail must remain a draft")

        if failures:
            cur.execute(
                """
                INSERT INTO thread_controls
                    (thread_ref, investor_id, preflight_failures, last_failure_reason, updated_at)
                VALUES (%s, %s, 1, %s, now())
                ON CONFLICT (thread_ref) DO UPDATE SET
                    investor_id = EXCLUDED.investor_id,
                    preflight_failures = thread_controls.preflight_failures + 1,
                    last_failure_reason = EXCLUDED.last_failure_reason,
                    updated_at = now()
                """,
                (thread_ref, investor_id, "; ".join(failures)),
            )
            escalation_id = _escalate(cur, thread_ref, investor_id, "; ".join(failures))
            return {
                "allowed": False,
                "failures": failures,
                "escalation_id": escalation_id,
            }

        cur.execute(
            """
            INSERT INTO thread_controls (thread_ref, investor_id, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (thread_ref) DO UPDATE SET updated_at = now()
            """,
            (thread_ref, investor_id),
        )
        return {"allowed": True, "failures": [], "escalation_id": None}


def lock_thread(conn, thread_ref, investor_id=None, reason="Founder replied"):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO thread_controls
                (thread_ref, investor_id, founder_locked, lock_reason, locked_at, locked_by)
            VALUES (%s, %s, TRUE, %s, now(), 'founder')
            ON CONFLICT (thread_ref) DO UPDATE SET
                founder_locked = TRUE, lock_reason = EXCLUDED.lock_reason,
                locked_at = now(), locked_by = 'founder', updated_at = now()
            """,
            (thread_ref, investor_id, reason),
        )
        cur.execute(
            """
            INSERT INTO activity_log
                (actor, action_type, entity_type, entity_id, thread_ref, details)
            VALUES ('founder', 'thread_locked', 'thread', %s, %s, %s)
            """,
            (thread_ref, thread_ref, json.dumps({"reason": reason})),
        )
