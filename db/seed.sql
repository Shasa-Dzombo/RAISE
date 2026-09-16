-- RAISE -- Stage 1 seed data.
--
-- Seeds the required field_keys and a 40-question starter bank so the drift
-- test has real coverage to run against. No company facts are invented --
-- every canon_facts.value below is NULL on purpose. drift_test.py is expected
-- to flag all 40 questions as MISSING until real canon facts are loaded
-- (see identity/USER.md and the pseudo fixture at db/seed_pseudo_fixture.sql
-- for a fictional dataset that exercises the full pipeline in the meantime).
--
-- Safe to re-run: canon_facts is keyed on field_key, question_bank on
-- question text, both via ON CONFLICT DO NOTHING.

-- ============================================================================
-- CANON FACTS -- required from day one
-- ============================================================================

-- Africa-specific fields required from day one (currency/FX, revenue split by
-- market, regulatory licences, domicile/flip), plus the baseline financial,
-- team, product, market, legal, and round-mechanics fields a first-round
-- diligence pass asks for.

INSERT INTO canon_facts (field_key, field_label, category, agent_quotable) VALUES
    ('currency_of_revenue',        'Currency of revenue',                     'fx',          TRUE),
    ('fx_exposure_notes',          'FX exposure notes',                       'fx',          TRUE),
    ('revenue_split_by_market',    'Revenue split by market',                 'financials',  TRUE),
    ('regulatory_licences_by_market', 'Regulatory licences held, by market',  'regulatory',  TRUE),
    ('incorporation_jurisdiction', 'Incorporation jurisdiction',              'domicile',    TRUE),
    ('hq_jurisdiction',            'HQ jurisdiction',                         'domicile',    TRUE),
    ('planned_flip',               'Planned corporate flip (if any)',         'domicile',    TRUE),
    ('markets_operating_in',       'Markets currently operating in',          'markets',     TRUE),
    ('markets_targeting',          'Markets being targeted',                  'markets',     TRUE),
    ('round_stage',                'Round stage',                             'round',       TRUE),
    ('round_amount_target',        'Round amount being raised',               'round',       TRUE),
    ('round_currency',             'Round currency',                          'round',       TRUE),
    ('round_instrument',           'Round instrument (SAFE / equity / note)', 'round',       TRUE),
    ('round_target_close_date',    'Target close date',                       'round',       TRUE),
    ('arr_usd',                    'ARR (USD)',                               'financials',  TRUE),
    ('mrr_usd',                    'MRR (USD)',                               'financials',  TRUE),
    ('runway_months',              'Runway (months)',                         'financials',  TRUE),
    ('headcount',                  'Headcount',                               'team',        TRUE),

    ('monthly_burn_usd',              'Monthly burn (USD)',                       'financials', TRUE),
    ('cash_balance_usd',              'Cash balance today (USD)',                 'financials', TRUE),
    ('gross_margin_pct',              'Gross margin',                             'financials', TRUE),
    ('mom_growth_rate_pct',           'Month-over-month growth rate',             'financials', TRUE),
    ('churn_rate_pct',                'Monthly churn rate',                       'financials', TRUE),
    ('net_revenue_retention_pct',     'Net revenue retention',                    'financials', TRUE),
    ('cac_usd',                       'Blended customer acquisition cost (USD)',  'financials', TRUE),
    ('payback_period_months',         'CAC payback period (months)',              'financials', TRUE),
    ('paying_customers_count',        'Paying customers, current count',          'financials', TRUE),
    ('pricing_model_summary',         'Pricing model / take rate summary',        'financials', TRUE),
    ('outstanding_debt_summary',      'Outstanding debt summary',                 'financials', TRUE),
    ('committed_to_date_usd',         'Amount committed to this round to date',   'round',      TRUE),
    ('use_of_funds_breakdown',        'Use of funds, by category',                'round',      TRUE),
    ('round_milestones_before_close', 'Key milestones before close',              'round',      TRUE),
    ('follow_on_participation_notes', 'Existing-investor follow-on participation','round',      TRUE),

    ('founders_summary',            'Founders and backgrounds',                'team',      TRUE),
    ('team_domain_experience',      'Team domain experience',                  'team',      TRUE),
    ('key_person_risk_notes',       'Key-person risk notes',                   'team',      TRUE),
    ('hiring_plan_next_12mo',       'Hiring plan, next 12 months',              'team',      TRUE),

    ('product_summary',             'Product summary',                          'product',   TRUE),
    ('traction_summary',            'Traction to date',                         'product',   TRUE),
    ('gtm_strategy_summary',        'Go-to-market strategy',                    'product',   TRUE),
    ('tech_stack_summary',          'Technology stack summary',                 'product',   TRUE),
    ('ip_defensibility_notes',      'IP / defensibility notes',                 'product',   TRUE),

    ('tam_summary',                       'Total addressable market summary',    'markets',   TRUE),
    ('competitive_landscape_summary',     'Competitive landscape summary',       'markets',   TRUE),
    ('barriers_to_entry_summary',         'Barriers to entry summary',           'markets',   TRUE),

    ('data_protection_compliance_summary', 'Data protection compliance, by market',      'regulatory', TRUE),
    ('licences_required_for_target_markets', 'Licences required for target markets',     'regulatory', TRUE),
    ('pending_regulatory_changes_notes',   'Pending regulatory changes',                 'regulatory', TRUE),

    ('existing_investors_summary',  'Existing investors and amounts',           'legal',     TRUE),
    ('litigation_legal_risk_notes', 'Outstanding litigation / legal risk',      'legal',     TRUE),
    ('ip_assignment_status',        'IP assignment status across team',         'legal',     TRUE)
