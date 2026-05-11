"""Google Business Profile connector (OAuth + reviews) — scaffold."""

from __future__ import annotations

import logging

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MentionSource, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)


class GoogleBusinessSource(MentionSourceConnector):
    name = "google"

    def __init__(self, config: RepMonConfig, keys: APIKeys) -> None:
        super().__init__(config, keys)

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        """Fetch reviews when OAuth token is configured; otherwise return []."""
        if not self.keys.google_oauth_client_id:
            logger.debug("Google Business OAuth not configured; skipping fetch.")
            return []
        # Deployment wires token refresh + Locations API; engine stays generic.
        return []

    async def publish_reply(
        self,
        domain: MonitoredDomain,
        review_id: str,
        body: str,
    ) -> str:
        """Post approved reply to Google — stub until OAuth send path is wired."""
        logger.info(
            "Google publish_reply stub: domain=%s review_id=%s",
            domain.domain,
            review_id,
        )
        return f"stub:{review_id}"
