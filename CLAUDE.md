# CLAUDE.md — RepMon

Read this before editing this repository.

## What this is

**RepMon** is the public, identity-free engine for reputation monitoring and domain/email health. Named personas (e.g. Echo in `agentsia-core`) subclass the three AI seams and inject classes into `repmon.mcp_server.server.main()`.

## Layout

- `src/repmon/models.py` — Pydantic v2 models (contract for all layers).
- `src/repmon/config/loader.py` — `RepMonConfig` + `APIKeys` (env-only secrets).
- `src/repmon/crm/database.py` — async SQLite (`RepMonDatabase`).
- `src/repmon/sources/` — connectors (Google, Yelp, RSS, DNS, blocklists, DMARC).
- `src/repmon/ai/` — `MentionClassifier`, `ResponseDrafter`, `DomainAdvisor`.
- `src/repmon/scoring/engine.py` — deterministic scores (no LLM).
- `src/repmon/mcp_server/server.py` — stdio MCP; **no `print()` to stdout**.
- `src/repmon/cli.py` — `repmon` CLI.

## MCP rules

- Stdout = JSON-RPC only; use `logging` or `Console(stderr=True)`.
- Pluggable globals: `MENTION_CLASSIFIER_CLASS`, `RESPONSE_DRAFTER_CLASS`, `DOMAIN_ADVISOR_CLASS`; `main()` accepts `*_cls` overrides.
- `publish_response` is the only outbound publish path; uses `approval_token` interlock like SchedBot reminders.

## Cross-engine

Read-only SQLite via `cross_engine.py` + [docs/CROSS_ENGINE.md](docs/CROSS_ENGINE.md). Never import `leadgen` / `propgen` packages.

## Testing

```bash
uv run ruff check src
uv run python -m compileall -q src
```
