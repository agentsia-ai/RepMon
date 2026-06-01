"""High-level RepMon coordination."""

from __future__ import annotations

import logging
from typing import Any, Optional

from repmon import alerting
from repmon._time import now_utc
from repmon.ai.drafter import ResponseDrafter
from repmon.config.loader import APIKeys, RepMonConfig, format_review_signature
from repmon.crm.database import RepMonDatabase
from repmon.cross_engine import fetch_lead_domains, fetch_propgen_domains
from repmon.models import (
    Mention,
    MentionSource,
    MonitoredDomain,
    ResponseStatus,
    DomainStatus,
)
from repmon.scoring.engine import (
    compute_composite,
    compute_deliverability,
    compute_reputation,
    dmarc_reports_in_window,
    trailing_composite_avg,
)
from repmon.sources.blocklist_checker import check_domain as bl_check
from repmon.sources.dns_checker import check_dns
from repmon.sources.dmarc_parser import ingest_report_file
from repmon.sources.google_business import GoogleBusinessSource

logger = logging.getLogger(__name__)


def append_operator_signature(config: RepMonConfig, body: str) -> str:
    """Append operator sign-off to a customer-facing draft; never agent_name."""
    text = body.strip()
    sig = format_review_signature(config)
    if not sig:
        return text
    op = (config.operator_name or "").strip()
    if op and op in text:
        return text
    return f"{text}{sig}"


async def resolve_domain_id(db: RepMonDatabase, token: str) -> Optional[MonitoredDomain]:
    token = token.strip()
    d = await db.get_domain(token)
    if d:
        return d
    by_name = await db.find_domain_by_name(token)
    if by_name:
        return by_name
    prefix = await db.find_domain_id_prefix(token)
    if prefix:
        return await db.get_domain(prefix)
    return None


async def refresh_domain_scores(
    db: RepMonDatabase,
    config: RepMonConfig,
    domain: MonitoredDomain,
) -> MonitoredDomain:
    dns = await check_dns(domain.id, domain.domain, config.domain_health.dkim_selectors)
    await db.insert_dns_snapshot(dns)
    bl = await bl_check(domain.id, domain.domain, domain.sending_ip, config)
    await db.insert_blocklist_result(bl)
    reports = await db.list_dmarc_reports(domain.id, limit=500)
    window = dmarc_reports_in_window(reports, window_days=7)
    dlv = compute_deliverability(dns, bl, window)
    mentions = await db.list_mentions(domain_id=domain.id, limit=500)
    rep = compute_reputation(mentions)
    hist = await db.list_score_history(domain.id, limit=14)
    trail = trailing_composite_avg(hist, days=7)
    comp, trend = compute_composite(dlv, rep, config, trail)
    domain.deliverability_score = dlv
    domain.rep_score = rep
    domain.composite_score = comp
    domain.score_trend = trend
    domain.last_checked_at = now_utc()
    await db.update_domain(domain)
    await db.insert_score_snapshot(domain.id, comp, rep, dlv)
    await alerting.on_dns_issues(db, domain.id, dns)
    if bl.listed_count > 0 and config.monitoring.blocklist_alert_on_any:
        await alerting.on_blocklist(db, domain.id, bl)
    return domain


async def add_domain(
    db: RepMonDatabase,
    config: RepMonConfig,
    fqdn: str,
) -> MonitoredDomain:
    existing = await db.find_domain_by_name(fqdn)
    if existing:
        return await refresh_domain_scores(db, config, existing)
    d = MonitoredDomain(
        domain=fqdn.lower().strip(),
        display_name=fqdn,
        operator_email=config.operator_email or "",
        dkim_selector=config.domain_health.dkim_selectors[0]
        if config.domain_health.dkim_selectors
        else "google",
        status=DomainStatus.ACTIVE,
    )
    await db.insert_domain(d)
    return await refresh_domain_scores(db, config, d)


async def draft_response_for_mention(
    db: RepMonDatabase,
    config: RepMonConfig,
    keys: APIKeys,
    mention_id: str,
    drafter_cls: type[ResponseDrafter],
) -> Mention:
    m = await db.get_mention(mention_id)
    if not m:
        raise ValueError("mention not found")
    dom = await db.get_domain(m.domain_id)
    if not dom:
        raise ValueError("domain not found")
    drafter = drafter_cls(config, keys)
    if m.source == MentionSource.GOOGLE and m.rating is not None:
        subj, body = await drafter.draft_review_response(dom, m)
    else:
        subj, body = await drafter.draft_mention_response(dom, m)
    text = body if not subj else f"{subj}\n\n{body}"
    m.draft_response = append_operator_signature(config, text)
    m.response_status = ResponseStatus.DRAFTED
    await db.upsert_mention(m)
    return m


async def approve_response(db: RepMonDatabase, mention_id: str) -> tuple[bool, Optional[str]]:
    return await db.approve_mention_response(mention_id)


async def publish_response(
    db: RepMonDatabase,
    config: RepMonConfig,
    keys: APIKeys,
    mention_id: str,
    approval_token: str,
) -> bool:
    # RepMon does not send outbound email — only stages drafts and publishes
    # operator-approved replies to platforms (e.g. Google Business) after approval.
    if config.outreach.auto_send:
        raise ValueError("outreach.auto_send must remain false — publishing requires human approval")
    if config.outreach.require_approval and not approval_token.strip():
        raise ValueError("approval_token required when outreach.require_approval is true")
    m = await db.get_mention(mention_id)
    if not m:
        raise ValueError("mention not found")
    dom = await db.get_domain(m.domain_id)
    if not dom:
        raise ValueError("domain not found")
    if m.response_status != ResponseStatus.APPROVED:
        raise ValueError("mention must be APPROVED before publish")
    if m.response_approval_token != approval_token.strip():
        raise ValueError("approval_token mismatch")
    if m.source == MentionSource.GOOGLE:
        g = GoogleBusinessSource(config, keys)
        await g.publish_reply(dom, m.external_id, m.draft_response)
    else:
        logger.info("publish_response: platform stub for %s", m.source.value)
    ok = await db.mark_mention_published(mention_id, approval_token.strip())
    return ok


async def dashboard_summary(db: RepMonDatabase) -> list[dict[str, Any]]:
    rows = []
    for d in await db.list_domains(limit=500):
        rows.append(d.model_dump(mode="json"))
    return rows


async def cross_engine_suggested_domains(config: RepMonConfig) -> list[str]:
    a = await fetch_lead_domains(config)
    b = await fetch_propgen_domains(config)
    return sorted(set(a) | set(b))
