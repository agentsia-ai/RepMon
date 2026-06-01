"""Shared fixtures — generic placeholders only (no product persona names)."""

from __future__ import annotations

import pytest

from repmon.config.loader import APIKeys, RepMonConfig


@pytest.fixture
def test_config() -> RepMonConfig:
    return RepMonConfig(
        client_name="Example Co",
        operator_name="Pat Operator",
        operator_title="Owner",
        operator_email="pat@example.com",
        agent_name="Reputation Assistant",
        agent_email="assistant@example.com",
    )


@pytest.fixture
def test_keys() -> APIKeys:
    return APIKeys()
