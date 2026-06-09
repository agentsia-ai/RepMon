"""Reddit keyword monitor — stub."""

from __future__ import annotations

import logging

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)


class RedditSource(MentionSourceConnector):
    name = "reddit"

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        logger.debug("Reddit connector stub — configure OAuth via environment variables (Doppler in production, or a local .env in development) to enable.")
        return []
