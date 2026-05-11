"""Default DNS blocklist zones aligned with common mail-tester style checks.

Each entry is checked against a *sending IP* using the classic reversed-octet
format, e.g. for 203.0.113.10 on zen.spamhaus.org:

    query = "10.113.0.203.zen.spamhaus.org"
    if query resolves to A record → listed; NXDOMAIN → clean

**Domain-only / RHSBL** lists use a different query shape (hostname or domain
left-to-right with a delimiter). RepMon's checker documents per-zone behavior;
`check` is "ip" (default) or "domain" for the domain/MX hostname form.

Spamhaus publishes separate zones (SBL, XBL, PBL, CSS) plus the composite ZEN.
We include the composite plus the explicit zones so operators can see *which*
Spamhaus list fired without deduplicating ZEN across the four.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CheckKind = Literal["ip", "domain"]


@dataclass(frozen=True)
class BlocklistZone:
    """One DNSBL zone definition."""

    list_name: str
    zone: str
    kind: CheckKind = "ip"


# Default set of 23 zones (names match common aggregated "mail tester" panels).
DEFAULT_BLOCKLIST_ZONES: tuple[BlocklistZone, ...] = (
    BlocklistZone("Spamhaus ZEN", "zen.spamhaus.org"),
    BlocklistZone("Spamhaus SBL", "sbl.spamhaus.org"),
    BlocklistZone("Spamhaus CSS", "css.spamhaus.org"),
    BlocklistZone("Spamhaus XBL", "xbl.spamhaus.org"),
    BlocklistZone("Spamhaus PBL", "pbl.spamhaus.org"),
    BlocklistZone("Barracuda", "b.barracudacentral.org"),
    BlocklistZone("SpamCop", "bl.spamcop.net"),
    BlocklistZone("SORBS aggregate", "dnsbl.sorbs.net"),
    BlocklistZone("SORBS spam", "spam.dnsbl.sorbs.net"),
    BlocklistZone("SORBS relay", "misc.dnsbl.sorbs.net"),
    BlocklistZone("Backscatterer", "ips.backscatterer.org"),
    BlocklistZone("Hostkarma", "hostkarma.junkemailfilter.com"),
    BlocklistZone("LashBack UBL", "ubl.lashback.com", "domain"),
    BlocklistZone("mailspike RBL", "rep.mailspike.net"),
    BlocklistZone("PSBL", "psbl.surriel.com"),
    BlocklistZone("RATS-All", "all.rbl.webiron.net"),
    BlocklistZone("SEM-BLACK", "bl.sem-fxp.com"),
    BlocklistZone("SEM-BACKSCATTER", "bl.score.senderscore.com"),
    BlocklistZone("GBUdb Truncate", "truncate.gbudb.net"),
    BlocklistZone("UCEPROTECT-1", "dnsbl-1.uceprotect.net"),
    BlocklistZone("SpamRATS Dyna", "dyna.spamrats.com"),
    BlocklistZone("SpamRATS NOPTR", "noptr.spamrats.com"),
    BlocklistZone("SpamRATS Spam", "spam.spamrats.com"),
)
