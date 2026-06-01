"""Response drafter for reviews and mentions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MonitoredDomain

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """You draft professional, empathetic public responses for a local business owner.
Write in first person as the owner (use the operator name from context). Never use an AI assistant,
bot, or agent persona name in customer-facing text.
Every response is reviewed before publishing — do not claim refunds or compensation unless explicitly stated in context.

Return ONLY JSON:
{"subject": "<email subject or empty>", "body": "<plain text body>"}"""


class ResponseDrafter:
    SYSTEM_PROMPT: str = DEFAULT_SYSTEM_PROMPT

    def __init__(self, config: RepMonConfig, keys: APIKeys) -> None:
        self.config = config
        self.client = anthropic.AsyncAnthropic(api_key=keys.anthropic or "dummy")
        self.model = config.ai.model
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        path_raw = self.config.ai.drafter_prompt_path
        if path_raw:
            path = Path(path_raw)
            if path.exists():
                return path.read_text(encoding="utf-8")
            logger.warning("Missing drafter prompt file: %s", path)
        return self.SYSTEM_PROMPT

    async def _call(self, user: str) -> tuple[str, str]:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=min(self.config.ai.max_tokens, 1200),
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
        return str(data.get("subject") or ""), str(data.get("body") or "")

    async def draft_review_response(
        self, domain: MonitoredDomain, mention: Mention
    ) -> tuple[str, str]:
        owner = (self.config.operator_name or "the business owner").strip()
        user = f"""Business: {domain.display_name or domain.domain}
Business owner (first-person voice): {owner}
Review from {mention.author or 'anonymous'} (rating {mention.rating!s}):
{mention.content}

Draft a public reply in first person as {owner}. Do not mention any AI agent or assistant by name.
"""
        return await self._call(user)

    async def draft_mention_response(
        self, domain: MonitoredDomain, mention: Mention
    ) -> tuple[str, str]:
        owner = (self.config.operator_name or "the business owner").strip()
        user = f"""Business: {domain.display_name or domain.domain}
Business owner (first-person voice): {owner}
Social mention ({mention.source.value}):
{mention.content}
URL: {mention.url}

Draft a public reply in first person as {owner}. Do not mention any AI agent or assistant by name.
"""
        return await self._call(user)

    async def draft_escalation_alert(
        self, domain: MonitoredDomain, summary: str
    ) -> tuple[str, str]:
        user = f"""Internal escalation note for ops about {domain.domain}:
{summary}
Write subject + body for operator email."""
        return await self._call(user)
