"""Mention and DNS checker ABCs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MonitoredDomain


class MentionSourceConnector(ABC):
    """Pluggable inbound mention/review connector."""

    name: str = "base"

    def __init__(self, config: RepMonConfig, keys: APIKeys) -> None:
        self.config = config
        self.keys = keys

    @abstractmethod
    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        """Pull recent mentions for a monitored domain."""
        raise NotImplementedError


class DnsHealthChecker(ABC):
    """Optional extension point for custom DNS validation pipelines."""

    @abstractmethod
    async def check(self, domain: str, dkim_selectors: list[str]) -> dict[str, Any]:
        raise NotImplementedError
