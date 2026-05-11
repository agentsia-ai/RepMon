# RepMon architecture

## Layers

1. **Sources** fetch or probe external signals (reviews, RSS, DNS, DNSBL, DMARC XML).
2. **CRM** persists `MonitoredDomain`, snapshots, mentions, alerts, warmup plans.
3. **Scoring** combines latest DNS + blocklist + rolling DMARC window with mention stats (no AI).
4. **AI seams** classify mentions, draft responses, explain deliverability / warmup (Anthropic).
5. **Service** orchestrates checks, scoring refresh, and publish interlock.
6. **MCP / CLI** expose the same operations to humans and agents.

## Data flow

```
Sources → RawMentionIngest / snapshots
       → MentionClassifier (optional per batch)
       → Mention rows + AlertRecord
       → ResponseDrafter (on demand)
       → approve_response → publish_response (token-guarded)
```

Domain health:

```
DnsChecker → DnsSnapshot
BlocklistChecker → BlocklistResult
DMARC ingest → DmarcReport + DmarcRecord
         → scoring.engine.compute_deliverability
```

## Async

All I/O uses `async`/`await` (aiosqlite, httpx, dnspython async resolver, Anthropic async client).
