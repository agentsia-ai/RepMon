# RepMon

> AGPL-licensed AI-powered **reputation monitoring** and **domain / email health** engine — reviews, DNS, blocklists, DMARC, and operator-approved responses.

Copyright © Artificial Intelligentsia, LLC d/b/a Agentsia. Licensed under [AGPL-3.0](LICENSE).

---

## What it does

- **Mission 1 — Reputation:** aggregate mentions and reviews (Google, Yelp, RSS; more connectors as stubs), classify sentiment, draft responses (never auto-published).
- **Mission 2 — Deliverability:** SPF/DKIM/DMARC checks, DNSBL screening, DMARC aggregate ingestion, deterministic deliverability scoring.
- **RepScore:** configurable blend of reputation + deliverability with transparent sub-scores.

---

## Quickstart

```bash
cd RepMon
uv sync --extra dev
cp .env.example .env
cp config.example.yaml config.yaml
uv run repmon pipeline
uv run repmon add-domain example.com
uv run repmon check example.com
uv run repmon mcp
```

See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

---

## Architecture

Engine layout mirrors [SchedBot](https://github.com/agentsia-ai/SchedBot): `src/repmon/` package, async SQLite CRM, YAML + `.env` split, stdio MCP server, Click CLI.

Persona subclasses (e.g. Agentsia **Echo**) live in `agentsia-core` and inject `MentionClassifier`, `ResponseDrafter`, and `DomainAdvisor` at MCP startup.

---

## License

AGPL-3.0 — see [LICENSE](LICENSE).
