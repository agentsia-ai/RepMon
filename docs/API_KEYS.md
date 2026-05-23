# API keys and credentials

Secrets live in `.env` only (never in `config.yaml`).

| Integration | Env vars | Notes |
|-------------|----------|--------|
| **Anthropic** | `ANTHROPIC_API_KEY` | Required for classifier, drafter, advisor. |
| **Google Business Profile** | `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_OAUTH_TOKEN_PATH` | OAuth2 Desktop app JSON + cached refresh token; fetches reviews and posts approved replies. |
| **Yelp Fusion** | `YELP_API_KEY` | **Read-only** — Yelp does not expose public reply via this API; use RepMon to draft, then reply in Yelp UI. |
| **Trustpilot** | `TRUSTPILOT_API_KEY`, `TRUSTPILOT_BUSINESS_UNIT_ID` | Connector stub — fill when enabling. |
| **Reddit** | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | OAuth app; connector stub. |
| **Twitter / X** | `TWITTER_BEARER_TOKEN` | Free tier is limited; search volume may be capped. |
| **MXToolbox** | `MXTOOLBOX_API_KEY` | Optional; `mxtoolbox.py` is an abstraction stub. |
| **SMTP** | `SMTP_*` | Optional alerts / outbound. |

See each vendor’s developer docs for rotation and least-privilege keys.
