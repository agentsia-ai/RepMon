"""RSS / Atom mention monitor via feedparser."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import feedparser

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MentionSource, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)


class RssSource(MentionSourceConnector):
    name = "rss"

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        feeds = self.config.reputation.sources.rss_feeds
        out: list[Mention] = []
        for url in feeds:
            try:
                parsed = await asyncio.to_thread(feedparser.parse, url)
            except Exception as e:  # noqa: BLE001
                logger.warning("RSS parse failed %s: %s", url, e)
                continue
            for ent in (parsed.entries or [])[:limit]:
                published = None
                if ent.get("published_parsed"):
                    try:
                        published = datetime(
                            *ent.published_parsed[:6], tzinfo=timezone.utc
                        )
                    except (TypeError, ValueError):
                        published = None
                out.append(
                    Mention(
                        domain_id=domain.id,
                        source=MentionSource.RSS,
                        external_id=str(ent.get("id") or ent.get("link") or ""),
                        author=str(ent.get("author") or ""),
                        content=str(ent.get("title") or "") + "\n" + str(ent.get("summary") or ""),
                        url=str(ent.get("link") or ""),
                        published_at=published,
                    )
                )
        return out[:limit]
