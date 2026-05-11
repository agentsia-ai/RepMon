"""Concurrent DNSBL lookups via dnspython."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from typing import Any

import dns.asyncresolver
import dns.exception

from repmon._time import now_utc
from repmon.config.loader import RepMonConfig
from repmon.models import BlocklistResult
from repmon.sources.blocklists import DEFAULT_BLOCKLIST_ZONES, BlocklistZone

logger = logging.getLogger(__name__)


def _reverse_ipv4(ip: str) -> str:
    parts = ip.strip().split(".")
    if len(parts) != 4:
        raise ValueError("not ipv4")
    return ".".join(reversed(parts))


async def _listed_on_zone_ip(ip: str, zone: BlocklistZone) -> tuple[bool, str]:
    try:
        qname = f"{_reverse_ipv4(ip)}.{zone.zone}"
        await dns.asyncresolver.resolve(qname, "A")
        return True, "a_record"
    except dns.exception.NXDOMAIN:
        return False, "nxdomain"
    except dns.exception.NoAnswer:
        return False, "no_answer"
    except (dns.exception.DNSException, OSError, ValueError) as e:
        logger.debug("DNSBL %s for %s: %s", zone.list_name, ip, e)
        return False, f"error:{e!s}"


async def _listed_on_zone_domain(domain: str, zone: BlocklistZone) -> tuple[bool, str]:
    d = domain.lower().strip().rstrip(".")
    qname = f"{d}.{zone.zone}"
    try:
        await dns.asyncresolver.resolve(qname, "A")
        return True, "a_record"
    except dns.exception.NXDOMAIN:
        return False, "nxdomain"
    except dns.exception.NoAnswer:
        return False, "no_answer"
    except (dns.exception.DNSException, OSError) as e:
        return False, f"error:{e!s}"


async def _mx_ipv4s(hostname: str) -> list[str]:
    out: list[str] = []
    try:
        a_ans = await dns.asyncresolver.resolve(hostname, "A")
        for rrset in a_ans:
            for rdata in rrset:
                out.append(str(rdata))
    except (dns.exception.DNSException, OSError):
        pass
    return out


async def check_domain(
    domain_id: str,
    domain: str,
    ip: str | None,
    config: RepMonConfig,
) -> BlocklistResult:
    """Run configured blocklist set against `ip` (or first MX IPv4)."""

    zones: list[BlocklistZone] = []
    if config.domain_health.blocklists.use_defaults:
        zones.extend(DEFAULT_BLOCKLIST_ZONES)
    for z in config.domain_health.blocklists.additional:
        zones.append(BlocklistZone(z, z, "ip"))

    ips: list[str] = []
    if ip:
        try:
            ips.append(str(ipaddress.ip_address(ip.strip())))
        except ValueError:
            logger.warning("Invalid IP for blocklist check: %s", ip)

    if not ips:
        try:
            ans = await dns.asyncresolver.resolve(domain, "MX")
            hosts: list[tuple[int, str]] = []
            for rrset in ans:
                for rdata in rrset:
                    hosts.append((int(rdata.preference), str(rdata.exchange).rstrip(".")))
            hosts.sort(key=lambda x: x[0])
            if hosts:
                ips.extend(await _mx_ipv4s(hosts[0][1]))
        except (dns.exception.DNSException, OSError) as e:
            logger.debug("Could not resolve MX IP for %s: %s", domain, e)

    tasks: list[Any] = []
    meta: list[tuple[BlocklistZone, str | None]] = []

    async def _const(res: tuple[bool, str]) -> tuple[bool, str]:
        return res

    for zone in zones:
        if zone.kind == "domain":
            tasks.append(_listed_on_zone_domain(domain, zone))
            meta.append((zone, None))
        elif not ips:
            meta.append((zone, None))
            tasks.append(_const((False, "no_ip_to_check")))
        else:
            for chk in ips:
                tasks.append(_listed_on_zone_ip(chk, zone))
                meta.append((zone, chk))

    raw = await asyncio.gather(*tasks)
    results: list[dict] = []
    listed_count = 0
    checked_count = 0
    for (zone, chk_ip), (listed, detail) in zip(meta, raw, strict=True):
        checked_count += 1
        if listed:
            listed_count += 1
        row: dict = {"list_name": zone.list_name, "listed": listed, "detail": detail}
        if chk_ip:
            row["ip"] = chk_ip
        results.append(row)

    return BlocklistResult(
        domain_id=domain_id,
        checked_at=now_utc(),
        listed_count=listed_count,
        checked_count=max(checked_count, 1),
        results_json=json.dumps(results),
    )
