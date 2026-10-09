"""Provider-neutral contact and sender metadata helpers.

This module deliberately does not send mail. Provider adapters may create
approval artifacts, but Manager policy remains the authority for any outbound
action.
"""

import re

EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def normalize_email(value):
    """Return a canonical address or raise for malformed input."""
    address = (value or "").strip().strip("<>").lower()
    if not EMAIL_RE.fullmatch(address):
        raise ValueError("invalid email address")
    return address


def email_domain(value):
    return normalize_email(value).rsplit("@", 1)[1]


def contact_from_row(row):
    """Convert a contact query row into provider-independent metadata."""
    if row is None:
        return None
    return {
        "id": row[0],
        "investor_id": row[1],
        "display_name": row[2],
        "email_address": row[3],
        "normalized_email": row[4],
        "email_domain": row[5],
        "role": row[6],
        "is_primary": row[7],
        "is_verified": row[8],
    }


def find_contact(cur, address):
    normalized = normalize_email(address)
    cur.execute(
        """
        SELECT id, investor_id, display_name, email_address, normalized_email,
               email_domain, role, is_primary, is_verified
        FROM contact_identities
        WHERE normalized_email = %s AND active = TRUE
        """,
        (normalized,),
    )
    return contact_from_row(cur.fetchone())


def ensure_contact(cur, address, investor_id=None, display_name=None, source="inbound"):
    normalized = normalize_email(address)
    domain = email_domain(normalized)
    cur.execute(
        """
        INSERT INTO contact_identities
            (investor_id, display_name, email_address, normalized_email,
             email_domain, source)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (normalized_email) DO UPDATE
        SET investor_id = COALESCE(contact_identities.investor_id, EXCLUDED.investor_id),
            display_name = COALESCE(contact_identities.display_name, EXCLUDED.display_name),
            updated_at = now()
        RETURNING id
        """,
        (investor_id, display_name, address.strip(), normalized, domain, source),
    )
    return cur.fetchone()[0]


def find_sender_mailbox(cur, mailbox_address):
    normalized = normalize_email(mailbox_address)
    cur.execute(
        """
        SELECT id, provider, mailbox_address, calendar_id, draft_only,
               approval_policy
        FROM sender_mailboxes
        WHERE normalized_address = %s AND active = TRUE
        """,
        (normalized,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "provider": row[1],
        "mailbox_address": row[2],
        "calendar_id": row[3],
        "draft_only": row[4],
        "approval_policy": row[5],
    }
