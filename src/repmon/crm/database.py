"""Async SQLite CRM for RepMon."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import aiosqlite

from repmon._time import now_utc, parse_iso, to_iso
from repmon.models import (
    AlertKind,
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    BlocklistResult,
    DnsSnapshot,
    DmarcPolicy,
    DmarcRecord,
    DmarcReport,
    DomainStatus,
    Mention,
    MentionKind,
    MentionSource,
    MonitoredDomain,
    RawMentionIngest,
    ResponseStatus,
    ScoreTrend,
    Sentiment,
    WarmupPlan,
    WarmupStatus,
)

logger = logging.getLogger(__name__)


class RepMonDatabase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitored_domains (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    sending_ip TEXT,
                    dkim_selector TEXT DEFAULT 'google',
                    operator_email TEXT DEFAULT '',
                    rep_score REAL DEFAULT 0,
                    deliverability_score REAL DEFAULT 0,
                    composite_score REAL DEFAULT 0,
                    score_trend TEXT DEFAULT 'flat',
                    last_checked_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_domains_status ON monitored_domains(status);

                CREATE TABLE IF NOT EXISTS dns_snapshots (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    spf_record TEXT,
                    spf_valid INTEGER NOT NULL,
                    dkim_record TEXT,
                    dkim_valid INTEGER NOT NULL,
                    dmarc_record TEXT,
                    dmarc_valid INTEGER NOT NULL,
                    dmarc_policy TEXT DEFAULT 'none',
                    mx_records_json TEXT DEFAULT '[]',
                    issues_json TEXT DEFAULT '[]',
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );
                CREATE INDEX IF NOT EXISTS idx_dns_domain ON dns_snapshots(domain_id);

                CREATE TABLE IF NOT EXISTS blocklist_results (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    listed_count INTEGER DEFAULT 0,
                    checked_count INTEGER DEFAULT 0,
                    results_json TEXT DEFAULT '[]',
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );
                CREATE INDEX IF NOT EXISTS idx_bl_domain ON blocklist_results(domain_id);

                CREATE TABLE IF NOT EXISTS dmarc_reports (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    report_id TEXT DEFAULT '',
                    org_name TEXT DEFAULT '',
                    date_begin TEXT,
                    date_end TEXT,
                    pass_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    dkim_pass INTEGER DEFAULT 0,
                    dkim_fail INTEGER DEFAULT 0,
                    spf_pass INTEGER DEFAULT 0,
                    spf_fail INTEGER DEFAULT 0,
                    raw_xml_path TEXT,
                    ingested_at TEXT NOT NULL,
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );
                CREATE INDEX IF NOT EXISTS idx_dmarc_domain ON dmarc_reports(domain_id);

                CREATE TABLE IF NOT EXISTS dmarc_records (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    source_ip TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    disposition TEXT DEFAULT '',
                    dkim_result TEXT DEFAULT '',
                    spf_result TEXT DEFAULT '',
                    header_from TEXT DEFAULT '',
                    FOREIGN KEY (report_id) REFERENCES dmarc_reports(id)
                );

                CREATE TABLE IF NOT EXISTS mentions (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    external_id TEXT DEFAULT '',
                    author TEXT DEFAULT '',
                    rating REAL,
                    content TEXT DEFAULT '',
                    mention_kind TEXT DEFAULT 'mention',
                    sentiment TEXT DEFAULT 'neutral',
                    sentiment_score REAL DEFAULT 0.5,
                    url TEXT DEFAULT '',
                    published_at TEXT,
                    fetched_at TEXT NOT NULL,
                    response_status TEXT DEFAULT 'none',
                    draft_response TEXT DEFAULT '',
                    response_approval_token TEXT,
                    response_published_at TEXT,
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );
                CREATE INDEX IF NOT EXISTS idx_mentions_domain ON mentions(domain_id);

                CREATE TABLE IF NOT EXISTS alert_records (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail_json TEXT DEFAULT '{}',
                    status TEXT NOT NULL,
                    triggered_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_domain ON alert_records(domain_id);

                CREATE TABLE IF NOT EXISTS warmup_plans (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL UNIQUE,
                    start_date TEXT NOT NULL,
                    target_daily_volume_json TEXT DEFAULT '[]',
                    guidance_md TEXT DEFAULT '',
                    current_day INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );

                CREATE TABLE IF NOT EXISTS raw_mention_ingest (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    raw_payload_json TEXT DEFAULT '{}',
                    received_at TEXT NOT NULL,
                    processed INTEGER DEFAULT 0,
                    error TEXT,
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );

                CREATE TABLE IF NOT EXISTS score_history (
                    id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    composite_score REAL NOT NULL,
                    rep_score REAL NOT NULL,
                    deliverability_score REAL NOT NULL,
                    FOREIGN KEY (domain_id) REFERENCES monitored_domains(id)
                );
                CREATE INDEX IF NOT EXISTS idx_scorehist_domain ON score_history(domain_id);
                """
            )
            await db.commit()
        logger.info("RepMon database ready: %s", self.db_path)

    # --- domains ---

    async def insert_domain(self, d: MonitoredDomain) -> MonitoredDomain:
        d.updated_at = now_utc()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO monitored_domains (
                    id, domain, status, display_name, sending_ip, dkim_selector,
                    operator_email, rep_score, deliverability_score, composite_score,
                    score_trend, last_checked_at, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    d.id,
                    d.domain.lower().strip(),
                    d.status.value,
                    d.display_name,
                    d.sending_ip,
                    d.dkim_selector,
                    d.operator_email,
                    d.rep_score,
                    d.deliverability_score,
                    d.composite_score,
                    d.score_trend.value,
                    to_iso(d.last_checked_at),
                    to_iso(d.created_at),
                    to_iso(d.updated_at),
                ),
            )
            await db.commit()
        return d

    async def get_domain(self, domain_id: str) -> Optional[MonitoredDomain]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM monitored_domains WHERE id = ?", (domain_id,)
            ) as cur:
                row = await cur.fetchone()
        return _row_to_domain(row) if row else None

    async def find_domain_by_name(self, domain: str) -> Optional[MonitoredDomain]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM monitored_domains WHERE domain = ?",
                (domain.lower().strip(),),
            ) as cur:
                row = await cur.fetchone()
        return _row_to_domain(row) if row else None

    async def find_domain_id_prefix(self, prefix: str) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id FROM monitored_domains WHERE id LIKE ? LIMIT 2",
                (f"{prefix}%",),
            ) as cur:
                rows = await cur.fetchall()
        if len(rows) == 1:
            return str(rows[0][0])
        return None

    async def insert_score_snapshot(
        self,
        domain_id: str,
        composite: float,
        rep: float,
        deliverability: float,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO score_history
                  (id, domain_id, recorded_at, composite_score, rep_score, deliverability_score)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    str(uuid4()),
                    domain_id,
                    to_iso(now_utc()),
                    composite,
                    rep,
                    deliverability,
                ),
            )
            await db.commit()

    async def list_score_history(
        self, domain_id: str, limit: int = 90
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM score_history WHERE domain_id = ? "
                "ORDER BY recorded_at DESC LIMIT ?",
                (domain_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def update_domain(self, d: MonitoredDomain) -> None:
        d.updated_at = now_utc()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE monitored_domains SET
                    status=?, display_name=?, sending_ip=?, dkim_selector=?,
                    operator_email=?, rep_score=?, deliverability_score=?,
                    composite_score=?, score_trend=?, last_checked_at=?, updated_at=?
                WHERE id=?
                """,
                #
                (
                    d.status.value,
                    d.display_name,
                    d.sending_ip,
                    d.dkim_selector,
                    d.operator_email,
                    d.rep_score,
                    d.deliverability_score,
                    d.composite_score,
                    d.score_trend.value,
                    to_iso(d.last_checked_at),
                    to_iso(d.updated_at),
                    d.id,
                ),
            )
            await db.commit()

    async def list_domains(
        self,
        status: Optional[DomainStatus] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        limit: int = 200,
    ) -> list[MonitoredDomain]:
        q = "SELECT * FROM monitored_domains WHERE 1=1"
        params: list[Any] = []
        if status:
            q += " AND status = ?"
            params.append(status.value)
        if min_score is not None:
            q += " AND composite_score >= ?"
            params.append(min_score)
        if max_score is not None:
            q += " AND composite_score <= ?"
            params.append(max_score)
        q += " ORDER BY domain ASC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(q, params) as cur:
                rows = await cur.fetchall()
        return [_row_to_domain(r) for r in rows]

    # --- DNS / blocklist / dmarc ---

    async def insert_dns_snapshot(self, s: DnsSnapshot) -> DnsSnapshot:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO dns_snapshots (
                  id, domain_id, checked_at, spf_record, spf_valid, dkim_record,
                  dkim_valid, dmarc_record, dmarc_valid, dmarc_policy,
                  mx_records_json, issues_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    s.id,
                    s.domain_id,
                    to_iso(s.checked_at),
                    s.spf_record,
                    1 if s.spf_valid else 0,
                    s.dkim_record,
                    1 if s.dkim_valid else 0,
                    s.dmarc_record,
                    1 if s.dmarc_valid else 0,
                    s.dmarc_policy.value,
                    s.mx_records_json,
                    s.issues_json,
                ),
            )
            await db.commit()
        return s

    async def list_dns_snapshots(
        self, domain_id: str, limit: int = 30
    ) -> list[DnsSnapshot]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM dns_snapshots WHERE domain_id = ? "
                "ORDER BY checked_at DESC LIMIT ?",
                (domain_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_dns(r) for r in rows]

    async def insert_blocklist_result(self, b: BlocklistResult) -> BlocklistResult:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO blocklist_results (
                  id, domain_id, checked_at, listed_count, checked_count, results_json
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    b.id,
                    b.domain_id,
                    to_iso(b.checked_at),
                    b.listed_count,
                    b.checked_count,
                    b.results_json,
                ),
            )
            await db.commit()
        return b

    async def list_blocklist_results(
        self, domain_id: str, limit: int = 30
    ) -> list[BlocklistResult]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM blocklist_results WHERE domain_id = ? "
                "ORDER BY checked_at DESC LIMIT ?",
                (domain_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_blocklist(r) for r in rows]

    async def insert_dmarc_report(self, r: DmarcReport) -> DmarcReport:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO dmarc_reports (
                  id, domain_id, report_id, org_name, date_begin, date_end,
                  pass_count, fail_count, dkim_pass, dkim_fail, spf_pass, spf_fail,
                  raw_xml_path, ingested_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r.id,
                    r.domain_id,
                    r.report_id,
                    r.org_name,
                    to_iso(r.date_begin),
                    to_iso(r.date_end),
                    r.pass_count,
                    r.fail_count,
                    r.dkim_pass,
                    r.dkim_fail,
                    r.spf_pass,
                    r.spf_fail,
                    r.raw_xml_path,
                    to_iso(r.ingested_at),
                ),
            )
            await db.commit()
        return r

    async def insert_dmarc_record_row(self, rec: DmarcRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO dmarc_records (
                  id, report_id, source_ip, count, disposition,
                  dkim_result, spf_result, header_from
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    rec.id,
                    rec.report_id,
                    rec.source_ip,
                    rec.count,
                    rec.disposition,
                    rec.dkim_result,
                    rec.spf_result,
                    rec.header_from,
                ),
            )
            await db.commit()

    async def list_dmarc_reports(
        self, domain_id: str, limit: int = 90
    ) -> list[DmarcReport]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM dmarc_reports WHERE domain_id = ? "
                "ORDER BY COALESCE(date_begin, ingested_at) DESC LIMIT ?",
                (domain_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_dmarc_report(r) for r in rows]

    # --- mentions ---

    async def upsert_mention(self, m: Mention) -> Mention:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM mentions WHERE id = ?", (m.id,)) as cur:
                exists = await cur.fetchone()
            if exists:
                await db.execute(
                    """
                    UPDATE mentions SET
                      source=?, external_id=?, author=?, rating=?, content=?,
                      mention_kind=?, sentiment=?, sentiment_score=?, url=?,
                      published_at=?, fetched_at=?, response_status=?,
                      draft_response=?, response_approval_token=?,
                      response_published_at=?
                    WHERE id=?
                    """,
                    (
                        m.source.value,
                        m.external_id,
                        m.author,
                        m.rating,
                        m.content,
                        m.mention_kind.value,
                        m.sentiment.value,
                        m.sentiment_score,
                        m.url,
                        to_iso(m.published_at),
                        to_iso(m.fetched_at),
                        m.response_status.value,
                        m.draft_response,
                        m.response_approval_token,
                        to_iso(m.response_published_at),
                        m.id,
                    ),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO mentions (
                      id, domain_id, source, external_id, author, rating, content,
                      mention_kind, sentiment, sentiment_score, url, published_at,
                      fetched_at, response_status, draft_response,
                      response_approval_token, response_published_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        m.id,
                        m.domain_id,
                        m.source.value,
                        m.external_id,
                        m.author,
                        m.rating,
                        m.content,
                        m.mention_kind.value,
                        m.sentiment.value,
                        m.sentiment_score,
                        m.url,
                        to_iso(m.published_at),
                        to_iso(m.fetched_at),
                        m.response_status.value,
                        m.draft_response,
                        m.response_approval_token,
                        to_iso(m.response_published_at),
                    ),
                )
            await db.commit()
        return m

    async def get_mention(self, mention_id: str) -> Optional[Mention]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM mentions WHERE id = ?", (mention_id,)
            ) as cur:
                row = await cur.fetchone()
        return _row_to_mention(row) if row else None

    async def find_mention_id_prefix(self, prefix: str) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id FROM mentions WHERE id LIKE ? LIMIT 2",
                (f"{prefix}%",),
            ) as cur:
                rows = await cur.fetchall()
        if len(rows) == 1:
            return str(rows[0][0])
        return None

    async def list_mentions(
        self,
        domain_id: Optional[str] = None,
        source: Optional[MentionSource] = None,
        sentiment: Optional[Sentiment] = None,
        response_status: Optional[ResponseStatus] = None,
        limit: int = 50,
    ) -> list[Mention]:
        q = "SELECT * FROM mentions WHERE 1=1"
        params: list[Any] = []
        if domain_id:
            q += " AND domain_id = ?"
            params.append(domain_id)
        if source:
            q += " AND source = ?"
            params.append(source.value)
        if sentiment:
            q += " AND sentiment = ?"
            params.append(sentiment.value)
        if response_status:
            q += " AND response_status = ?"
            params.append(response_status.value)
        q += " ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(q, params) as cur:
                rows = await cur.fetchall()
        return [_row_to_mention(r) for r in rows]

    async def approve_mention_response(
        self, mention_id: str, approved_by: str = "operator"
    ) -> tuple[bool, Optional[str]]:
        """Move draft -> approved; assign new approval token for publish interlock."""
        token = str(uuid4())
        now = to_iso(now_utc())
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE mentions
                   SET response_status = 'approved',
                       response_approval_token = ?
                 WHERE id = ?
                   AND response_status = 'drafted'
                   AND draft_response != ''
                """,
                (token, mention_id),
            )
            await db.commit()
            if cur.rowcount > 0:
                return True, token
        return False, None

    async def mark_mention_published(
        self, mention_id: str, approval_token: str
    ) -> bool:
        """Atomic publish guard — only from approved + matching token."""
        now = to_iso(now_utc())
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE mentions
                   SET response_status = 'published',
                       response_published_at = ?
                 WHERE id = ?
                   AND response_status = 'approved'
                   AND response_approval_token = ?
                """,
                (now, mention_id, approval_token),
            )
            await db.commit()
            return cur.rowcount > 0

    # --- alerts ---

    async def insert_alert(self, a: AlertRecord) -> AlertRecord:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO alert_records (
                  id, domain_id, kind, severity, message, detail_json,
                  status, triggered_at, resolved_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    a.id,
                    a.domain_id,
                    a.kind.value,
                    a.severity.value,
                    a.message,
                    a.detail_json,
                    a.status.value,
                    to_iso(a.triggered_at),
                    to_iso(a.resolved_at),
                ),
            )
            await db.commit()
        return a

    async def list_alerts(
        self,
        domain_id: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
        kind: Optional[AlertKind] = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[AlertRecord]:
        q = "SELECT * FROM alert_records WHERE 1=1"
        params: list[Any] = []
        if domain_id:
            q += " AND domain_id = ?"
            params.append(domain_id)
        if severity:
            q += " AND severity = ?"
            params.append(severity.value)
        if kind:
            q += " AND kind = ?"
            params.append(kind.value)
        if active_only:
            q += " AND status IN ('new', 'acknowledged')"
        q += " ORDER BY triggered_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(q, params) as cur:
                rows = await cur.fetchall()
        return [_row_to_alert(r) for r in rows]

    async def acknowledge_alert(self, alert_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE alert_records SET status = 'acknowledged'
                WHERE id = ? AND status = 'new'
                """,
                (alert_id,),
            )
            await db.commit()
            return cur.rowcount > 0

    async def resolve_alert(self, alert_id: str) -> bool:
        now = to_iso(now_utc())
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE alert_records SET status = 'resolved', resolved_at = ?
                WHERE id = ? AND status IN ('new', 'acknowledged')
                """,
                (now, alert_id),
            )
            await db.commit()
            return cur.rowcount > 0

    # --- warmup ---

    async def upsert_warmup_plan(self, w: WarmupPlan) -> WarmupPlan:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id FROM warmup_plans WHERE domain_id = ?", (w.domain_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute(
                    """
                    UPDATE warmup_plans SET
                      start_date=?, target_daily_volume_json=?, guidance_md=?,
                      current_day=?, status=?
                    WHERE domain_id=?
                    """,
                    (
                        to_iso(w.start_date),
                        w.target_daily_volume_json,
                        w.guidance_md,
                        w.current_day,
                        w.status.value,
                        w.domain_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO warmup_plans (
                      id, domain_id, start_date, target_daily_volume_json,
                      guidance_md, current_day, status, created_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        w.id,
                        w.domain_id,
                        to_iso(w.start_date),
                        w.target_daily_volume_json,
                        w.guidance_md,
                        w.current_day,
                        w.status.value,
                        to_iso(w.created_at),
                    ),
                )
            await db.commit()
        return w

    async def get_warmup_plan(self, domain_id: str) -> Optional[WarmupPlan]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM warmup_plans WHERE domain_id = ?", (domain_id,)
            ) as cur:
                row = await cur.fetchone()
        return _row_to_warmup(row) if row else None

    async def insert_raw_mention(self, r: RawMentionIngest) -> RawMentionIngest:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO raw_mention_ingest (
                  id, domain_id, source, raw_payload_json, received_at, processed, error
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    r.id,
                    r.domain_id,
                    r.source.value,
                    r.raw_payload_json,
                    to_iso(r.received_at),
                    1 if r.processed else 0,
                    r.error,
                ),
            )
            await db.commit()
        return r


# --- row mappers ---


def _row_to_domain(row: aiosqlite.Row) -> MonitoredDomain:
    return MonitoredDomain(
        id=row["id"],
        domain=row["domain"],
        status=DomainStatus(row["status"]),
        display_name=row["display_name"] or "",
        sending_ip=row["sending_ip"],
        dkim_selector=row["dkim_selector"] or "google",
        operator_email=row["operator_email"] or "",
        rep_score=float(row["rep_score"] or 0),
        deliverability_score=float(row["deliverability_score"] or 0),
        composite_score=float(row["composite_score"] or 0),
        score_trend=ScoreTrend(row["score_trend"] or "flat"),
        last_checked_at=parse_iso(row["last_checked_at"]),
        created_at=parse_iso(row["created_at"]) or now_utc(),
        updated_at=parse_iso(row["updated_at"]) or now_utc(),
    )


def _row_to_dns(row: aiosqlite.Row) -> DnsSnapshot:
    return DnsSnapshot(
        id=row["id"],
        domain_id=row["domain_id"],
        checked_at=parse_iso(row["checked_at"]) or now_utc(),
        spf_record=row["spf_record"],
        spf_valid=bool(row["spf_valid"]),
        dkim_record=row["dkim_record"],
        dkim_valid=bool(row["dkim_valid"]),
        dmarc_record=row["dmarc_record"],
        dmarc_valid=bool(row["dmarc_valid"]),
        dmarc_policy=DmarcPolicy(row["dmarc_policy"] or "none"),
        mx_records_json=row["mx_records_json"] or "[]",
        issues_json=row["issues_json"] or "[]",
    )


def _row_to_blocklist(row: aiosqlite.Row) -> BlocklistResult:
    return BlocklistResult(
        id=row["id"],
        domain_id=row["domain_id"],
        checked_at=parse_iso(row["checked_at"]) or now_utc(),
        listed_count=int(row["listed_count"] or 0),
        checked_count=int(row["checked_count"] or 0),
        results_json=row["results_json"] or "[]",
    )


def _row_to_dmarc_report(row: aiosqlite.Row) -> DmarcReport:
    return DmarcReport(
        id=row["id"],
        domain_id=row["domain_id"],
        report_id=row["report_id"] or "",
        org_name=row["org_name"] or "",
        date_begin=parse_iso(row["date_begin"]),
        date_end=parse_iso(row["date_end"]),
        pass_count=int(row["pass_count"] or 0),
        fail_count=int(row["fail_count"] or 0),
        dkim_pass=int(row["dkim_pass"] or 0),
        dkim_fail=int(row["dkim_fail"] or 0),
        spf_pass=int(row["spf_pass"] or 0),
        spf_fail=int(row["spf_fail"] or 0),
        raw_xml_path=row["raw_xml_path"],
        ingested_at=parse_iso(row["ingested_at"]) or now_utc(),
    )


def _row_to_mention(row: aiosqlite.Row) -> Mention:
    return Mention(
        id=row["id"],
        domain_id=row["domain_id"],
        source=MentionSource(row["source"]),
        external_id=row["external_id"] or "",
        author=row["author"] or "",
        rating=row["rating"],
        content=row["content"] or "",
        mention_kind=MentionKind(row["mention_kind"] or "mention"),
        sentiment=Sentiment(row["sentiment"] or "neutral"),
        sentiment_score=float(row["sentiment_score"] or 0.5),
        url=row["url"] or "",
        published_at=parse_iso(row["published_at"]),
        fetched_at=parse_iso(row["fetched_at"]) or now_utc(),
        response_status=ResponseStatus(row["response_status"] or "none"),
        draft_response=row["draft_response"] or "",
        response_approval_token=row["response_approval_token"],
        response_published_at=parse_iso(row["response_published_at"]),
    )


def _row_to_alert(row: aiosqlite.Row) -> AlertRecord:
    return AlertRecord(
        id=row["id"],
        domain_id=row["domain_id"],
        kind=AlertKind(row["kind"]),
        severity=AlertSeverity(row["severity"]),
        message=row["message"] or "",
        detail_json=row["detail_json"] or "{}",
        status=AlertStatus(row["status"]),
        triggered_at=parse_iso(row["triggered_at"]) or now_utc(),
        resolved_at=parse_iso(row["resolved_at"]),
    )


def _row_to_warmup(row: aiosqlite.Row) -> WarmupPlan:
    return WarmupPlan(
        id=row["id"],
        domain_id=row["domain_id"],
        start_date=parse_iso(row["start_date"]) or now_utc(),
        target_daily_volume_json=row["target_daily_volume_json"] or "[]",
        guidance_md=row["guidance_md"] or "",
        current_day=int(row["current_day"] or 0),
        status=WarmupStatus(row["status"]),
        created_at=parse_iso(row["created_at"]) or now_utc(),
    )
