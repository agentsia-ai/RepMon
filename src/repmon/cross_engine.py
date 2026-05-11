"""Read-only sibling SQLite access (LeadGen, PropGen). No package imports."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import aiosqlite

from repmon.config.loader import RepMonConfig

logger = logging.getLogger(__name__)


def _ro_uri(path: Path) -> str:
    base = path.resolve().as_uri()
    return f"{base}?mode=ro&immutable=1"


def _extract_domain_from_email(email: str) -> Optional[str]:
    email = (email or "").strip().lower()
    if "@" not in email:
        return None
    host = email.rsplit("@", 1)[-1].strip()
    return host if host else None


async def fetch_lead_domains(config: RepMonConfig) -> list[str]:
    """Distinct company domains from LeadGen `leads.company_json` (domain/website)."""
    path_raw = config.cross_engine.leadgen_db
    if not path_raw:
        return []
    path = Path(path_raw)
    if not path.is_file():
        logger.debug("LeadGen DB not found: %s", path)
        return []
    out: set[str] = set()
    try:
        uri = _ro_uri(path)
        async with aiosqlite.connect(uri, uri=True) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT company_json FROM leads WHERE company_json IS NOT NULL AND company_json != ''"
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            raw = row["company_json"]
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            d = (data.get("domain") or data.get("website") or "").strip()
            if not d:
                continue
            d = d.lower().replace("https://", "").replace("http://", "").split("/")[0]
            if d:
                out.add(d)
        return sorted(out)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_lead_domains failed: %s", e)
        return []


async def fetch_propgen_domains(config: RepMonConfig) -> list[str]:
    """Client email domains from PropGen proposals (sent or accepted lifecycle)."""
    path_raw = config.cross_engine.propgen_db
    if not path_raw:
        return []
    path = Path(path_raw)
    if not path.is_file():
        logger.debug("PropGen DB not found: %s", path)
        return []
    out: set[str] = set()
    try:
        uri = _ro_uri(path)
        async with aiosqlite.connect(uri, uri=True) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT client_email, status FROM proposals
                WHERE client_email IS NOT NULL AND client_email != ''
                  AND status IN ('sent', 'viewed', 'signed', 'accepted', 'drafted')
                """
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            dom = _extract_domain_from_email(str(row["client_email"] or ""))
            if dom:
                out.add(dom)
        return sorted(out)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_propgen_domains failed: %s", e)
        return []
