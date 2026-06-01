"""RepMon CLI — `repmon` command."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from repmon import __version__
from repmon.config.loader import display_agent_name, load_api_keys, load_config
from repmon.crm.database import RepMonDatabase
from repmon.scoring.engine import dmarc_reports_in_window
from repmon.service import (
    add_domain,
    dashboard_summary,
    refresh_domain_scores,
    resolve_domain_id,
)
from repmon.sources.dmarc_parser import ingest_report_file

console = Console()


def _log(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _boot() -> tuple:
    config = load_config()
    keys = load_api_keys()
    db = RepMonDatabase(config.database.path)
    await db.init()
    return config, keys, db


@click.group()
@click.version_option(__version__, prog_name="repmon")
@click.option("--debug", is_flag=True)
def main(debug: bool) -> None:
    """RepMon — reputation monitoring and domain health."""
    _log(debug)


@main.command()
def pipeline() -> None:
    """Composite health dashboard for all domains."""

    async def _run() -> None:
        cfg, _, db = await _boot()
        rows = await dashboard_summary(db)
        if not rows:
            console.print("[yellow]No monitored domains. Use add-domain.[/yellow]")
            return
        table = Table(title=f"RepMon Dashboard ({display_agent_name(cfg)})")
        table.add_column("Domain")
        table.add_column("Composite")
        table.add_column("Reputation")
        table.add_column("Deliverability")
        table.add_column("Trend")
        for r in rows:
            table.add_row(
                r["domain"],
                f"{r['composite_score']:.1f}",
                f"{r['rep_score']:.1f}",
                f"{r['deliverability_score']:.1f}",
                str(r.get("score_trend") or ""),
            )
        console.print(table)

    asyncio.run(_run())


@main.command("add-domain")
@click.argument("domain")
def add_domain_cmd(domain: str) -> None:
    """Add a monitored domain and run an initial check."""

    async def _run() -> None:
        config, _, db = await _boot()
        d = await add_domain(db, config, domain)
        console.print(f"[green]Added[/green] {d.domain} composite={d.composite_score:.1f}")

    asyncio.run(_run())


@main.command()
@click.argument("domain_token")
def check(domain_token: str) -> None:
    """Run DNS + blocklist refresh for a domain."""

    async def _run() -> None:
        config, _, db = await _boot()
        d = await resolve_domain_id(db, domain_token)
        if not d:
            console.print("[red]Domain not found[/red]")
            return
        d2 = await refresh_domain_scores(db, config, d)
        console.print(
            f"composite={d2.composite_score:.1f} "
            f"rep={d2.rep_score:.1f} dlv={d2.deliverability_score:.1f}"
        )

    asyncio.run(_run())


@main.command()
@click.argument("domain_token")
def dmarc(domain_token: str) -> None:
    """Show DMARC pass/fail rollups (7-day)."""

    async def _run() -> None:
        _, _, db = await _boot()
        d = await resolve_domain_id(db, domain_token)
        if not d:
            console.print("[red]Domain not found[/red]")
            return
        reports = await db.list_dmarc_reports(d.id, limit=500)
        w = dmarc_reports_in_window(reports, window_days=7)
        p, f = sum(r.pass_count for r in w), sum(r.fail_count for r in w)
        console.print(f"7-day aggregate: pass={p} fail={f} reports={len(w)}")

    asyncio.run(_run())


@main.command("ingest-dmarc")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--domain-id", required=True, help="Monitored domain id")
def ingest_dmarc(path: Path, domain_id: str) -> None:
    """Parse and store a DMARC XML report file."""

    async def _run() -> None:
        _, _, db = await _boot()
        rep = await ingest_report_file(path, domain_id, db)
        console.print(f"Ingested report {rep.report_id} ({rep.id})")

    asyncio.run(_run())


@main.command()
def mentions() -> None:
    """Recent mentions."""

    async def _run() -> None:
        _, _, db = await _boot()
        m = await db.list_mentions(limit=30)
        for x in m:
            console.print(f"{x.id[:8]} | {x.source.value} | {x.sentiment.value} | {x.content[:80]!s}")

    asyncio.run(_run())


@main.command()
def alerts() -> None:
    """Active alerts."""

    async def _run() -> None:
        _, _, db = await _boot()
        a = await db.list_alerts(limit=50)
        for x in a:
            console.print(f"{x.severity.value} | {x.kind.value} | {x.message}")

    asyncio.run(_run())


@main.command()
@click.argument("domain_token")
@click.option("--generate", is_flag=True, help="AI-generate a new plan")
def warmup(domain_token: str, generate: bool) -> None:
    """Show or generate a warmup plan."""

    async def _run() -> None:
        config, keys, db = await _boot()
        d = await resolve_domain_id(db, domain_token)
        if not d:
            console.print("[red]Domain not found[/red]")
            return
        if generate:
            from repmon.ai.advisor import DomainAdvisor

            adv = DomainAdvisor(config, keys)
            plan = await adv.generate_warmup_plan(d.domain, d.id)
            await db.upsert_warmup_plan(plan)
            console.print(plan.guidance_md)
        else:
            w = await db.get_warmup_plan(d.id)
            if not w:
                console.print("No warmup plan.")
                return
            console.print(w.guidance_md or json.dumps(w.model_dump(mode="json")))

    asyncio.run(_run())


@main.command()
@click.argument("domain_token")
def score(domain_token: str) -> None:
    """Print current scores for a domain."""

    async def _run() -> None:
        _, _, db = await _boot()
        d = await resolve_domain_id(db, domain_token)
        if not d:
            console.print("[red]Domain not found[/red]")
            return
        console.print(json.dumps(d.model_dump(mode="json"), indent=2, default=str))

    asyncio.run(_run())


@main.command()
def mcp() -> None:
    """Start MCP server (stdio)."""
    from repmon.mcp_server.server import main as mcp_main

    asyncio.run(mcp_main())


if __name__ == "__main__":
    main()
