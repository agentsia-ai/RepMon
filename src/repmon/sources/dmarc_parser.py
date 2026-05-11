"""DMARC aggregate report XML parsing (RFC 7489) + ingestion."""

from __future__ import annotations

import gzip
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lxml import etree

from repmon._time import now_utc
from repmon.crm.database import RepMonDatabase
from repmon.models import DmarcRecord, DmarcReport


def _lname(el: etree._Element) -> str:
    tag = el.tag
    return tag.split("}")[-1] if "}" in str(tag) else str(tag)


def _child(parent: etree._Element, name: str) -> etree._Element | None:
    for ch in parent:
        if _lname(ch) == name:
            return ch
    return None


def _text(el: etree._Element | None, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _int_text(el: etree._Element | None, default: int = 0) -> int:
    if el is None or el.text is None:
        return default
    try:
        return int(el.text.strip())
    except ValueError:
        return default


@dataclass
class ParsedDmarcReport:
    org_name: str = ""
    report_id: str = ""
    date_begin: datetime | None = None
    date_end: datetime | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    dkim_pass: int = 0
    dkim_fail: int = 0
    spf_pass: int = 0
    spf_fail: int = 0


def parse_dmarc_xml(xml_bytes: bytes) -> ParsedDmarcReport:
    """Parse DMARC aggregate XML (namespace-agnostic local names)."""
    root = etree.fromstring(xml_bytes)
    meta = _child(root, "report_metadata")
    parsed = ParsedDmarcReport()
    if meta is not None:
        parsed.org_name = _text(_child(meta, "org_name"))
        parsed.report_id = _text(_child(meta, "report_id"))
        dr = _child(meta, "date_range")
        if dr is not None:
            b = _child(dr, "begin")
            e = _child(dr, "end")
            if b is not None and b.text:
                parsed.date_begin = datetime.fromtimestamp(int(b.text), tz=timezone.utc)
            if e is not None and e.text:
                parsed.date_end = datetime.fromtimestamp(int(e.text), tz=timezone.utc)

    for rec in root:
        if _lname(rec) != "record":
            continue
        row: dict[str, Any] = {}
        src = _child(rec, "row")
        if src is not None:
            row["source_ip"] = _text(_child(src, "source_ip"))
            row["count"] = _int_text(_child(src, "count"), 1)
            pe = _child(src, "policy_evaluated")
            if pe is not None:
                row["disposition"] = _text(_child(pe, "disposition"))
                row["dkim"] = _text(_child(pe, "dkim"))
                row["spf"] = _text(_child(pe, "spf"))
        ident = _child(rec, "identifiers")
        header_from = ""
        if ident is not None:
            header_from = _text(_child(ident, "header_from"))
        row["header_from"] = header_from

        dkim_domain = ""
        dkim_result = ""
        spf_domain = ""
        spf_result = ""
        auth = _child(rec, "auth_results")
        if auth is not None:
            for ach in auth:
                ln = _lname(ach)
                if ln == "dkim" and not dkim_result:
                    dkim_domain = _text(_child(ach, "domain"))
                    dkim_result = _text(_child(ach, "result"))
                elif ln == "spf" and not spf_result:
                    spf_domain = _text(_child(ach, "domain"))
                    spf_result = _text(_child(ach, "result"))
        row["dkim_domain"] = dkim_domain
        row["dkim_result"] = dkim_result
        row["spf_domain"] = spf_domain
        row["spf_result"] = spf_result

        parsed.records.append(row)
        cnt = int(row.get("count") or 1)
        dkim_align = str(row.get("dkim", "")).lower() == "pass"
        spf_align = str(row.get("spf", "")).lower() == "pass"
        dkim_auth = str(dkim_result or "").lower() == "pass"
        spf_auth = str(spf_result or "").lower() == "pass"
        if dkim_align or spf_align or (dkim_auth and spf_auth):
            parsed.pass_count += cnt
        else:
            parsed.fail_count += cnt
        if dkim_auth:
            parsed.dkim_pass += cnt
        else:
            parsed.dkim_fail += cnt
        if spf_auth:
            parsed.spf_pass += cnt
        else:
            parsed.spf_fail += cnt

    return parsed


def _read_xml_payload(path: Path) -> bytes:
    raw = path.read_bytes()
    if path.suffix.lower() == ".gz":
        return gzip.decompress(raw)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    return zf.read(name)
        raise ValueError("zip contains no xml")
    return raw


async def ingest_report_file(
    path: Path, domain_id: str, db: RepMonDatabase
) -> DmarcReport:
    """Load XML (plain/gzip/zip), parse, persist DmarcReport + DmarcRecords."""
    payload = _read_xml_payload(path)
    parsed = parse_dmarc_xml(payload)
    report = DmarcReport(
        domain_id=domain_id,
        report_id=parsed.report_id,
        org_name=parsed.org_name,
        date_begin=parsed.date_begin,
        date_end=parsed.date_end,
        pass_count=parsed.pass_count,
        fail_count=parsed.fail_count,
        dkim_pass=parsed.dkim_pass,
        dkim_fail=parsed.dkim_fail,
        spf_pass=parsed.spf_pass,
        spf_fail=parsed.spf_fail,
        raw_xml_path=str(path.resolve()),
        ingested_at=now_utc(),
    )
    await db.insert_dmarc_report(report)
    for rec in parsed.records:
        await db.insert_dmarc_record_row(
            DmarcRecord(
                report_id=report.id,
                source_ip=str(rec.get("source_ip") or ""),
                count=int(rec.get("count") or 0),
                disposition=str(rec.get("disposition") or ""),
                dkim_result=str(rec.get("dkim_result") or ""),
                spf_result=str(rec.get("spf_result") or ""),
                header_from=str(rec.get("header_from") or ""),
            )
        )
    return report