ON CONFLICT (field_key) DO NOTHING;

-- ============================================================================
-- QUESTION BANK -- 40 questions, templates reference field_keys only.
-- No numbers are hardcoded here, so nothing below can go stale on its own; it
-- fails to render (and drift_test.py flags it) until canon_facts is filled in.
-- ============================================================================

INSERT INTO question_bank (question, answer_template, category, is_public) VALUES
    ('What currency is your revenue in, and what is your FX exposure?',
     'Our revenue is denominated in {{currency_of_revenue}}. {{fx_exposure_notes}}',
     'fx', TRUE),
    ('What is your revenue split by market?',
     '{{revenue_split_by_market}}',
     'financials', FALSE),
    ('What regulatory licences do you hold, and in which markets?',
     '{{regulatory_licences_by_market}}',
     'regulatory', FALSE),
    ('Where is the company incorporated, and is a flip planned?',
     'The company is incorporated in {{incorporation_jurisdiction}}, with HQ in {{hq_jurisdiction}}. {{planned_flip}}',
     'domicile', FALSE),
    ('What markets are you operating in today vs. targeting?',
     'We currently operate in {{markets_operating_in}} and are targeting {{markets_targeting}}.',
     'markets', TRUE),
    ('What stage and how much are you raising, and what will it be used for?',
     'We are raising a {{round_stage}} round of {{round_amount_target}} {{round_currency}} via {{round_instrument}}, targeting close by {{round_target_close_date}}. Use of funds: {{use_of_funds_breakdown}}',
     'round', TRUE),
    ('What is your current ARR and MRR?',
     'Current ARR is {{arr_usd}} USD (MRR {{mrr_usd}} USD).',
     'financials', FALSE),
    ('What is your current runway?',
     'Runway is {{runway_months}} months as of the last close of books.',
     'financials', FALSE),
    ('What is your current headcount?',
     'Current headcount is {{headcount}}.',
     'team', TRUE)
ON CONFLICT (question) DO NOTHING;

