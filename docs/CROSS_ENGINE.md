# Cross-engine reads (LeadGen + PropGen)

RepMon **does not** import `leadgen` or `propgen` Python packages. It opens sibling SQLite files read-only (`mode=ro&immutable=1`) with fixed `SELECT`s.

## Config

```yaml
cross_engine:
  leadgen_db: "../LeadGen/data/leadgen.db"
  propgen_db: "../PropGen/data/propgen.db"
```

## LeadGen contract

- **Table:** `leads`
- **Column:** `company_json` (JSON object)
- **Fields read:** `domain`, `website` (either normalized to a hostname)

Function: `fetch_lead_domains(config) -> list[str]`

## PropGen contract

- **Table:** `proposals`
- **Columns:** `client_email`, `status`
- **Rows:** `status IN ('sent','viewed','signed','accepted','drafted')`
- **Domain:** right-hand side of `client_email` after `@`

Function: `fetch_propgen_domains(config) -> list[str]`

## Failure behavior

Missing file, missing table, or schema drift → **empty list**; warning logged. RepMon never raises solely on cross-engine errors.
