"""RepMon core data models — Pydantic v2 throughout."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from repmon._time import now_utc


# ── Enums ─────────────────────────────────────────────────────────────────────


class DomainStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class MentionSource(str, Enum):
    GOOGLE = "google"
    YELP = "yelp"
    TRUSTPILOT = "trustpilot"
    RSS = "rss"
    REDDIT = "reddit"
    TWITTER = "twitter"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    URGENT = "urgent"


class AlertKind(str, Enum):
    BLOCKLIST_HIT = "blocklist_hit"
    DNS_ISSUE = "dns_issue"
    DMARC_SPIKE = "dmarc_spike"
    LOW_SCORE = "low_score"
    NEGATIVE_REVIEW = "negative_review"
    URGENT_MENTION = "urgent_mention"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ResponseStatus(str, Enum):
    NONE = "none"
    DRAFTED = "drafted"
    APPROVED = "approved"
    PUBLISHED = "published"
    SKIPPED = "skipped"


class WarmupStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class ScoreTrend(str, Enum):
    UP = "up"
    FLAT = "flat"
    DOWN = "down"


class DmarcPolicy(str, Enum):
    NONE = "none"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class MentionKind(str, Enum):
    REVIEW = "review"
    MENTION = "mention"
    COMPLAINT = "complaint"
    COMPLIMENT = "compliment"
    QUESTION = "question"
    SPAM = "spam"


# ── Records ───────────────────────────────────────────────────────────────────


class MonitoredDomain(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain: str
    status: DomainStatus = DomainStatus.ACTIVE
    display_name: str = ""
    sending_ip: Optional[str] = None
    dkim_selector: str = "google"
    operator_email: str = ""
    rep_score: float = 0.0
    deliverability_score: float = 0.0
    composite_score: float = 0.0
    score_trend: ScoreTrend = ScoreTrend.FLAT
    last_checked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class DnsSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    checked_at: datetime = Field(default_factory=now_utc)
    spf_record: Optional[str] = None
    spf_valid: bool = False
    dkim_record: Optional[str] = None
    dkim_valid: bool = False
    dmarc_record: Optional[str] = None
    dmarc_valid: bool = False
    dmarc_policy: DmarcPolicy = DmarcPolicy.NONE
    mx_records_json: str = "[]"
    issues_json: str = "[]"


class BlocklistResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    checked_at: datetime = Field(default_factory=now_utc)
    listed_count: int = 0
    checked_count: int = 0
    results_json: str = "[]"


class DmarcReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    report_id: str = ""
    org_name: str = ""
    date_begin: Optional[datetime] = None
    date_end: Optional[datetime] = None
    pass_count: int = 0
    fail_count: int = 0
    dkim_pass: int = 0
    dkim_fail: int = 0
    spf_pass: int = 0
    spf_fail: int = 0
    raw_xml_path: Optional[str] = None
    ingested_at: datetime = Field(default_factory=now_utc)


class DmarcRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    report_id: str
    source_ip: str
    count: int = 0
    disposition: str = ""
    dkim_result: str = ""
    spf_result: str = ""
    header_from: str = ""


class Mention(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    source: MentionSource
    external_id: str = ""
    author: str = ""
    rating: Optional[float] = None
    content: str = ""
    mention_kind: MentionKind = MentionKind.MENTION
    sentiment: Sentiment = Sentiment.NEUTRAL
    sentiment_score: float = 0.5
    url: str = ""
    published_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=now_utc)
    response_status: ResponseStatus = ResponseStatus.NONE
    draft_response: str = ""
    response_approval_token: Optional[str] = None
    response_published_at: Optional[datetime] = None


class AlertRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    kind: AlertKind
    severity: AlertSeverity
    message: str
    detail_json: str = "{}"
    status: AlertStatus = AlertStatus.NEW
    triggered_at: datetime = Field(default_factory=now_utc)
    resolved_at: Optional[datetime] = None


class WarmupPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    start_date: datetime = Field(default_factory=now_utc)
    target_daily_volume_json: str = "[]"
    guidance_md: str = ""
    current_day: int = 0
    status: WarmupStatus = WarmupStatus.ACTIVE
    created_at: datetime = Field(default_factory=now_utc)


class RawMentionIngest(BaseModel):
    """Inbound envelope before classification (mirrors SchedBot RawBookingRequest)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    domain_id: str
    source: MentionSource
    raw_payload_json: str = "{}"
    received_at: datetime = Field(default_factory=now_utc)
    processed: bool = False
    error: Optional[str] = None


class ClassificationResult(BaseModel):
    kind: MentionKind = MentionKind.MENTION
    sentiment: Sentiment = Sentiment.NEUTRAL
    sentiment_score: float = 0.5
    urgency: bool = False
    confidence: float = 0.0
    reasoning: str = ""
