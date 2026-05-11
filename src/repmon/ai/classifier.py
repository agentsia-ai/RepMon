"""Mention classifier — reviews and social text."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import ClassificationResult, MentionKind, Sentiment

logger = logging.getLogger(__name__)


DEFAULT_CLASSIFIER_PROMPT = """You classify inbound customer reviews and social mentions.

Return ONLY valid JSON:
{
  "kind": "review|mention|complaint|compliment|question|spam",
  "sentiment": "positive|neutral|negative|urgent",
  "sentiment_score": <float 0.0-1.0, higher = more positive>,
  "urgency": <true|false>,
  "confidence": <0-1>,
  "reasoning": "<short>"
}

If confidence is low, still return best-effort fields; the engine may neutralize."""


class MentionClassifier:
    SYSTEM_PROMPT: str = DEFAULT_CLASSIFIER_PROMPT

    def __init__(self, config: RepMonConfig, keys: APIKeys) -> None:
        self.config = config
        self.client = anthropic.AsyncAnthropic(api_key=keys.anthropic or "dummy")
        self.model = config.ai.model
        self.min_confidence = config.ai.min_classification_confidence
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        path_raw = self.config.ai.classifier_prompt_path
        if path_raw:
            path = Path(path_raw)
            if path.exists():
                return path.read_text(encoding="utf-8")
            logger.warning("Missing classifier prompt file: %s", path)
        return self.SYSTEM_PROMPT

    def _user_prompt(self, text: str, source: str = "") -> str:
        return f"""Source hint: {source or "unknown"}
Text:
---
{text.strip()}
---
Return only JSON."""

    async def classify(self, text: str, source: str = "") -> ClassificationResult:
        prompt = self._user_prompt(text, source=source)
        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=min(self.config.ai.max_tokens, 600),
                temperature=self.config.ai.temperature,
                system=self._system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
            data = _parse_json_loosely(raw)
            conf = float(data.get("confidence", 0) or 0)
            sentiment = _coerce_sentiment(data.get("sentiment"))
            score = float(data.get("sentiment_score", 0.5) or 0.5)
            kind = _coerce_kind(data.get("kind"))
            if conf < self.min_confidence:
                sentiment = Sentiment.NEUTRAL
                score = 0.5
            return ClassificationResult(
                kind=kind,
                sentiment=sentiment,
                sentiment_score=max(0.0, min(1.0, score)),
                urgency=bool(data.get("urgency")),
                confidence=conf,
                reasoning=str(data.get("reasoning") or ""),
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Classification failed: %s", e)
            return ClassificationResult(
                reasoning=str(e),
            )


def _parse_json_loosely(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _coerce_sentiment(raw: object) -> Sentiment:
    try:
        return Sentiment(str(raw).lower().strip())
    except ValueError:
        return Sentiment.NEUTRAL


def _coerce_kind(raw: object) -> MentionKind:
    try:
        return MentionKind(str(raw).lower().strip())
    except ValueError:
        return MentionKind.MENTION
