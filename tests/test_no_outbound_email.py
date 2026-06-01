"""Confirm RepMon has no outbound SMTP send implementation."""

from __future__ import annotations

import ast
from pathlib import Path


def test_no_aiosmtplib_send_in_source_tree() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "repmon"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "send":
                    base = ast.unparse(func.value) if hasattr(ast, "unparse") else ""
                    if "aiosmtplib" in base or base.endswith("smtp"):
                        offenders.append(f"{path}:{node.lineno}")
    assert offenders == []
