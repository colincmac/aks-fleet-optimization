from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement

from scripts import verify

ROOT = Path(__file__).resolve().parents[1]


def test_schema_check_reports_missing_artifacts_without_creating_them(tmp_path: Path) -> None:
    output = tmp_path / "schemas"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_schemas.py"),
            "--check",
            "--output-dir",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert not output.exists()
    assert "fleet-snapshot.schema.json" in result.stdout


def test_schema_check_does_not_repair_stale_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "schemas"
    output.mkdir()
    artifact = output / "fleet-snapshot.schema.json"
    artifact.write_text("{}\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_schemas.py"),
            "--check",
            "--output-dir",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert artifact.read_text(encoding="utf-8") == "{}\n"


def test_schema_generation_and_check_support_explicit_paths(tmp_path: Path) -> None:
    output = tmp_path / "artifacts with spaces"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "generate_schemas.py"),
        "--output-dir",
        str(output),
    ]
    subprocess.run(command, cwd=tmp_path, check=True)
    before = {path.name: path.read_bytes() for path in output.glob("*.json")}
    assert set(before) == {
        "history-run.schema.json",
        "history-trend.schema.json",
        "cost-import.schema.json",
        "cost-reconciliation.schema.json",
        "operator-catalog.schema.json",
        "operator-inspection.schema.json",
        "execution-preview.schema.json",
        "source-profile.schema.json",
        "source-capabilities.schema.json",
        "metric-query-plan.schema.json",
        "recommendation-pack.schema.json",
        "query-export.schema.json",
        "analysis-config.schema.json",
        "fleet-snapshot.schema.json",
        "analysis-report.schema.json",
        "onboarding-config.schema.json",
        "readiness-report.schema.json",
        "azure-inventory.schema.json",
        "kubernetes-metadata.schema.json",
        "prometheus-metrics.schema.json",
        "assessment-fragments.schema.json",
        "offline-assessment.schema.json",
        "collection-plan.schema.json",
    }
    subprocess.run([*command, "--check"], cwd=tmp_path, check=True)
    assert before == {path.name: path.read_bytes() for path in output.glob("*.json")}


def test_verification_commands_share_interpreter_and_read_only_schema_gate(tmp_path: Path) -> None:
    commands = verify.verification_commands(tmp_path)
    assert all(command[0] == sys.executable for command in commands)
    assert [sys.executable, "-m", "ruff", "check", "."] in commands
    assert [sys.executable, "-m", "ruff", "format", "--check", "."] in commands
    assert [sys.executable, "-m", "mypy", "src", "scripts"] in commands
    schema = next(command for command in commands if "generate_schemas.py" in " ".join(command))
    assert "--check" in schema
    operator = next(
        command for command in commands if "generate_operator_catalog.py" in " ".join(command)
    )
    assert "--check" in operator
    assert any("pytest" in command for command in commands)
    smoke_commands = [command for command in commands if "aks_fleet_efficiency.cli" in command]
    assert len(smoke_commands) == 2
    assert {command[command.index("--format") + 1] for command in smoke_commands} == {
        "json",
        "markdown",
    }
    assert all("--as-of" in command for command in smoke_commands)


def test_verification_stops_at_first_failing_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["cwd"] == ROOT
        assert kwargs["check"] is True
        raise subprocess.CalledProcessError(17, command)

    monkeypatch.setattr(verify.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError) as error:
        verify.run_verification(tmp_path)
    assert error.value.returncode == 17
    assert len(calls) == 1


def test_verification_main_preserves_failure_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(output_dir: Path) -> None:
        raise subprocess.CalledProcessError(17, ["synthetic-check"])

    monkeypatch.setattr(verify, "run_verification", fail)
    assert verify.main(["--output-dir", str(tmp_path)]) == 17


