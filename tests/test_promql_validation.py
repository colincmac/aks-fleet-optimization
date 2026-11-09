from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import validate_promql


def test_pinned_tool_is_required_and_never_silently_skipped(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="promtool"):
        validate_promql.verify_tool(tmp_path / "missing.exe")


def test_pinned_tool_rejects_wrong_bytes_before_execution(tmp_path: Path) -> None:
    tool = tmp_path / "promtool.exe"
    tool.write_bytes(b"not the approved binary")
    with pytest.raises(RuntimeError, match="checksum"):
        validate_promql.verify_tool(tool)


def test_shared_verifier_requires_offline_promql_validation(tmp_path: Path) -> None:
    from scripts.verify import verification_commands

    assert any(
        "validate_promql.py" in " ".join(command) for command in verification_commands(tmp_path)
    )


def test_validation_runs_actual_pack_expressions_and_optional_recordings(tmp_path: Path) -> None:
    output = tmp_path / "promql"
    validate_promql.validate(output)
    receipt = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    assert receipt["tool_version"] == "3.16.0-rc.2"
    assert receipt["query_assets"] >= 9
    assert receipt["source_profiles"] == 2
    assert receipt["recording_files"] == 1
    assert receipt["status"] == "passed"
