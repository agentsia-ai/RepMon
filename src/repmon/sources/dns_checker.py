"""DNS validation with dnspython async resolver (SPF, DKIM, DMARC, MX)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

import dns.asyncresolver
import dns.exception
import dns.rdatatype

from repmon.models import DnsSnapshot, DmarcPolicy

logger = logging.getLogger(__name__)


def _txt_records(answer: Any) -> list[str]:
    chunks: list[str] = []
    for rrset in answer:
        for rdata in rrset:
            if rdata.rdtype == dns.rdatatype.TXT:
                blobs = rdata.strings
                if isinstance(blobs, list):
                    chunks.append(b"".join(blobs).decode("utf-8", errors="replace"))
                else:
                    chunks.append(str(blobs))
    return chunks


async def _resolve_txt(name: str) -> list[str]:
    try:
        answer = await dns.asyncresolver.resolve(name, "TXT")
        return _txt_records(answer)
    except (dns.exception.DNSException, OSError) as e:
        logger.debug("TXT lookup failed for %s: %s", name, e)
        return []


async def _resolve_mx(name: str) -> list[tuple[int, str]]:
    try:
        answer = await dns.asyncresolver.resolve(name, "MX")
        out: list[tuple[int, str]] = []
        for rrset in answer:
            for rdata in rrset:
                if rdata.rdtype == dns.rdatatype.MX:
                    out.append((int(rdata.preference), str(rdata.exchange).rstrip(".")))
        out.sort(key=lambda x: x[0])
        return out
    except (dns.exception.DNSException, OSError) as e:
        logger.debug("MX lookup failed for %s: %s", name, e)
        return []


def _parse_spf(txts: list[str]) -> tuple[Optional[str], bool, list[str]]:
    issues: list[str] = []
    spf = next((t for t in txts if t.startswith("v=spf1")), None)
    if not spf:
        issues.append("missing_spf")
        return None, False, issues
    if "v=spf1" not in spf:
        issues.append("malformed_spf")
        return spf, False, issues
    return spf, True, issues


def _parse_dkim(txts: list[str]) -> tuple[Optional[str], bool, list[str]]:
    issues: list[str] = []
    rec = next((t for t in txts if "v=DKIM1" in t or t.startswith("v=DKIM1")), None)
    if not rec:
        issues.append("missing_dkim")
        return None, False, issues
    if "p=" not in rec:
        issues.append("malformed_dkim")
        return rec, False, issues
    m = re.search(r"p=([^;\\s]+)", rec)
    key = m.group(1).strip() if m else ""
    if not key or key in ('""', "''"):
        issues.append("dkim_key_revoked_or_empty")
        return rec, False, issues
    return rec, True, issues


def _parse_dmarc(txts: list[str]) -> tuple[Optional[str], bool, DmarcPolicy, list[str]]:
    issues: list[str] = []
    rec = next((t for t in txts if "v=DMARC1" in t), None)
    if not rec:
        issues.append("missing_dmarc")
        return None, False, DmarcPolicy.NONE, issues
    m = re.search(r"\bp=(none|quarantine|reject)\b", rec, re.I)
    pol = DmarcPolicy((m.group(1).lower() if m else "none"))
    valid = bool(m)
    if pol == DmarcPolicy.NONE:
        issues.append("dmarc_policy_none_warning")
    return rec, valid, pol, issues


async def check_dns(domain_id: str, fqdn: str, dkim_selectors: list[str]) -> DnsSnapshot:
    """Build a DnsSnapshot for apex hostname `fqdn`."""
    issues: list[str] = []
    fqdn = fqdn.lower().strip().rstrip(".")

    apex_txt_task = _resolve_txt(fqdn)
    dmarc_task = _resolve_txt(f"_dmarc.{fqdn}")
    mx_task = _resolve_mx(fqdn)
    dkim_tasks = [
        _resolve_txt(f"{sel}._domainkey.{fqdn}") for sel in dkim_selectors
    ]
    gathered = await asyncio.gather(apex_txt_task, dmarc_task, mx_task, *dkim_tasks)
    apex_txt = gathered[0]
    dmarc_txts = gathered[1]
    mx_list = gathered[2]
    dkim_txt_lists = gathered[3:] if dkim_tasks else []

    spf_raw, spf_ok, spf_issues = _parse_spf(apex_txt)
    issues.extend(spf_issues)

    dkim_ok_any = False
    dkim_raw: Optional[str] = None
    for txts in dkim_txt_lists:
        raw, ok, di = _parse_dkim(txts)
        issues.extend(di)
        if raw:
            dkim_raw = raw
        if ok:
            dkim_ok_any = True

    dmarc_raw, dmarc_ok, dmarc_pol, dm_issues = _parse_dmarc(dmarc_txts)
    issues.extend(dm_issues)

    return DnsSnapshot(
        domain_id=domain_id,
        spf_record=spf_raw,
        spf_valid=spf_ok,
        dkim_record=dkim_raw,
        dkim_valid=dkim_ok_any,
        dmarc_record=dmarc_raw,
        dmarc_valid=dmarc_ok,
        dmarc_policy=dmarc_pol,
        mx_records_json=json.dumps([{"priority": p, "host": h} for p, h in mx_list]),
        issues_json=json.dumps(issues),
    )