def test_report_comparison_uses_structured_json(tmp_path: Path) -> None:
    reference = tmp_path / "source.json"
    installed = tmp_path / "wheel.json"
    reference.write_text('{"recommendations": [], "schema_version": "2.0"}', encoding="utf-8")
    installed.write_text('{"schema_version":"2.0","recommendations":[]}', encoding="utf-8")
    verify.compare_reports(reference, installed, structured=True)
    installed.write_text('{"schema_version":"2.0","recommendations":[{}]}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="Report differs"):
        verify.compare_reports(reference, installed, structured=True)


def test_report_comparison_tolerates_platform_line_endings_only(tmp_path: Path) -> None:
    reference = tmp_path / "expected.md"
    installed = tmp_path / "actual.md"
    reference.write_bytes(b"# Report\n\nBlocked findings: 5\n")
    installed.write_bytes(b"# Report\r\n\r\nBlocked findings: 5\r\n")
    verify.compare_reports(reference, installed)
    installed.write_text("# Report\n\nBlocked findings: 0\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Report differs"):
        verify.compare_reports(reference, installed)


def test_make_verify_uses_the_shared_runner() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "PYTHON ?= python" in makefile
    assert "verify:\n\t$(PYTHON) scripts/verify.py" in makefile


def test_ci_runs_the_shared_verifier_on_windows_and_linux() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["verify"]
    assert set(job["strategy"]["matrix"]["os"]) == {"ubuntu-latest", "windows-latest"}
    assert job["runs-on"] == "${{ matrix.os }}"
    commands = [step["run"] for step in job["steps"] if "run" in step]
    assert len([command for command in commands if "scripts/verify.py" in command]) == 1
    assert not any("ruff check" in command or "pytest " in command for command in commands)
    assert any(".[dev,kubernetes]" in command for command in commands)


def test_ci_action_references_are_immutable() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    references = [step["uses"] for step in workflow["jobs"]["verify"]["steps"] if "uses" in step]
    assert references
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in references)


def test_offline_wheel_build_tools_are_declared() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    development = project["project"]["optional-dependencies"]["dev"]
    names = {Requirement(dependency).name for dependency in development}
    assert {"build", "setuptools", "wheel"} <= names


def test_assessment_verification_uses_same_arguments_and_checks_partial_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    shapes: list[str] = []
    memory_shapes: list[str] = []
    cpu_shapes: list[str] = []
    source_shapes: list[object] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        partial = any(
            name in " ".join(command)
            for name in [
                "pool-assessment-partial.json",
                "workload-assessment.json",
                "history-assessment.json",
                "scoped-assessment.json",
                "azure-fragments-assessment.json",
                "replica-inventory-assessment.json",
                "memory-assessment.json",
                "autoscalers-assessment.json",
                "hpa-history-assessment.json",
                "keda-assessment.json",
                "replica-floor-assessment.json",
                "vpa-bounds-assessment.json",
                "memory-envelope-assessment.json",
                "memory-limit-assessment.json",
                "memory-context-assessment.json",
                "ordinary-source-assessment.json",
            ]
        )
        return subprocess.CompletedProcess(command, 3 if partial else 0, stdout="{}")

    monkeypatch.setattr(verify.subprocess, "run", run)
    monkeypatch.setattr(verify, "compare_reports", lambda *args, **kwargs: None)
    monkeypatch.setattr(verify, "_verify_autoscaler_shape", lambda case, value: shapes.append(case))
    monkeypatch.setattr(
        verify, "_verify_memory_shape", lambda case, value: memory_shapes.append(case)
    )
    monkeypatch.setattr(
        verify, "_verify_cpu_pack_shape", lambda case, value: cpu_shapes.append(case)
    )
    monkeypatch.setattr(verify, "_verify_source_shape", lambda value: source_shapes.append(value))
    verify._verify_assessments(tmp_path, "source", ["source-python"])
    verify._verify_assessments(tmp_path, "wheel", ["installed-cli"])
    assert len(calls) == 80
    assert [command[1:] for command in calls[:40]] == [command[1:] for command in calls[40:]]
    assert shapes == ["keda", "replica-floor", "vpa-bounds"] * 2
    assert memory_shapes == ["memory-envelope", "memory-limit", "memory-context"] * 2
    assert cpu_shapes == ["cpu-pack-baseline", "cpu-pack-guarded"] * 2
    assert len(source_shapes) == 4
    assert all("--as-of" in command for command in calls)
