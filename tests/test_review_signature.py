"""Review draft signatures — operator identity, not agent persona."""

from __future__ import annotations

from repmon.config.loader import RepMonConfig, format_review_signature
from repmon.service import append_operator_signature


def test_format_review_signature_uses_operator_not_agent() -> None:
    config = RepMonConfig(
        operator_name="Pat Operator",
        operator_title="Owner",
        agent_name="Reputation Assistant",
    )
    sig = format_review_signature(config)
    assert "Pat Operator" in sig
    assert "Owner" in sig
    assert "Reputation Assistant" not in sig


def test_append_operator_signature_adds_sign_off() -> None:
    config = RepMonConfig(
        operator_name="Pat Operator",
        operator_title="Owner",
        agent_name="Reputation Assistant",
    )
    body = append_operator_signature(config, "Thanks for your feedback!")
    assert "Pat Operator" in body
    assert "Reputation Assistant" not in body
    assert body.startswith("Thanks for your feedback!")


def test_append_operator_signature_skips_duplicate() -> None:
    config = RepMonConfig(operator_name="Pat Operator", operator_title="")
    body = append_operator_signature(config, "Reply\n\n— Pat Operator")
    assert body.count("Pat Operator") == 1
