"""RepMon MCP server — stdio transport; no print() to stdout."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from repmon.ai.advisor import DomainAdvisor
from repmon.ai.classifier import MentionClassifier
from repmon.ai.drafter import ResponseDrafter
from repmon.config.loader import display_agent_name, load_api_keys, load_config
from repmon.crm.database import RepMonDatabase
from repmon.models import MentionSource, Sentiment, ResponseStatus
from repmon.scoring.engine import (
    compute_deliverability,
    dmarc_reports_in_window,
)
from repmon.service import (
    add_domain,
    approve_response,
    dashboard_summary,
    draft_response_for_mention,
    publish_response,
    resolve_domain_id,
)
from repmon.sources.blocklist_checker import check_domain as bl_check
from repmon.sources.dns_checker import check_dns
from repmon.sources.dmarc_parser import ingest_report_file

logger = logging.getLogger(__name__)

app = Server("repmon")

config = None  # type: ignore[assignment]
keys = None  # type: ignore[assignment]
db = None  # type: ignore[assignment]

MENTION_CLASSIFIER_CLASS: type[MentionClassifier] = MentionClassifier
RESPONSE_DRAFTER_CLASS: type[ResponseDrafter] = ResponseDrafter
DOMAIN_ADVISOR_CLASS: type[DomainAdvisor] = DomainAdvisor


def _json(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_dashboard",
            description="Composite health summary for all monitored domains.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_domain",
            description="Add a domain to monitoring and run an initial check.",
            inputSchema={
                "type": "object",
                "properties": {"domain": {"type": "string"}},
                "required": ["domain"],
            },
        ),
        Tool(
            name="get_domain_detail",
            description="Full health card for one domain (id or FQDN).",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
        ),
        Tool(
            name="list_domains",
            description="Filter domains by status / composite score range.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "min_score": {"type": "number"},
                    "max_score": {"type": "number"},
                },
            },
        ),
        Tool(
            name="run_dns_check",
            description="On-demand DNS validation.",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
        ),
        Tool(
            name="run_blocklist_check",
            description="On-demand DNSBL checks.",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
        ),
        Tool(
            name="get_dns_history",
            description="Recent DnsSnapshots.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["domain_id"],
            },
        ),
        Tool(
            name="get_blocklist_history",
            description="Recent BlocklistResults.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["domain_id"],
            },
        ),
        Tool(
            name="get_dmarc_summary",
            description="Aggregated DMARC pass/fail in the last 7 days.",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
        ),
        Tool(
            name="ingest_dmarc_report",
            description="Ingest a DMARC XML file from disk.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "domain_id": {"type": "string"},
                },
                "required": ["path", "domain_id"],
            },
        ),
        Tool(
            name="list_mentions",
            description="List mentions with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_id": {"type": "string"},
                    "source": {"type": "string"},
                    "sentiment": {"type": "string"},
                    "response_status": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="get_mention_detail",
            description="Single mention + draft response.",
            inputSchema={
                "type": "object",
                "properties": {"mention_id": {"type": "string"}},
                "required": ["mention_id"],
            },
        ),
        Tool(
            name="draft_response",
            description="AI-draft a response (does not publish).",
            inputSchema={
                "type": "object",
                "properties": {"mention_id": {"type": "string"}},
                "required": ["mention_id"],
            },
        ),
        Tool(
            name="approve_response",
            description="Approve draft; returns approval_token for publish.",
            inputSchema={
                "type": "object",
                "properties": {"mention_id": {"type": "string"}},
                "required": ["mention_id"],
            },
        ),
        Tool(
            name="publish_response",
            description=(
                "Post approved response (stub for most platforms); requires approval_token."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mention_id": {"type": "string"},
                    "approval_token": {"type": "string"},
                },
                "required": ["mention_id", "approval_token"],
            },
        ),
        Tool(
            name="list_alerts",
            description="Active alerts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_id": {"type": "string"},
                    "severity": {"type": "string"},
                    "kind": {"type": "string"},
                },
            },
        ),
        Tool(
            name="acknowledge_alert",
            inputSchema={
                "type": "object",
                "properties": {"alert_id": {"type": "string"}},
                "required": ["alert_id"],
            },
            description="Mark alert acknowledged.",
        ),
        Tool(
            name="resolve_alert",
            inputSchema={
                "type": "object",
                "properties": {"alert_id": {"type": "string"}},
                "required": ["alert_id"],
            },
            description="Mark alert resolved.",
        ),
        Tool(
            name="get_warmup_plan",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
            description="Current warmup plan for a domain.",
        ),
        Tool(
            name="generate_warmup_plan",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
            description="AI-generate a warmup plan.",
        ),
        Tool(
            name="get_rep_score_history",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["domain_id"],
            },
            description="Rolling composite / rep / deliverability samples.",
        ),
        Tool(
            name="get_deliverability_score",
            inputSchema={
                "type": "object",
                "properties": {"domain_id": {"type": "string"}},
                "required": ["domain_id"],
            },
            description="Deliverability sub-score with DNS/BL/DMARC breakdown.",
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    arguments = arguments or {}
    try:

        if name == "get_dashboard":
            data = await dashboard_summary(db)
            return _json({"agent": display_agent_name(config), "domains": data})

        if name == "add_domain":
            dom = await add_domain(db, config, arguments["domain"])
            return _json({"domain": dom.model_dump(mode="json")})

        if name == "get_domain_detail":
            d = await resolve_domain_id(db, arguments["domain_id"])
            if not d:
                return _json({"error": "domain not found"})
            dns_l = await db.list_dns_snapshots(d.id, limit=1)
            bl_l = await db.list_blocklist_results(d.id, limit=1)
            reports = await db.list_dmarc_reports(d.id, limit=200)
            w = dmarc_reports_in_window(reports, window_days=7)
            dns_s = dns_l[0] if dns_l else None
            bl_s = bl_l[0] if bl_l else None
            diagnosis = ""
            if dns_s and bl_s:
                adv = DOMAIN_ADVISOR_CLASS(config, keys)
                total_p = sum(r.pass_count for r in w)
                total_f = sum(r.fail_count for r in w)
                summary_md = f"7-day DMARC passes: {total_p}, fails: {total_f}"
                diagnosis = await adv.diagnose_deliverability(dns_s, bl_s, summary_md)
            return _json(
                {
                    "domain": d.model_dump(mode="json"),
                    "latest_dns": dns_s.model_dump(mode="json") if dns_s else None,
                    "latest_blocklist": bl_s.model_dump(mode="json") if bl_s else None,
                    "diagnosis_md": diagnosis,
                }
            )

        if name == "list_domains":
            from repmon.models import DomainStatus

            st = arguments.get("status")
            status = DomainStatus(st) if st else None
            rows = await db.list_domains(
                status=status,
                min_score=arguments.get("min_score"),
                max_score=arguments.get("max_score"),
            )
            return _json([r.model_dump(mode="json") for r in rows])

        if name == "run_dns_check":
            d = await resolve_domain_id(db, arguments["domain_id"])
            if not d:
                return _json({"error": "domain not found"})
            snap = await check_dns(
                d.id, d.domain, config.domain_health.dkim_selectors
            )
            await db.insert_dns_snapshot(snap)
            return _json({"snapshot": snap.model_dump(mode="json")})

        if name == "run_blocklist_check":
            d = await resolve_domain_id(db, arguments["domain_id"])
            if not d:
                return _json({"error": "domain not found"})
            bl = await bl_check(d.id, d.domain, d.sending_ip, config)
            await db.insert_blocklist_result(bl)
            return _json({"blocklist": bl.model_dump(mode="json")})

        if name == "get_dns_history":
            snaps = await db.list_dns_snapshots(
                arguments["domain_id"], limit=int(arguments.get("limit", 30))
            )
            return _json([s.model_dump(mode="json") for s in snaps])

        if name == "get_blocklist_history":
            rows = await db.list_blocklist_results(
                arguments["domain_id"], limit=int(arguments.get("limit", 30))
            )
            return _json([r.model_dump(mode="json") for r in rows])

        if name == "get_dmarc_summary":
            reports = await db.list_dmarc_reports(arguments["domain_id"], limit=500)
            w = dmarc_reports_in_window(reports, window_days=7)
            return _json(
                {
                    "reports": [r.model_dump(mode="json") for r in w],
                    "pass_sum": sum(r.pass_count for r in w),
                    "fail_sum": sum(r.fail_count for r in w),
                }
            )

        if name == "ingest_dmarc_report":
            from pathlib import Path

            path = Path(arguments["path"])
            if not path.is_file():
                return _json({"error": f"file not found: {path}"})
            rep = await ingest_report_file(path, arguments["domain_id"], db)
            return _json({"report": rep.model_dump(mode="json")})

        if name == "list_mentions":
            src = arguments.get("source")
            sent = arguments.get("sentiment")
            rs = arguments.get("response_status")
            rows = await db.list_mentions(
                domain_id=arguments.get("domain_id"),
                source=MentionSource(src) if src else None,
                sentiment=Sentiment(sent) if sent else None,
                response_status=ResponseStatus(rs) if rs else None,
                limit=int(arguments.get("limit", 50)),
            )
            return _json([m.model_dump(mode="json") for m in rows])

        if name == "get_mention_detail":
            m = await db.get_mention(arguments["mention_id"])
            return _json({"mention": m.model_dump(mode="json") if m else None})

        if name == "draft_response":
            m = await draft_response_for_mention(
                db,
                config,
                keys,
                arguments["mention_id"],
                RESPONSE_DRAFTER_CLASS,
            )
            return _json({"mention": m.model_dump(mode="json")})

        if name == "approve_response":
            ok, tok = await approve_response(db, arguments["mention_id"])
            return _json({"ok": ok, "approval_token": tok})

        if name == "publish_response":
            ok = await publish_response(
                db,
                config,
                keys,
                arguments["mention_id"],
                arguments["approval_token"],
            )
            return _json({"published": ok})

        if name == "list_alerts":
            from repmon.models import AlertKind, AlertSeverity

            kind = arguments.get("kind")
            sev = arguments.get("severity")
            rows = await db.list_alerts(
                domain_id=arguments.get("domain_id"),
                severity=AlertSeverity(sev) if sev else None,
                kind=AlertKind(kind) if kind else None,
            )
            return _json([a.model_dump(mode="json") for a in rows])

        if name == "acknowledge_alert":
            ok = await db.acknowledge_alert(arguments["alert_id"])
            return _json({"ok": ok})

        if name == "resolve_alert":
            ok = await db.resolve_alert(arguments["alert_id"])
            return _json({"ok": ok})

        if name == "get_warmup_plan":
            w = await db.get_warmup_plan(arguments["domain_id"])
            return _json({"warmup": w.model_dump(mode="json") if w else None})

        if name == "generate_warmup_plan":
            d = await resolve_domain_id(db, arguments["domain_id"])
            if not d:
                return _json({"error": "domain not found"})
            adv = DOMAIN_ADVISOR_CLASS(config, keys)
            plan = await adv.generate_warmup_plan(d.domain, d.id)
            await db.upsert_warmup_plan(plan)
            return _json({"warmup": plan.model_dump(mode="json")})

        if name == "get_rep_score_history":
            rows = await db.list_score_history(
                arguments["domain_id"], limit=int(arguments.get("limit", 90))
            )
            return _json({"history": rows})

        if name == "get_deliverability_score":
            d = await resolve_domain_id(db, arguments["domain_id"])
            if not d:
                return _json({"error": "domain not found"})
            dns_l = await db.list_dns_snapshots(d.id, limit=1)
            bl_l = await db.list_blocklist_results(d.id, limit=1)
            reports = await db.list_dmarc_reports(d.id, limit=500)
            w = dmarc_reports_in_window(reports, window_days=7)
            dns_s = dns_l[0] if dns_l else await check_dns(
                d.id, d.domain, config.domain_health.dkim_selectors
            )
            bl_s = bl_l[0] if bl_l else await bl_check(
                d.id, d.domain, d.sending_ip, config
            )
            score = compute_deliverability(dns_s, bl_s, w)
            dns_pts = (
                (15 if dns_s.spf_valid else 0)
                + (15 if dns_s.dkim_valid else 0)
                + (10 if dns_s.dmarc_valid else 0)
            )
            chk = max(bl_s.checked_count, 1)
            listed_ratio = min(1.0, bl_s.listed_count / chk)
            bl_pts = 35.0 - (listed_ratio * 35.0)
            tot_p = sum(r.pass_count for r in w)
            tot_f = sum(r.fail_count for r in w)
            dm_pts = (tot_p / (tot_p + tot_f) * 25.0) if (tot_p + tot_f) else 0.0
            return _json(
                {
                    "deliverability_score": score,
                    "breakdown": {
                        "dns_points": dns_pts,
                        "blocklist_points": max(0, min(35, bl_pts)),
                        "dmarc_points": max(0, min(25, dm_pts)),
                    },
                }
            )

        return _json({"error": f"Unknown tool: {name}"})
    except Exception as e:  # noqa: BLE001
        logger.exception("tool error")
        return _json({"error": str(e)})


async def main(
    mention_classifier_cls: type[MentionClassifier] | None = None,
    response_drafter_cls: type[ResponseDrafter] | None = None,
    domain_advisor_cls: type[DomainAdvisor] | None = None,
) -> None:
    global MENTION_CLASSIFIER_CLASS, RESPONSE_DRAFTER_CLASS, DOMAIN_ADVISOR_CLASS
    global config, keys, db

    if mention_classifier_cls is not None:
        MENTION_CLASSIFIER_CLASS = mention_classifier_cls
    if response_drafter_cls is not None:
        RESPONSE_DRAFTER_CLASS = response_drafter_cls
    if domain_advisor_cls is not None:
        DOMAIN_ADVISOR_CLASS = domain_advisor_cls

    config = load_config()
    keys = load_api_keys()
    db = RepMonDatabase(config.database.path)
    await db.init()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    agent_label = display_agent_name(config)
    logger.info("Starting RepMon MCP server (agent=%s)...", agent_label)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
