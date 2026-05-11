# MCP setup (Claude Desktop)

RepMon speaks **stdio** MCP — same pattern as SchedBot.

```json
{
  "mcpServers": {
    "repmon": {
      "command": "uv",
      "args": ["run", "repmon", "mcp"],
      "env": {
        "CONFIG_PATH": "/absolute/path/to/your/config.yaml"
      }
    }
  }
}
```

On Windows, point `CONFIG_PATH` at your checked-out `config.yaml`. Working directory should be the deployment folder so `./data/repmon.db` resolves.

## Tools

See `src/repmon/mcp_server/server.py` → `list_tools()` for the authoritative tool list (`get_dashboard`, `publish_response`, etc.).

**Guardrail:** `publish_response` requires a valid `approval_token` from `approve_response` when `outreach.require_approval` is true (default).
