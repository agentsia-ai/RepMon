# Getting started

1. **Install**

   ```bash
   uv sync --extra dev
   ```

2. **Configure**

   ```bash
   cp config.example.yaml config.yaml
   cp .env.example .env
   ```

   Fill `operator_email`, `business.domain`, `database.path`, and optional `cross_engine.*` paths to sibling LeadGen / PropGen SQLite files.

3. **Initialize**

   ```bash
   uv run repmon pipeline
   uv run repmon add-domain yourdomain.com
   uv run repmon check yourdomain.com
   ```

4. **MCP**

   ```bash
   uv run repmon mcp
   ```

5. **DMARC file ingest**

   ```bash
   uv run repmon ingest-dmarc ./report.xml.gz --domain-id <uuid>
   ```

Use `repmon score <domain>` for the full JSON card. Prefix domain IDs work where unambiguous.
