# DMARC setup for operators

## What DMARC reports are

Receiving providers send **aggregate (rua) XML reports** describing SPF/DKIM alignment and disposition for mail claiming to be from your domain. They are the ground truth for authentication health.

## Configure `rua`

In your DMARC TXT record at `_dmarc.example.com`:

```txt
v=DMARC1; p=none; rua=mailto:dmarc@reports.example.com;
```

Use a mailbox you control; many operators use a dedicated subdomain and address.

## Feeding RepMon

1. Set `monitoring.dmarc_report_inbox` in `config.yaml` (documentation / ops cue).
2. Save aggregate attachments dropped to disk (gzip/zip/xml).
3. Ingest:

   ```bash
   uv run repmon ingest-dmarc ./corp.com!google.com!1700000000!1700086399.xml.gz --domain-id <uuid>
   ```

   Or call the MCP tool `ingest_dmarc_report`.

4. Use `repmon dmarc example.com` or MCP `get_dmarc_summary` for pass/fail trends.

## Policy rollout

- **`p=none`** — monitoring only; fix auth failures before tightening.  
- **`p=quarantine`** — gradual enforcement; watch fail spikes in RepMon alerts.  
- **`p=reject`** — strongest; only after stable pass rates.

The engine flags **valid DMARC with `p=none`** as a warning so you don’t mistake “valid DNS” for “protected domain.”
