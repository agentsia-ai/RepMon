"""Trustpilot — stub connector."""

from __future__ import annotations

import logging

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)


class TrustpilotSource(MentionSourceConnector):
    name = "trustpilot"

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        logger.debug("Trustpilot connector not yet implemented.")
        return []
