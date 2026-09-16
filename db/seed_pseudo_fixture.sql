-- OPTIONAL, PSEUDO TEST DATA ONLY -- do not run this against a real deployment.
--
-- Loads the fictional Mazao Analytics figures from identity/USER.md into
-- canon_facts, so drift_test.py can be exercised against realistic values
-- instead of an all-NULL fact sheet. Every value here matches USER.md exactly
-- (per the consistency rule) and is clearly fabricated -- do not copy these
-- numbers into real outbound under any circumstance.
--
-- Usage:
--   python -c "import psycopg, os, pathlib; from dotenv import load_dotenv; \
--     load_dotenv('.env'); \
--     psycopg.connect(os.environ['DATABASE_URL'], autocommit=True).execute(pathlib.Path('db/seed_pseudo_fixture.sql').read_text())"

UPDATE canon_facts SET
    value = '"KES and UGX (blended); reported in USD at prevailing spot for investor reporting"',
    as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'currency_of_revenue';

UPDATE canon_facts SET
    value = '"Revenue collected in KES and UGX; costs largely KES with some USD-denominated cloud and infra spend. No hedging in place; FX risk is monitor-only at this stage."',
    as_of_date = '2026-08-31', source = 'Founder finance notes (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'fx_exposure_notes';

UPDATE canon_facts SET
    value = '"Kenya 72%, Uganda 28% (trailing 3 months)"',
    as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'revenue_split_by_market';

UPDATE canon_facts SET
    value = '"Kenya: registered as a digital marketplace under the Data Protection Act, ODPC registration on file. Uganda: no sector-specific licence required for the current transaction-facilitation model; payments run through a licensed PSP partner."',
    as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'regulatory_licences_by_market';

UPDATE canon_facts SET
    value = '"Kenya (private limited company)"',
    as_of_date = '2026-08-31', source = 'Certificate of incorporation (pseudo test data)', refresh_by = '2027-08-31'
WHERE field_key = 'incorporation_jurisdiction';

UPDATE canon_facts SET
    value = '"Nairobi, Kenya"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2027-08-31'
WHERE field_key = 'hq_jurisdiction';

UPDATE canon_facts SET
    value = '"A Delaware C-Corp flip is under discussion with counsel for this round; not yet executed."',
    as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'planned_flip';

UPDATE canon_facts SET
    value = '"Kenya, Uganda"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'markets_operating_in';

UPDATE canon_facts SET
    value = '"Tanzania, Rwanda"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'markets_targeting';

UPDATE canon_facts SET
    value = '"Seed"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-12-15'
WHERE field_key = 'round_stage';

UPDATE canon_facts SET
    value = '1500000',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-12-15'
WHERE field_key = 'round_amount_target';

UPDATE canon_facts SET
    value = '"USD"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-12-15'
WHERE field_key = 'round_currency';

UPDATE canon_facts SET
    value = '"SAFE"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-12-15'
WHERE field_key = 'round_instrument';

UPDATE canon_facts SET
    value = '"2026-12-15"',
    as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-12-15'
WHERE field_key = 'round_target_close_date';

UPDATE canon_facts SET
    value = '180000',
    as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'arr_usd';

UPDATE canon_facts SET
    value = '15000',
    as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'mrr_usd';

UPDATE canon_facts SET
    value = '7',
    as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'runway_months';

UPDATE canon_facts SET
    value = '18',
    as_of_date = '2026-08-31', source = 'Founder, headcount roster (pseudo test data)', refresh_by = '2026-11-30'
WHERE field_key = 'headcount';

-- Fields added when the question bank was expanded toward 40 questions.

UPDATE canon_facts SET value = '4200', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'monthly_burn_usd';
UPDATE canon_facts SET value = '108000', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'cash_balance_usd';
UPDATE canon_facts SET value = '"58%"', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'gross_margin_pct';
UPDATE canon_facts SET value = '"11%"', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'mom_growth_rate_pct';
UPDATE canon_facts SET value = '"3.2%"', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'churn_rate_pct';
UPDATE canon_facts SET value = '"104%"', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'net_revenue_retention_pct';
UPDATE canon_facts SET value = '9', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'cac_usd';
UPDATE canon_facts SET value = '5', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'payback_period_months';
UPDATE canon_facts SET value = '3400', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'paying_customers_count';
UPDATE canon_facts SET value = '"We charge buyers a 3% transaction fee on completed trades facilitated through the platform; farmers pay nothing to list or transact."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'pricing_model_summary';
UPDATE canon_facts SET value = '"No outstanding debt. The company has not taken on any loans or convertible debt instruments."', as_of_date = '2026-08-31', source = 'Founder finance notes (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'outstanding_debt_summary';
UPDATE canon_facts SET value = '"250,000 USD committed by two Nairobi-based angels (pseudo)."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'committed_to_date_usd';
UPDATE canon_facts SET value = '"Product and engineering 40%; Tanzania and Rwanda market expansion 30%; buyer-side payments working capital 20%; team 10%."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'use_of_funds_breakdown';
UPDATE canon_facts SET value = '"Launch in Tanzania (Q1 2027), cross 5,000 paying customers, and close a licensed-PSP integration in Rwanda before final close."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'round_milestones_before_close';
UPDATE canon_facts SET value = '"Both existing angel investors have indicated intent to participate pro-rata; not yet formally committed."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'follow_on_participation_notes';

