"""Deterministic scoring — no LLM calls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from repmon.config.loader import RepMonConfig
from repmon.models import DmarcReport, DnsSnapshot, BlocklistResult, Mention, ScoreTrend, Sentiment


def compute_deliverability(
    dns: DnsSnapshot,
    bl: BlocklistResult,
    dmarc_window: list[DmarcReport],
) -> float:
    dns_score = 0.0
    if dns.spf_valid:
        dns_score += 15.0
    if dns.dkim_valid:
        dns_score += 15.0
    if dns.dmarc_valid:
        dns_score += 10.0

    checked = max(bl.checked_count, 1)
    listed_ratio = min(1.0, bl.listed_count / checked)
    blocklist_score = 35.0 - (listed_ratio * 35.0)
    blocklist_score = max(0.0, min(35.0, blocklist_score))

    total_pass = sum(r.pass_count for r in dmarc_window)
    total_fail = sum(r.fail_count for r in dmarc_window)
    denom = total_pass + total_fail
    if denom <= 0:
        dmarc_score = 0.0
    else:
        dmarc_score = (total_pass / denom) * 25.0

    total = dns_score + blocklist_score + dmarc_score
    return max(0.0, min(100.0, total))


def compute_reputation(
    mentions: list[Mention],
    *,
    window_days: int = 30,
    now: Optional[datetime] = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    recent: list[Mention] = []
    for m in mentions:
        ts = m.published_at or m.fetched_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            recent.append(m)

    if not recent:
        return 50.0

    rated = [m for m in recent if m.rating is not None]
    if rated:
        avg_rating = sum(float(m.rating) for m in rated) / len(rated)
        rating_score = (avg_rating / 5.0) * 60.0
    else:
        rating_score = 30.0

    pos = sum(
        1
        for m in recent
        if m.sentiment in (Sentiment.POSITIVE,)
    )
    total = len(recent)
    sentiment_score = (pos / total) * 40.0 if total else 0.0

    return max(0.0, min(100.0, rating_score + sentiment_score))


def dmarc_reports_in_window(
    reports: list[DmarcReport],
    *,
    window_days: int = 7,
    now: Optional[datetime] = None,
) -> list[DmarcReport]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    out: list[DmarcReport] = []
    for r in reports:
        start = r.date_begin or r.ingested_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start >= cutoff:
            out.append(r)
    return out


def compute_composite(
    deliverability: float,
    reputation: float,
    config: RepMonConfig,
    trailing_composite_average: Optional[float] = None,
) -> tuple[float, ScoreTrend]:
    w_d = config.scoring.deliverability_weight
    w_r = config.scoring.reputation_weight
    s = w_d + w_r
    w_d, w_r = w_d / s, w_r / s
    composite = w_d * deliverability + w_r * reputation
    composite = max(0.0, min(100.0, composite))

    if trailing_composite_average is None:
        return composite, ScoreTrend.FLAT
    delta = composite - trailing_composite_average
    if delta > 3.0:
        return composite, ScoreTrend.UP
    if delta < -3.0:
        return composite, ScoreTrend.DOWN
    return composite, ScoreTrend.FLAT


def trailing_composite_avg(history_rows: list[dict], *, days: int = 7) -> Optional[float]:
    """Average composite from score_history rows (SQLite row dicts)."""
    if not history_rows:
        return None
    vals = [float(r["composite_score"]) for r in history_rows[:days]]
    if not vals:
        return None
    return sum(vals) / len(vals)
