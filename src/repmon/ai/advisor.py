"""Domain advisor — warmup plans and deliverability narratives."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import BlocklistResult, DnsSnapshot, WarmupPlan, WarmupStatus
from repmon._time import now_utc

logger = logging.getLogger(__name__)


DEFAULT_ADVISOR_PROMPT = """You are an email deliverability strategist. Produce conservative, evidence-based warming plans.

Return JSON with:
  "targets": [{"day": 1, "target_sends": 20}, ...],
  "guidance_md": "<markdown advice>",
  "confidence": <0-1>,
The targets must monotonically increase or plateau; never spike more than ~30% day-over-day unless justified."""


class DomainAdvisor:
    SYSTEM_PROMPT: str = DEFAULT_ADVISOR_PROMPT

    def __init__(self, config: RepMonConfig, keys: APIKeys) -> None:
        self.config = config
        self.client = anthropic.AsyncAnthropic(api_key=keys.anthropic or "dummy")
        self.model = config.ai.model
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        path_raw = self.config.ai.advisor_prompt_path
        if path_raw:
            path = Path(path_raw)
            if path.exists():
                return path.read_text(encoding="utf-8")
            logger.warning("Missing advisor prompt file: %s", path)
        return self.SYSTEM_PROMPT

    async def generate_warmup_plan(
        self, domain_name: str, domain_id: str
    ) -> WarmupPlan:
        wh = self.config.domain_health.warmup
        user = f"""Domain: {domain_name}
Day-1 volume: {wh.default_start_volume}
Ramp days: {wh.ramp_days}
Return JSON targets for each day 1..{wh.ramp_days}."""
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=min(self.config.ai.max_tokens, 2000),
            temperature=self.config.ai.temperature,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        targets = data.get("targets") or []
        guidance = str(data.get("guidance_md") or "")
        conf = float(data.get("confidence") or 0.7)
        if conf < self.config.ai.min_warmup_confidence:
            guidance = (
                guidance
                + "\n\n_Note: model confidence was below min_warmup_confidence — review manually._\n"
            )
        return WarmupPlan(
            domain_id=domain_id,
            start_date=now_utc(),
            target_daily_volume_json=json.dumps(targets),
            guidance_md=guidance,
            current_day=1,
            status=WarmupStatus.ACTIVE,
        )

    async def diagnose_deliverability(
        self,
        dns_snapshot: DnsSnapshot,
        blocklist_result: BlocklistResult,
        dmarc_summary_md: str,
    ) -> str:
        user = f"""Data:

DNS issues JSON: {dns_snapshot.issues_json}
SPF valid: {dns_snapshot.spf_valid}, DKIM valid: {dns_snapshot.dkim_valid}, DMARC valid: {dns_snapshot.dmarc_valid}

Blocklist listed_count: {blocklist_result.listed_count} / checked {blocklist_result.checked_count}

DMARC summary:
{dmarc_summary_md}

Write a concise Markdown diagnosis: what's wrong, what to fix, in order of impact."""
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=min(self.config.ai.max_tokens, 1500),
            temperature=0.2,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()
