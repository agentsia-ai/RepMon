"""Create AlertRecord rows from monitoring signals."""

from __future__ import annotations

import json
import logging
from typing import Any

from repmon.crm.database import RepMonDatabase
from repmon.models import (
    AlertKind,
    AlertRecord,
    AlertSeverity,
    BlocklistResult,
    DnsSnapshot,
    Mention,
    Sentiment,
)

logger = logging.getLogger(__name__)


def _detail(obj: Any) -> str:
    return json.dumps(obj, default=str)


async def on_dns_issues(db: RepMonDatabase, domain_id: str, snap: DnsSnapshot) -> None:
    try:
        issues = json.loads(snap.issues_json or "[]")
    except json.JSONDecodeError:
        issues = []
    if not isinstance(issues, list):
        return
    for issue in issues:
        sev = AlertSeverity.CRITICAL
        if issue == "dmarc_policy_none_warning":
            sev = AlertSeverity.WARNING
        elif issue.endswith("_warning"):
            sev = AlertSeverity.WARNING
        msg = f"DNS issue: {issue}"
        await db.insert_alert(
            AlertRecord(
                domain_id=domain_id,
                kind=AlertKind.DNS_ISSUE,
                severity=sev,
                message=msg,
                detail_json=_detail({"issue": issue, "snapshot_id": snap.id}),
            )
        )


async def on_blocklist(db: RepMonDatabase, domain_id: str, result: BlocklistResult) -> None:
    try:
        rows = json.loads(result.results_json or "[]")
    except json.JSONDecodeError:
        rows = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("listed"):
            continue
        name = str(row.get("list_name") or "")
        critical = "spamhaus" in name.lower()
        await db.insert_alert(
            AlertRecord(
                domain_id=domain_id,
                kind=AlertKind.BLOCKLIST_HIT,
                severity=AlertSeverity.CRITICAL if critical else AlertSeverity.WARNING,
                message=f"Blocklist hit: {name}",
                detail_json=_detail(row),
            )
        )


async def on_sentiment(
    db: RepMonDatabase,
    mention: Mention,
    threshold: float,
) -> None:
    if mention.sentiment == Sentiment.URGENT or mention.sentiment_score < threshold:
        await db.insert_alert(
            AlertRecord(
                domain_id=mention.domain_id,
                kind=AlertKind.URGENT_MENTION
                if mention.sentiment == Sentiment.URGENT
                else AlertKind.NEGATIVE_REVIEW,
                severity=AlertSeverity.CRITICAL
                if mention.sentiment == Sentiment.URGENT
                else AlertSeverity.WARNING,
                message="Negative or urgent mention detected",
                detail_json=_detail(
                    {"mention_id": mention.id, "sentiment": mention.sentiment.value}
                ),
            )
        )