INSERT INTO question_bank (question, answer_template, category, is_public) VALUES
    ('What is your current monthly burn rate?',
     'Monthly burn is {{monthly_burn_usd}} USD as of the last close of books.',
     'financials', FALSE),
    ('What is your cash balance today, and how does that compare to your burn?',
     'Current cash balance is {{cash_balance_usd}} USD, against monthly burn of {{monthly_burn_usd}} USD, giving {{runway_months}} months of runway.',
     'financials', FALSE),
    ('What is your gross margin?',
     'Gross margin is {{gross_margin_pct}}.',
     'financials', FALSE),
    ('What is your month-over-month growth rate?',
     'Month-over-month growth is {{mom_growth_rate_pct}}, trailing three months.',
     'financials', FALSE),
    ('What is your churn rate?',
     'Monthly churn is {{churn_rate_pct}}.',
     'financials', FALSE),
    ('What is your net revenue retention?',
     'Net revenue retention is {{net_revenue_retention_pct}}.',
     'financials', FALSE),
    ('What is your customer acquisition cost (CAC)?',
     'Blended CAC is {{cac_usd}} USD.',
     'financials', FALSE),
    ('What is your CAC payback period?',
     'CAC payback period is {{payback_period_months}} months.',
     'financials', FALSE),
    ('How many paying customers do you have?',
     'We have {{paying_customers_count}} paying customers as of the last close of books.',
     'financials', FALSE),
    ('What is your pricing model or take rate?',
     '{{pricing_model_summary}}',
     'financials', FALSE),
    ('Do you have any outstanding debt?',
     '{{outstanding_debt_summary}}',
     'financials', FALSE),
    ('How much has been committed to this round so far, and by whom?',
     '{{committed_to_date_usd}}',
     'round', FALSE)
ON CONFLICT (question) DO NOTHING;

INSERT INTO question_bank (question, answer_template, category, is_public) VALUES
    ('Who are the founders, and what is their background?',
     '{{founders_summary}}',
     'team', TRUE),
    ('What relevant domain experience does the team bring?',
     '{{team_domain_experience}}',
     'team', TRUE),
    ('Is there key-person risk on the team?',
     '{{key_person_risk_notes}}',
     'team', FALSE),
    ('What is your hiring plan for the next 12 months?',
     '{{hiring_plan_next_12mo}}',
     'team', FALSE),
    ('What does your product do, and how does it work?',
     '{{product_summary}}',
     'product', TRUE),
    ('What traction have you achieved to date?',
     '{{traction_summary}}',
     'product', FALSE),
    ('What is your go-to-market strategy?',
     '{{gtm_strategy_summary}}',
     'product', FALSE),
    ('What is your technology stack?',
     '{{tech_stack_summary}}',
     'product', FALSE),
    ('Do you have any defensible IP or patents?',
     '{{ip_defensibility_notes}}',
     'product', FALSE),
    ('How big is your total addressable market?',
     '{{tam_summary}}',
     'markets', TRUE),
    ('Who are your main competitors, and how do you differentiate?',
     '{{competitive_landscape_summary}}',
     'markets', FALSE)
ON CONFLICT (question) DO NOTHING;

INSERT INTO question_bank (question, answer_template, category, is_public) VALUES
    ('What are the barriers to entry in this market?',
     '{{barriers_to_entry_summary}}',
     'markets', FALSE),
    ('Are you compliant with data protection regulations in each market you operate in?',
     '{{data_protection_compliance_summary}}',
     'regulatory', FALSE),
    ('What additional licences, if any, are required for the markets you are targeting next?',
     '{{licences_required_for_target_markets}}',
     'regulatory', FALSE),
    ('Are there any pending regulatory changes that could affect your business model?',
     '{{pending_regulatory_changes_notes}}',
     'regulatory', FALSE),
    ('Who are your existing investors, and what have they invested?',
     '{{existing_investors_summary}}',
     'legal', FALSE),
    ('Is there any outstanding litigation or legal risk?',
     '{{litigation_legal_risk_notes}}',
     'legal', FALSE),
    ('Is IP assignment clean across all founders and employees?',
     '{{ip_assignment_status}}',
     'legal', FALSE),
    ('What are the key milestones before close?',
     '{{round_milestones_before_close}}',
     'round', FALSE),
    ('Are existing investors participating pro-rata (follow-on) in this round?',
     '{{follow_on_participation_notes}}',
     'round', FALSE)
ON CONFLICT (question) DO NOTHING;

-- Link every question to the field_keys its template references.
INSERT INTO question_bank_facts (question_id, field_key)
SELECT qb.id, f.fk
FROM question_bank qb
CROSS JOIN LATERAL regexp_matches(qb.answer_template, '\{\{([a-z0-9_]+)\}\}', 'g') AS m(fk_arr)
CROSS JOIN LATERAL (SELECT m.fk_arr[1] AS fk) AS f(fk)
ON CONFLICT DO NOTHING;
