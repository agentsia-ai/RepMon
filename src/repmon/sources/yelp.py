"""Yelp Fusion — read-only reviews (no reply API)."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MentionSource, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)


class YelpSource(MentionSourceConnector):
    name = "yelp"

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        if not self.keys.yelp_api_key:
            return []
        headers = {"Authorization": f"Bearer {self.keys.yelp_api_key}"}
        # Minimal search-by-keyword fallback — production maps business_id in config.
        term = quote(domain.display_name or domain.domain)
        url = f"https://api.yelp.com/v3/businesses/search?term={term}&limit=1"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                logger.debug("Yelp search failed: %s", r.status_code)
                return []
            data = r.json()
            businesses = data.get("businesses") or []
            if not businesses:
                return []
            bid = businesses[0].get("id")
            rev_url = f"https://api.yelp.com/v3/businesses/{bid}/reviews"
            r2 = await client.get(rev_url, headers=headers)
            if r2.status_code != 200:
                return []
            reviews = r2.json().get("reviews") or []
        out: list[Mention] = []
        for rv in reviews[:limit]:
            out.append(
                Mention(
                    domain_id=domain.id,
                    source=MentionSource.YELP,
                    external_id=str(rv.get("id") or ""),
                    author=str((rv.get("user") or {}).get("name") or ""),
                    rating=float(rv.get("rating") or 0) or None,
                    content=str(rv.get("text") or ""),
                    url=str(rv.get("url") or ""),
                )
            )
        return out
