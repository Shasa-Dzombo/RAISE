"""Deterministic first-note templates for the four capital types.

All company claims come from public canon facts or the founder-signed story
pack. This module only creates draft content; it never sends mail.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_lib import check_outbound_fact  # noqa: E402


def _v(facts, key):
    return check_outbound_fact(facts, key)


def _story(story, key):
    value = story.get(key)
    if not value:
        raise ValueError(
            "story_pack.{} is not founder-signed -- cannot draft a first note".format(key)
        )
    return value


def africa_focused_vc(fund, facts, story):
    company = _v(facts, "company_name")
    subject = "{} -- {} round, live in {}".format(
        company, _v(facts, "round_stage"), _v(facts, "markets_operating_in")
    )
    body = (
        "Hi {partner},\n\n"
        "{company} is {one_liner} We are at {arr} USD ARR, live in {markets}, "
        "growing {growth} month over month. {why_them}\n\n"
        "Raising a {stage} round -- deck attached. Open to a call if this is "
        "in your wheelhouse.\n\n"
        "Regards,\n{founder}"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        company=company,
        one_liner=_story(story, "one_liner"),
        arr=_v(facts, "arr_usd"),
        markets=_v(facts, "markets_operating_in"),
        growth=_v(facts, "mom_growth_rate_pct"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
        founder=_v(facts, "founder_name"),
    )
    return subject, body


def global_vc_africa_portfolio(fund, facts, story):
    company = _v(facts, "company_name")
    subject = "{} -- {} for African markets".format(company, _v(facts, "sector"))
    body = (
        "Hi {partner},\n\n"
        "Quick context: {company} is {one_liner} -- current ARR {arr} USD, "
        "live in {markets}. {why_them}\n\n"
        "Raising a {stage} round -- deck attached. Worth a conversation?\n\n"
        "Regards,\n{founder}"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        company=company,
        one_liner=_story(story, "one_liner"),
        arr=_v(facts, "arr_usd"),
        markets=_v(facts, "markets_operating_in"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
        founder=_v(facts, "founder_name"),
    )
    return subject, body


def dfi_impact(fund, facts, story):
    company = _v(facts, "company_name")
    subject = "{} -- {} outcomes in African markets".format(
        company, _v(facts, "sector")
    )
    body = (
        "Hi {partner},\n\n"
        "{company} is {one_liner} We operate across {markets} -- current ARR "
        "{arr} USD. {why_them}\n\n"
        "Raising a {stage} round to extend into {targeting}. Deck attached, "
        "happy to share farmer-level outcome data on a call.\n\n"
        "Regards,\n{founder}"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        company=company,
        one_liner=_story(story, "one_liner"),
        markets=_v(facts, "markets_operating_in"),
        arr=_v(facts, "arr_usd"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
        targeting=_v(facts, "markets_targeting"),
        founder=_v(facts, "founder_name"),
    )
    return subject, body


def local_angel_syndicate(fund, facts, story):
    company = _v(facts, "company_name")
    subject = "{} -- intro via {}".format(
        company, fund.get("warm_path") or "[warm intro needed]"
    )
    body = (
        "Hi {partner},\n\n"
        "{warm_path_line}{company} -- {one_liner} We have {arr} USD ARR, "
        "live in {markets}. {why_them}\n\n"
        "Raising a {stage} round -- deck attached. Would value your take.\n\n"
        "Regards,\n{founder}"
    ).format(
        partner=(fund.get("partner_name") or "there").split(" (")[0],
        warm_path_line=(
            "{} suggested I reach out. ".format(fund["warm_path"])
            if fund.get("warm_path")
            else ""
        ),
        company=company,
        one_liner=_story(story, "one_liner"),
        arr=_v(facts, "arr_usd"),
        markets=_v(facts, "markets_operating_in"),
        why_them=fund.get("why_them") or "",
        stage=_v(facts, "round_stage"),
        founder=_v(facts, "founder_name"),
    )
    return subject, body


TEMPLATES = {
    "africa_focused_vc": africa_focused_vc,
    "global_vc_africa_portfolio": global_vc_africa_portfolio,
    "dfi_impact": dfi_impact,
    "local_angel_syndicate": local_angel_syndicate,
}


def draft_first_note(fund, facts, story):
    template_fn = TEMPLATES.get(fund["capital_type"])
    if template_fn is None:
        raise ValueError("no template for capital_type={}".format(fund["capital_type"]))
    return template_fn(fund, facts, story)
