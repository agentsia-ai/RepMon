"""MXToolbox API abstraction — optional supplementary blocklist checks."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from repmon.config.loader import APIKeys

logger = logging.getLogger(__name__)


class MXToolboxClient:
    def __init__(self, keys: APIKeys) -> None:
        self._api_key = keys.mxtoolbox_api_key

    async def blacklist_check(self, host: str) -> dict[str, Any] | None:
        if not self._api_key:
            logger.debug("MXToolbox API key unset")
            return None
        # Endpoint shapes vary by MXToolbox product tier — stub returns None.
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.debug("MXToolbox blacklist_check stub for %s", host)
            _ = client
        return None
