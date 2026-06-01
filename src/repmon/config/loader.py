"""RepMon configuration — YAML + environment. Secrets only in .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()


class AIConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.3
    max_tokens: int = 1000
    classifier_prompt_path: Optional[str] = None
    drafter_prompt_path: Optional[str] = None
    advisor_prompt_path: Optional[str] = None
    min_classification_confidence: float = 0.7
    min_warmup_confidence: float = 0.8


class BusinessConfig(BaseModel):
    name: str = ""
    timezone: str = "America/Chicago"
    domain: str = ""


class MonitoringConfig(BaseModel):
    check_interval_hours: int = 24
    dmarc_report_inbox: str = ""
    sentiment_alert_threshold: float = 0.3
    blocklist_alert_on_any: bool = True
    score_drop_alert_threshold: int = 10


class ReputationSourcesConfig(BaseModel):
    google_business: bool = True
    yelp: bool = True
    trustpilot: bool = False
    rss_feeds: list[str] = []
    reddit_keywords: list[str] = []
    twitter_keywords: list[str] = []


class ReputationConfig(BaseModel):
    sources: ReputationSourcesConfig = ReputationSourcesConfig()


class BlocklistsOverrideConfig(BaseModel):
    use_defaults: bool = True
    additional: list[str] = []


class WarmupDomainConfig(BaseModel):
    default_start_volume: int = 20
    ramp_days: int = 30


class DomainHealthConfig(BaseModel):
    dkim_selectors: list[str] = ["google"]
    blocklists: BlocklistsOverrideConfig = BlocklistsOverrideConfig()
    warmup: WarmupDomainConfig = WarmupDomainConfig()


class OutreachConfig(BaseModel):
    require_approval: bool = True
    auto_send: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_username: str = ""
    from_address: str = ""


class CrossEngineConfig(BaseModel):
    leadgen_db: Optional[str] = None
    propgen_db: Optional[str] = None


class DatabaseConfig(BaseModel):
    path: str = "./data/repmon.db"


class SchedulerConfig(BaseModel):
    timezone: str = "America/Chicago"
    run_checks_at: str = "06:00"


class ScoringConfig(BaseModel):
    deliverability_weight: float = 0.5
    reputation_weight: float = 0.5


class RepMonConfig(BaseModel):
    client_name: str = ""
    operator_name: str = ""
    operator_title: str = ""
    operator_email: str = ""
    agent_name: str = ""
    agent_email: str = ""
    business: BusinessConfig = BusinessConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    reputation: ReputationConfig = ReputationConfig()
    domain_health: DomainHealthConfig = DomainHealthConfig()
    outreach: OutreachConfig = OutreachConfig()
    cross_engine: CrossEngineConfig = CrossEngineConfig()
    ai: AIConfig = AIConfig()
    scoring: ScoringConfig = ScoringConfig()
    database: DatabaseConfig = DatabaseConfig()
    scheduler: SchedulerConfig = SchedulerConfig()


class APIKeys(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    anthropic: str = Field(default="", alias="ANTHROPIC_API_KEY")
    google_credentials_path: str = Field(default="", alias="GOOGLE_CREDENTIALS_PATH")
    google_oauth_token_path: str = Field(
        default="./.google_oauth_token.json", alias="GOOGLE_OAUTH_TOKEN_PATH"
    )
    yelp_api_key: str = Field(default="", alias="YELP_API_KEY")
    trustpilot_api_key: str = Field(default="", alias="TRUSTPILOT_API_KEY")
    trustpilot_business_unit_id: str = Field(
        default="", alias="TRUSTPILOT_BUSINESS_UNIT_ID"
    )
    reddit_client_id: str = Field(default="", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="repmon/0.1", alias="REDDIT_USER_AGENT")
    twitter_bearer_token: str = Field(default="", alias="TWITTER_BEARER_TOKEN")
    mxtoolbox_api_key: str = Field(default="", alias="MXTOOLBOX_API_KEY")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")

    @classmethod
    def from_env(cls) -> APIKeys:
        values: dict[str, Any] = {}
        for f in cls.model_fields.values():
            alias = f.alias
            if not alias:
                continue
            raw = os.getenv(alias)
            if raw is None or raw == "":
                continue
            values[alias] = raw
        return cls(**values)


def display_agent_name(config: RepMonConfig) -> str:
    """Agent-facing label for logs and MCP metadata.

    Productized deployments (e.g. agentsia-core) set config.agent_name.
    Standalone RepMon installs fall back to the engine name.
    """
    name = (config.agent_name or "").strip()
    return name or "repmon"


def format_review_signature(config: RepMonConfig) -> str:
    """Customer-facing sign-off for review replies (operator, never agent persona)."""
    name = (config.operator_name or "").strip()
    if not name:
        return ""
    title = (config.operator_title or "").strip()
    if title:
        return f"\n\n— {name}, {title}"
    return f"\n\n— {name}"


def load_config(config_path: str | Path | None = None) -> RepMonConfig:
    path = Path(config_path or os.getenv("CONFIG_PATH", "config.yaml"))
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Copy config.example.yaml to {path} and fill in your details."
        )
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return RepMonConfig(**raw)


def load_api_keys() -> APIKeys:
    return APIKeys.from_env()
