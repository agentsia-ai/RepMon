"""Publishing guards — human approval required; no auto-send."""

from __future__ import annotations

import pytest

from repmon.config.loader import APIKeys, RepMonConfig
from repmon.service import publish_response


@pytest.mark.asyncio
async def test_publish_requires_approval_token_by_default(
    test_config: RepMonConfig,
    test_keys: APIKeys,
) -> None:
    assert test_config.outreach.require_approval is True
    assert test_config.outreach.auto_send is False
    with pytest.raises(ValueError, match="approval_token required"):
        await publish_response(
            db=None,  # type: ignore[arg-type]
            config=test_config,
            keys=test_keys,
            mention_id="m-1",
            approval_token="",
        )


@pytest.mark.asyncio
async def test_publish_rejects_auto_send_flag(test_config: RepMonConfig, test_keys: APIKeys) -> None:
    test_config.outreach.auto_send = True
    with pytest.raises(ValueError, match="auto_send must remain false"):
        await publish_response(
            db=None,  # type: ignore[arg-type]
            config=test_config,
            keys=test_keys,
            mention_id="m-1",
            approval_token="tok",
        )
