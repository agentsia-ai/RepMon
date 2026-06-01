"""Google Business Profile connector — OAuth + reviews.

Authentication: OAuth2 with a cached refresh token. On first use the
`google-auth-oauthlib` helper runs a local-server flow and opens a browser
for consent. The resulting token is persisted to `keys.google_oauth_token_path`
(default `./.google_oauth_token.json`, gitignored).

Scope: `business.manage` — read locations/reviews and post owner replies.

Reply publishing is gated by RepMon's service layer: `draft_response` stages
draft-only text (no email send), `approve_response` approves, and `publish_response`
calls `publish_reply` only after a valid approval token is presented.
RepMon never auto-sends email; platform posts require explicit operator approval.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.models import Mention, MentionKind, MentionSource, MonitoredDomain
from repmon.sources.base import MentionSourceConnector

logger = logging.getLogger(__name__)

GOOGLE_BUSINESS_SCOPES = ["https://www.googleapis.com/auth/business.manage"]

_STAR_TO_RATING = {
    "ONE": 1.0,
    "TWO": 2.0,
    "THREE": 3.0,
    "FOUR": 4.0,
    "FIVE": 5.0,
}


class GoogleBusinessSource(MentionSourceConnector):
    name = "google"

    async def fetch_recent(self, domain: MonitoredDomain, limit: int = 25) -> list[Mention]:
        """Fetch reviews when OAuth credentials are configured; otherwise return []."""
        if not self.keys.google_credentials_path:
            logger.debug("Google Business OAuth not configured; skipping fetch.")
            return []

        try:
            return await asyncio.to_thread(
                _fetch_recent_sync,
                self.keys.google_credentials_path,
                self.keys.google_oauth_token_path,
                domain,
                limit,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Google Business fetch failed for %s: %s", domain.domain, e)
            return []

    async def publish_reply(
        self,
        domain: MonitoredDomain,
        review_id: str,
        body: str,
    ) -> str:
        """Post an operator-approved reply to Google Reviews.

        Called only from `publish_response` after `approve_response` has
        assigned a valid approval token — never invoked directly for staging.
        """
        if not self.keys.google_credentials_path:
            raise RuntimeError(
                "GOOGLE_CREDENTIALS_PATH is not set; cannot publish Google review reply."
            )
        return await asyncio.to_thread(
            _publish_reply_sync,
            self.keys.google_credentials_path,
            self.keys.google_oauth_token_path,
            domain.domain,
            review_id,
            body,
        )


def _build_google_credentials(credentials_path: str, token_path: str) -> Any:
    """Build Google OAuth credentials. Performs the OAuth dance on first run."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_file = Path(token_path)
    creds: Any = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_file), GOOGLE_BUSINESS_SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path:
                raise RuntimeError(
                    "GOOGLE_CREDENTIALS_PATH is not set. Download OAuth client "
                    "credentials from Google Cloud Console and point "
                    "GOOGLE_CREDENTIALS_PATH at the JSON file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, GOOGLE_BUSINESS_SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Cached Google Business OAuth token at %s", token_file)

    return creds


def _build_google_services(credentials_path: str, token_path: str) -> tuple[Any, Any, Any]:
    from googleapiclient.discovery import build

    creds = _build_google_credentials(credentials_path, token_path)
    account_mgmt = build(
        "mybusinessaccountmanagement",
        "v1",
        credentials=creds,
        cache_discovery=False,
    )
    business_info = build(
        "mybusinessbusinessinformation",
        "v1",
        credentials=creds,
        cache_discovery=False,
    )
    reviews = build(
        "mybusiness",
        "v4",
        credentials=creds,
        cache_discovery=False,
        static_discovery=False,
        discoveryServiceUrl=(
            "https://developers.google.com/my-business/samples/"
            "mybusiness_google_rest_v4p9.json"
        ),
    )
    return account_mgmt, business_info, reviews


def _parse_rfc3339(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        normalized = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _location_matches_domain(location: dict[str, Any], fqdn: str) -> bool:
    needle = fqdn.lower().strip()
    if not needle:
        return True
    website = str(location.get("websiteUri") or location.get("websiteUrl") or "").lower()
    if needle in website:
        return True
    title = str(location.get("title") or "").lower()
    return needle in title


def _review_to_mention(domain: MonitoredDomain, review: dict[str, Any]) -> Mention:
    reviewer = review.get("reviewer") or {}
    star = review.get("starRating") or ""
    rating = _STAR_TO_RATING.get(str(star).upper())
    return Mention(
        domain_id=domain.id,
        source=MentionSource.GOOGLE,
        external_id=str(review.get("name") or ""),
        author=str(reviewer.get("displayName") or "Anonymous"),
        rating=rating,
        content=str(review.get("comment") or ""),
        mention_kind=MentionKind.REVIEW,
        url=str(review.get("reviewUrl") or ""),
        published_at=_parse_rfc3339(review.get("createTime")),
    )


def _list_locations(
    account_mgmt: Any,
    business_info: Any,
    domain: MonitoredDomain,
) -> list[dict[str, Any]]:
    accounts_resp = account_mgmt.accounts().list().execute()
    accounts = accounts_resp.get("accounts") or []
    locations: list[dict[str, Any]] = []

    for account in accounts:
        account_name = account.get("name")
        if not account_name:
            continue
        page_token: str | None = None
        while True:
            req = business_info.accounts().locations().list(
                parent=account_name,
                readMask="name,title,websiteUri",
                pageSize=100,
            )
            if page_token:
                req = req.pageToken(page_token)
            resp = req.execute()
            batch = resp.get("locations") or []
            for loc in batch:
                if _location_matches_domain(loc, domain.domain):
                    locations.append(loc)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    if not locations and accounts:
        logger.info(
            "No Google Business locations matched domain %s; fetching all accessible locations.",
            domain.domain,
        )
        for account in accounts:
            account_name = account.get("name")
            if not account_name:
                continue
            resp = (
                business_info.accounts()
                .locations()
                .list(
                    parent=account_name,
                    readMask="name,title,websiteUri",
                    pageSize=100,
                )
                .execute()
            )
            locations.extend(resp.get("locations") or [])

    return locations


def _fetch_recent_sync(
    credentials_path: str,
    token_path: str,
    domain: MonitoredDomain,
    limit: int,
) -> list[Mention]:
    account_mgmt, business_info, reviews_svc = _build_google_services(
        credentials_path, token_path
    )
    locations = _list_locations(account_mgmt, business_info, domain)
    out: list[Mention] = []

    for location in locations:
        location_name = location.get("name")
        if not location_name:
            continue
        page_token: str | None = None
        while len(out) < limit:
            req = reviews_svc.accounts().locations().reviews().list(
                parent=location_name,
                pageSize=min(50, limit - len(out)),
            )
            if page_token:
                req = req.pageToken(page_token)
            resp = req.execute()
            for review in resp.get("reviews") or []:
                out.append(_review_to_mention(domain, review))
                if len(out) >= limit:
                    break
            page_token = resp.get("nextPageToken")
            if not page_token or len(out) >= limit:
                break

    return out[:limit]


def _publish_reply_sync(
    credentials_path: str,
    token_path: str,
    domain_name: str,
    review_id: str,
    body: str,
) -> str:
    _, _, reviews_svc = _build_google_services(credentials_path, token_path)
    resp = (
        reviews_svc.accounts()
        .locations()
        .reviews()
        .updateReply(name=review_id, body={"comment": body})
        .execute()
    )
    reply = resp.get("comment") or body
    logger.info("Published Google review reply for domain=%s review=%s", domain_name, review_id)
    return str(reply)
