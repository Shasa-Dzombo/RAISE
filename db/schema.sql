-- RAISE — shared record schema (Stage 1)
-- Postgres 15+ with pgvector extension.
-- pgvector is used only for question_bank similarity search (finding the closest
-- approved answer to an incoming diligence question).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CANON FACTS
-- Every number any agent may ever write comes from this table, or it does not
-- get written. No agent may insert into fact_history directly — the app layer
-- writes the prior row there before updating canon_facts, so every value ever
-- quoted is reconstructable.
-- ============================================================================

CREATE TABLE canon_facts (
    id              SERIAL PRIMARY KEY,
    field_key       TEXT NOT NULL UNIQUE,       -- e.g. 'arr_usd', 'domicile'
    field_label     TEXT NOT NULL,              -- human-readable name
    category        TEXT NOT NULL,              -- financials | fx | regulatory | domicile | markets | round | team | other
    value           JSONB,                      -- NULL = not yet supplied
    unit            TEXT,                       -- 'USD', '%', 'months', etc. NULL if not applicable
    as_of_date      DATE,                       -- date the value was true as of
    source          TEXT,                       -- where the number came from (e.g. 'Aug 2026 management accounts')
    source_url      TEXT,
    is_public       BOOLEAN NOT NULL DEFAULT FALSE,   -- ok to state to a fund with no NDA
    agent_quotable  BOOLEAN NOT NULL DEFAULT TRUE,    -- FALSE = tracked for internal consistency only; no agent may ever cite it (e.g. valuation, cap)
    refresh_by      DATE,                       -- after this date the fact is stale and must not be quoted
    notes           TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_canon_facts_category ON canon_facts (category);
CREATE INDEX idx_canon_facts_refresh_by ON canon_facts (refresh_by);

-- Append-only audit trail. A row is inserted here (via app logic, before
-- overwrite) every time a canon_facts value changes, so any number quoted in
-- the past can be traced to what was true when it was quoted.
CREATE TABLE fact_history (
    id              BIGSERIAL PRIMARY KEY,
    fact_id         INTEGER NOT NULL REFERENCES canon_facts (id),
    field_key       TEXT NOT NULL,
    value           JSONB,
    unit            TEXT,
    as_of_date      DATE,
    source          TEXT,
    source_url      TEXT,
    is_public       BOOLEAN,
    agent_quotable  BOOLEAN,
    refresh_by      DATE,
    notes           TEXT,
    superseded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by   TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_fact_history_fact_id ON fact_history (fact_id);

-- ============================================================================
-- STORY PACK
-- Founder-signed narrative. No agent may edit a signed section; a new version
-- must be created and re-signed.
-- ============================================================================

CREATE TABLE story_pack (
    id              SERIAL PRIMARY KEY,
    section_key     TEXT NOT NULL,              -- 'one_liner' | 'problem' | 'why_now' | 'product' | 'gtm' | 'use_of_funds'
    version         INTEGER NOT NULL DEFAULT 1,
    content         TEXT NOT NULL,
    is_signed       BOOLEAN NOT NULL DEFAULT FALSE,
    signed_by       TEXT,
    signed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (section_key, version)
);

-- Convenience view: the current signed version of each section, if any.
CREATE VIEW story_pack_current AS
SELECT DISTINCT ON (section_key) *
FROM story_pack
WHERE is_signed = TRUE
ORDER BY section_key, version DESC;

-- ============================================================================
-- INVESTOR FILE
-- One record per firm. Created before question_bank_asked_by, which
-- references it.
-- ============================================================================

CREATE TABLE investor_file (
    id                  SERIAL PRIMARY KEY,
    firm_name           TEXT NOT NULL,
    partner_name        TEXT,
    partner_email       TEXT,
    capital_type        TEXT NOT NULL CHECK (capital_type IN (
                            'africa_focused_vc', 'global_vc_africa_portfolio',
                            'dfi_impact', 'local_angel_syndicate'
                        )),
    thesis              TEXT,
    check_size_min      NUMERIC,
    check_size_max      NUMERIC,
    check_size_currency TEXT,
    domicile            TEXT,               -- fund's domicile, for eligibility routing
    deployment_markets  TEXT[],             -- actual markets invested in (not just stated geography)
    domicile_blocker    BOOLEAN NOT NULL DEFAULT FALSE,  -- e.g. needs a flip we haven't done — route to counsel, not outreach
    warm_path           TEXT,               -- who can make the intro, if anyone
    process_stage       TEXT NOT NULL DEFAULT 'target' CHECK (process_stage IN (
                            'target', 'contacted', 'replied', 'diligence',
                            'term_sheet', 'closed_won', 'closed_lost', 'passed', 'do_not_contact'
                        )),
    do_not_contact      BOOLEAN NOT NULL DEFAULT FALSE,
    working_language    TEXT NOT NULL DEFAULT 'en',
    heat                TEXT CHECK (heat IN ('cold', 'warm', 'hot')),
    last_touch_at       TIMESTAMPTZ,
    next_action         TEXT,
    next_action_due     DATE,
    source              TEXT,               -- e.g. 'Partech Africa report', 'Briter Intelligence'
    source_date         DATE,
    notes                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_investor_file_process_stage ON investor_file (process_stage);
CREATE INDEX idx_investor_file_capital_type ON investor_file (capital_type);
CREATE UNIQUE INDEX idx_investor_file_firm_partner ON investor_file (firm_name, COALESCE(partner_email, ''));

-- ============================================================================
-- QUESTION BANK
-- Diligence answers are templates resolved at read time from canon_facts —
-- never static text with numbers baked in. A template like
-- "Our ARR is {{arr_usd}} USD as of {{arr_usd.as_of_date}}" cannot drift,
-- because it is re-rendered from canon_facts every time it is used, and
-- rendering fails loudly if a referenced fact is missing or stale.
-- ============================================================================

CREATE TABLE question_bank (
    id              SERIAL PRIMARY KEY,
    question        TEXT NOT NULL UNIQUE,
    answer_template TEXT NOT NULL,              -- contains {{field_key}} placeholders only; no raw numbers
    category        TEXT NOT NULL,
    is_public       BOOLEAN NOT NULL DEFAULT FALSE,
    last_reviewed   DATE,
    embedding       vector(1536),               -- for similarity match against incoming questions
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which canon_facts a question's answer_template depends on. Populated by the
-- app when a question is created (parsed from the template's {{...}} tokens),
-- and re-validated by the drift test.
CREATE TABLE question_bank_facts (
    question_id     INTEGER NOT NULL REFERENCES question_bank (id) ON DELETE CASCADE,
    field_key       TEXT NOT NULL REFERENCES canon_facts (field_key),
    PRIMARY KEY (question_id, field_key)
);

-- Which firms have asked a given question, and where — for the consistency
-- rule (same question from two funds gets the same answer from the same source).
CREATE TABLE question_bank_asked_by (
    id              BIGSERIAL PRIMARY KEY,
    question_id     INTEGER NOT NULL REFERENCES question_bank (id) ON DELETE CASCADE,
    investor_id     INTEGER NOT NULL REFERENCES investor_file (id),
    asked_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    thread_ref      TEXT
);

CREATE INDEX idx_question_bank_asked_by_question ON question_bank_asked_by (question_id);
CREATE INDEX idx_question_bank_asked_by_investor ON question_bank_asked_by (investor_id);

-- ============================================================================
-- ASSETS & RULES
-- Deck/dashboard/data-room locations, and the hard "never say / never send"
-- boundaries every agent must check before acting.
-- ============================================================================

CREATE TABLE assets (
    id              SERIAL PRIMARY KEY,
    asset_key       TEXT NOT NULL UNIQUE,
    asset_type      TEXT NOT NULL CHECK (asset_type IN ('deck', 'dashboard', 'data_room_folder', 'other')),
    location        TEXT NOT NULL,              -- URL or path
    description     TEXT,
    is_public       BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rules (
    id              SERIAL PRIMARY KEY,
    rule_key        TEXT NOT NULL UNIQUE,
    rule_type       TEXT NOT NULL CHECK (rule_type IN (
                        'email_allowlist', 'never_say', 'stop_condition', 'do_not_contact', 'other'
                    )),
    value           TEXT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- ACTIVITY LOG
-- Append-only. Every outbound, link granted, number quoted, escalation,
-- approval — everything logged, per the non-negotiable rules.
-- ============================================================================

CREATE TABLE activity_log (
    id              BIGSERIAL PRIMARY KEY,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor           TEXT NOT NULL,              -- agent name ('Scout', 'Inbox', ...) or 'founder'
    action_type     TEXT NOT NULL,              -- outbound_sent | outbound_drafted | link_granted | number_quoted | escalation | approval | thread_locked | other
    entity_type     TEXT,                       -- investor_file | question_bank | canon_facts | thread | data_room_link
    entity_id       TEXT,
    thread_ref      TEXT,
    details         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_activity_log_occurred_at ON activity_log (occurred_at);
CREATE INDEX idx_activity_log_actor ON activity_log (actor);
CREATE INDEX idx_activity_log_entity ON activity_log (entity_type, entity_id);

-- ============================================================================
-- STAGE 2 ADDITIONS -- inbox drafts + draft survival measurement
-- ============================================================================

-- Coarse, firm-level default seniority for the primary partner contact.
-- Per-message seniority (a firm can have contacts of more than one seniority)
-- is captured per-decision on drafts.sender_seniority below.
ALTER TABLE investor_file
    ADD COLUMN partner_seniority TEXT NOT NULL DEFAULT 'unknown'
        CHECK (partner_seniority IN ('partner', 'principal', 'associate', 'analyst', 'unknown'));

-- One row per Stage 2 inbox decision -- whether or not a draft was created.
-- This is the reviewable trail activity_log's free-form JSONB can't give us on
-- its own: the drafted text captured at creation time, what was actually sent,
-- and a computed survival score, all queryable together with a lifecycle status.
CREATE TABLE drafts (
    id                  BIGSERIAL PRIMARY KEY,
    gmail_thread_id     TEXT NOT NULL,
    gmail_message_id    TEXT NOT NULL,          -- inbound message this decision was made on
    gmail_draft_id      TEXT,                   -- set once create_draft succeeds; NULL if never drafted
    investor_id         INTEGER REFERENCES investor_file (id),
    sender_email        TEXT,
    sender_seniority    TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (sender_seniority IN ('partner', 'principal', 'associate', 'analyst', 'unknown')),
    classification      TEXT NOT NULL CHECK (classification IN (
                            'known_question_draft', 'unknown_question_escalate',
                            'legal_price_personal_escalate', 'meeting_request_flag',
                            'data_room_request_flag', 'thread_locked_skip', 'do_not_contact_skip'
                        )),
    question_id         INTEGER REFERENCES question_bank (id),
    match_score         NUMERIC(4,3),
    draft_text          TEXT,                   -- exact text placed in the Gmail draft body
    draft_created_at    TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'not_drafted' CHECK (status IN (
                            'not_drafted', 'drafted', 'sent_matched', 'sent_diverged', 'abandoned'
                        )),
    sent_message_id     TEXT,
    sent_text           TEXT,
    sent_at             TIMESTAMPTZ,
    survival_score      NUMERIC(5,4),
    survival_method     TEXT,
    measured_at         TIMESTAMPTZ,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_drafts_status ON drafts (status);
CREATE INDEX idx_drafts_thread ON drafts (gmail_thread_id);
CREATE UNIQUE INDEX idx_drafts_gmail_draft_id ON drafts (gmail_draft_id) WHERE gmail_draft_id IS NOT NULL;
CREATE UNIQUE INDEX idx_drafts_message_id ON drafts (gmail_message_id);

-- ============================================================================
-- SCOUT ADDITIONS -- fields from the one-page note template
-- (agents/SPECIALISTS.md #1 SCOUT) not already covered by investor_file.
-- ============================================================================

ALTER TABLE investor_file
    ADD COLUMN stage_fit          TEXT,  -- does the fund lead or follow at our stage
    ADD COLUMN portfolio_examples TEXT,  -- 2-3 relevant investments, with why relevant
    ADD COLUMN conflicts          TEXT,  -- competing portfolio companies
    ADD COLUMN why_them           TEXT,  -- two sentences, specific to us, not generic
    ADD COLUMN approved           BOOLEAN NOT NULL DEFAULT FALSE;  -- founder approved this target (per WORKFLOWS.md "New target identified" flow: Scout adds NOT APPROVED, founder approves or rejects before Outreach acts)

-- ============================================================================
-- DATA ROOM ADDITIONS (agents/SPECIALISTS.md #5 DATA ROOM)
-- ============================================================================

CREATE TABLE data_room_links (
    id                  BIGSERIAL PRIMARY KEY,
    investor_id         INTEGER NOT NULL REFERENCES investor_file (id),
    tier                TEXT NOT NULL CHECK (tier IN ('teaser', 'standard', 'full')),
    drive_folder_id     TEXT,               -- per-firm Drive folder holding this tier's files
    granted_by          TEXT NOT NULL DEFAULT 'founder',  -- full room access requires explicit founder approval per firm
    expiry_date         DATE,
    revoked_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_data_room_links_active ON data_room_links (investor_id) WHERE revoked_at IS NULL;

-- One row per file within a firm's data room -- each firm's copy of a file
-- is a SEPARATE Drive file (watermarked with that firm's name), never a
-- link shared across firms.
CREATE TABLE data_room_files (
    id                  BIGSERIAL PRIMARY KEY,
    link_id             BIGINT NOT NULL REFERENCES data_room_links (id),
    drive_file_id       TEXT NOT NULL UNIQUE,
    filename            TEXT NOT NULL,
    watermarked         BOOLEAN NOT NULL DEFAULT TRUE,
    share_url           TEXT,
    shared_with_email   TEXT,               -- restricted share target, not a public link -- this is what makes per-viewer tracking possible
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- View log -- who opened what, when. Populated from the Drive Activity API,
-- which can only attribute a view to a named identity when the file was
-- shared with that person's specific email (not "anyone with the link") --
-- another reason every share is per-firm and restricted, not a public URL.
CREATE TABLE data_room_views (
    id                  BIGSERIAL PRIMARY KEY,
    file_id             BIGINT NOT NULL REFERENCES data_room_files (id),
    viewer_email        TEXT,               -- NULL if Drive could not attribute the view to an identity
    viewed_at           TIMESTAMPTZ NOT NULL,
    flagged_unexpected  BOOLEAN NOT NULL DEFAULT FALSE,  -- viewer_email does not match shared_with_email -- link forwarded to an unissued party
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_data_room_views_file ON data_room_views (file_id);
CREATE INDEX idx_data_room_views_viewed_at ON data_room_views (viewed_at);

-- ============================================================================
-- OUTREACH ADDITIONS (agents/SPECIALISTS.md #2 OUTREACH)
-- ============================================================================

CREATE TABLE outreach_touches (
    id                  BIGSERIAL PRIMARY KEY,
    investor_id         INTEGER NOT NULL REFERENCES investor_file (id),
    touch_number        SMALLINT NOT NULL CHECK (touch_number IN (1, 2, 3)),  -- 1=first note, 2=day-4 follow-up, 3=day-11 follow-up; never a 4th
    template_capital_type TEXT NOT NULL,     -- which of the 4 templates was used
    gmail_draft_id      TEXT,
    gmail_message_id    TEXT,                -- set once actually sent
    draft_text          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'drafted' CHECK (status IN ('drafted', 'sent', 'abandoned')),
    drafted_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_outreach_touches_investor_touch ON outreach_touches (investor_id, touch_number);
CREATE INDEX idx_outreach_touches_status ON outreach_touches (status);
