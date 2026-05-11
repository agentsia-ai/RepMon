"""Twitter / X mention search — stub."""

from __future__ import annotations

import logging

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)


class TwitterSource(MentionSourceConnector):
    name = "twitter"

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        logger.debug("Twitter/X connector stub — bearer token required.")
        return []