UPDATE canon_facts SET value = '"Amara Osei (CEO, pseudo) -- 8 years in East African fintech and payments; Kwame Adjei (CTO, pseudo) -- ex-mobile money infrastructure engineer."', as_of_date = '2026-08-31', source = 'Founder bios (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'founders_summary';
UPDATE canon_facts SET value = '"Founding team has combined 14 years building payments and marketplace infrastructure for smallholder and informal-sector commerce in East Africa."', as_of_date = '2026-08-31', source = 'Founder bios (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'team_domain_experience';
UPDATE canon_facts SET value = '"CTO is the sole engineer with deep knowledge of the payments integration layer; a senior backend hire is budgeted in this round to reduce that concentration."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'key_person_risk_notes';
UPDATE canon_facts SET value = '"Plan to add 6 roles: 2 backend engineers, 1 country lead (Tanzania), 1 country lead (Rwanda), 1 finance/ops hire, 1 customer support lead."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'hiring_plan_next_12mo';
UPDATE canon_facts SET value = '"Mazao Analytics gives smallholder farmers real-time crop pricing and matches them directly with vetted buyers, over SMS for feature-phone users and a lightweight app for smartphone users."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'product_summary';
UPDATE canon_facts SET value = '"3,400 paying customers across Kenya and Uganda, 11% month-over-month growth, and 180,000 USD ARR as of the last close of books."', as_of_date = '2026-08-31', source = 'Mazao Analytics management accounts (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'traction_summary';
UPDATE canon_facts SET value = '"Field agent network signs up farmer cooperatives directly; buyer acquisition runs through existing grain-trader associations in each market."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'gtm_strategy_summary';
UPDATE canon_facts SET value = '"SMS gateway provider (pseudo), Python/Django backend, Postgres, React Native app, integrated with a licensed mobile-money PSP per market."', as_of_date = '2026-08-31', source = 'Founder and engineering notes (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'tech_stack_summary';
UPDATE canon_facts SET value = '"No patents filed. Defensibility is the field-agent relationship network and the pricing dataset accumulated across two markets, not IP."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'ip_defensibility_notes';

UPDATE canon_facts SET value = '"Estimated 2.1B USD in annual smallholder crop transactions across Kenya, Uganda, Tanzania, and Rwanda combined (pseudo estimate, methodology on file)."', as_of_date = '2026-08-31', source = 'Founder market sizing notes (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'tam_summary';
UPDATE canon_facts SET value = '"Primary competitors are informal broker networks and one regional app-based competitor (pseudo, unnamed); differentiation is the SMS-first channel reaching feature-phone farmers the app-only competitor cannot."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'competitive_landscape_summary';
UPDATE canon_facts SET value = '"Field-agent trust networks and buyer-side PSP integrations take 6-9 months to build per market, which is the primary barrier to new entrants."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'barriers_to_entry_summary';
UPDATE canon_facts SET value = '"Compliant with the Kenyan Data Protection Act (ODPC registration on file); Uganda data handling runs through the licensed PSP partner compliance program."', as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'data_protection_compliance_summary';
UPDATE canon_facts SET value = '"Tanzania and Rwanda both require a local PSP partnership for payment facilitation; neither requires a standalone marketplace licence at current transaction volumes."', as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'licences_required_for_target_markets';
UPDATE canon_facts SET value = '"No pending regulatory changes identified in any current or target market as of this review."', as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'pending_regulatory_changes_notes';
UPDATE canon_facts SET value = '"Two Nairobi-based angel investors, 250,000 USD combined, invested via SAFE in the current round (pseudo, names withheld pending consent)."', as_of_date = '2026-08-31', source = 'Founder (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'existing_investors_summary';
UPDATE canon_facts SET value = '"No outstanding litigation or known legal risk as of this review."', as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2026-11-30' WHERE field_key = 'litigation_legal_risk_notes';
UPDATE canon_facts SET value = '"IP assignment agreements are signed and on file for all founders and employees."', as_of_date = '2026-08-31', source = 'Founder and counsel notes (pseudo test data)', refresh_by = '2027-08-31' WHERE field_key = 'ip_assignment_status';
