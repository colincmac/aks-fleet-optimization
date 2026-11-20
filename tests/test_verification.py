from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_history import TENANT, write_run

from aks_fleet_efficiency.history import HistoryStore, summarize_fleet_artifacts
from scripts import verify

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_history_example_replays_with_first_release_versions() -> None:
    from uuid import UUID

    from aks_fleet_efficiency.history import _read_verified_archive

    _, assessment, config = _read_verified_archive(
        ROOT / "history-example", tenant_id=UUID("00000000-0000-0000-0000-000000000000")
    )
    assert assessment.report.pack_provenance
    assert {pack.version for pack in assessment.report.pack_provenance} == {"1.0.0"}
    assert len(config.pack_locks) == 24
    assert "AKS-START-001" not in config.pack_locks


def test_cost_review_verifier_checks_original_scope_and_decimal_order(tmp_path: Path) -> None:
    originals = write_run(tmp_path, "original", as_of=datetime.fromisoformat(verify.REPLAY_TIME))
    verify._verify_cost_review_order(
        tmp_path,
        "source",
        [sys.executable, "-m", "aks_fleet_efficiency.cli"],
        originals,
        cwd=ROOT,
        env=None,
    )
    result = json.loads((tmp_path / "source-cluster-cost-review.json").read_text())
    assert len(result["rows"]) == 2
    assert Decimal(result["rows"][0]["allocated_amount"]) == Decimal("200")
    assert result["engineering_order_changed"] is False
    assert result["estimated_monthly_savings"] is None


def test_ai_handoff_verifier_preserves_summary_and_withholds_unproven_measurements(
    tmp_path: Path,
) -> None:
    from aks_fleet_efficiency.artifacts import write_assessment_artifacts
    from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
    from aks_fleet_efficiency.config import load_onboarding_config

    fragments = AssessmentFragments.model_validate_json(
        (ROOT / "examples/fixtures/history-assessment.json").read_text(encoding="utf-8")
    )
    profile = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml")
    result = assess_fragments(fragments, profile, as_of=datetime.fromisoformat(verify.REPLAY_TIME))
    originals = tmp_path / "original"
    write_assessment_artifacts(originals, fragments, result, profile.analysis)
    verify._verify_ai_export(
        tmp_path,
        "source",
        [sys.executable, "-m", "aks_fleet_efficiency.cli"],
        originals,
        cwd=ROOT,
        env=None,
    )
    package = json.loads((tmp_path / "source-ai-measurements.json").read_text())
    summary = json.loads((tmp_path / "source-ai-package.json").read_text())
    assert package["summary"] == summary
    assert package["measurements"]
    assert all(
        item["status"] == "withheld" and item["value"] is None for item in package["measurements"]
    )
    experiment = json.loads((tmp_path / "source-ai-experiment.json").read_text())
    assert experiment["state"] == "unverified_experiment"
    assert experiment["execution_authority"] == "none"


def test_supplied_evidence_verifier_checks_canonical_unverified_reviews(tmp_path: Path) -> None:
    verify._verify_supplied_evidence_reviews(
        tmp_path,
        "source",
        [sys.executable, "-m", "aks_fleet_efficiency.cli"],
        cwd=ROOT,
        env=None,
    )
    history = json.loads((tmp_path / "source-node-history-review.json").read_text())
    policy = json.loads((tmp_path / "source-nap-policy-review.json").read_text())
    assert history["cpu_p95_mcpu"] == 1000.0
    assert history["source_admission"] == "unverified_saved_contributions"
    assert policy["reasons"]["Empty"]["configured_limit"] == 1
    assert policy["controller_admission"] == "unverified"
    daemonsets = json.loads((tmp_path / "source-daemonset-review.json").read_text())
    storage = json.loads((tmp_path / "source-storage-review.json").read_text())
    assert len(daemonsets["comparisons"]) == 2
    assert daemonsets["fit_status"] == storage["fit_status"] == "blocked"
    assert storage["source_issues"]


def test_ci_verifies_required_python_runtimes_with_distinct_artifacts() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["verify"]
    assert job["strategy"]["fail-fast"] is False
    matrix = job["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-latest", "windows-latest"]
    assert matrix.get("python") == ["3.15"]
    assert "include" not in matrix and "exclude" not in matrix
    assert "continue-on-error" not in job
    steps = job["steps"]
    setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "${{ matrix.python }}"
    installation = next(step for step in steps if "pip install" in step.get("run", ""))
    assert installation["env"]["PYYAML_FORCE_LIBYAML"] == "0"
    verification = next(
        step for step in steps if step.get("name") == "Verify source and installed wheel"
    )
    assert "python scripts/verify.py" in verification["run"]
    assert "--quick" not in verification["run"]
    artifact = next(
        step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    artifact_name = artifact["with"]["name"]
    names = {
        artifact_name.replace("${{ matrix.os }}", operating_system).replace(
            "${{ matrix.python }}", version
        )
        for operating_system in matrix["os"]
        for version in matrix["python"]
    }
    assert len(names) == 2
    assert artifact["if"] == "always()"
    assert artifact["with"]["retention-days"] == 7
    for step in steps:
        if "uses" in step:
            revision = step["uses"].rsplit("@", 1)[1]
            assert len(revision) == 40
            int(revision, 16)


def test_pack_replay_runner_reuses_locked_configuration_and_rejects_changed_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aks_fleet_efficiency.collectors.fixture import FixtureCollector
    from aks_fleet_efficiency.config import AdvisorConfig
    from aks_fleet_efficiency.reporting.markdown import render_markdown
    from aks_fleet_efficiency.rules.engine import analyze

    report = analyze(
        FixtureCollector(ROOT / "examples/fixtures/capacity-review-snapshot.json").collect(),
        AdvisorConfig(packs=["AKS-NP-002"]),
        as_of=datetime.fromisoformat(verify.REPLAY_TIME),
    )
    calls = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        configuration = json.loads(Path(command[command.index("--config") + 1]).read_text())
        assert configuration["packs"] == ["AKS-NP-002"]
        if len(calls) > 1:
            assert configuration["pack_locks"]
        output_format = command[command.index("--format") + 1]
        output = (
            render_markdown(report) if output_format == "markdown" else report.model_dump_json()
        )
        if len(calls) == 3:
            changed = report.model_dump(mode="json")
            changed["summary"]["pack_subject_counts"]["AKS-NP-002"] += 1
            output = json.dumps(changed)
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(verify.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="locked replay"):
        verify._verify_pack_replay(
            tmp_path,
            "synthetic",
            ["synthetic-installed-cli"],
            "capacity-review",
            "AKS-NP-002",
            "baseline",
            cwd=ROOT,
            env=None,
            golden=False,
        )
    assert len(calls) == 3


@pytest.mark.parametrize("corrupt", [False, True])
def test_history_verifier_checks_stateless_store_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt: bool
) -> None:
    previous = write_run(tmp_path, "previous", as_of=datetime.fromisoformat(verify.REPLAY_TIME))
    current = write_run(tmp_path, "current")
    store = HistoryStore(tmp_path / "expected", tenant_id=TENANT)
    previous_run = store.import_assessment(previous)
    current_run = store.import_assessment(current)
    trend = store.compare(previous_run.run_id, current_run.run_id)
    fleet = summarize_fleet_artifacts(
        [(previous, "synthetic-peer"), (current, "synthetic-peer")], tenant_id=TENANT
    )
    comparisons = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["cwd"] == ROOT
        arguments = command[1:]
        if arguments[0] == "assess":
            return subprocess.CompletedProcess(command, 3, "{}", "")
        if arguments[0] == "compare":
            comparisons.append(command)
            payload = trend.model_dump(mode="json") | {"comparable": not corrupt}
            output = json.dumps(payload)
        elif arguments[:2] == ["history", "import"]:
            source = arguments[arguments.index("--artifacts") + 1]
            output = (previous_run if source == str(previous) else current_run).model_dump_json()
        elif arguments[:2] == ["history", "list"]:
            output = json.dumps(
                [previous_run.model_dump(mode="json"), current_run.model_dump(mode="json")]
            )
        elif arguments[:2] == ["history", "compare"]:
            output = trend.model_dump_json()
        elif arguments[:2] == ["fleet", "trends"]:
            output = fleet.model_dump_json()
        else:
            pytest.fail(f"Unexpected verifier command: {arguments}")
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(verify.subprocess, "run", run)
    executable = ["synthetic-installed-cli"]
    if corrupt:
        with pytest.raises(RuntimeError, match="Stateless"):
            verify._verify_history(tmp_path, "source", executable, previous, cwd=ROOT, env=None)
    else:
        verify._verify_history(tmp_path, "source", executable, previous, cwd=ROOT, env=None)
        assert comparisons
        assert json.loads(
            (tmp_path / "source-history-stateless-trend.json").read_text()
        ) == json.loads((tmp_path / "source-history-trend.json").read_text())


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("indent", ["", "    "])
def test_documentation_commands_support_crlf_and_list_indented_fences(
    newline: str, indent: str
) -> None:
    text = newline.join(
        [
            "1. Run the saved example:",
            f"{indent}```powershell",
            f"{indent}aks-fleet-advisor reconcile-costs `",
            f"{indent}  --costs examples/fixtures/cost-import.json",
            f"{indent}```",
        ]
    )
    assert verify.documentation_commands(text, expected_blocks=1) == [
        ["aks-fleet-advisor", "reconcile-costs", "--costs", "examples/fixtures/cost-import.json"]
    ]


@pytest.mark.parametrize(
    "text,expected_blocks",
    [
        ("No matching command blocks", 1),
        ("", 0),
        ("```powershell\naks-fleet-advisor reconcile-costs", 1),
        ("```powershell\naks-fleet-advisor reconcile-costs `\n```", 1),
        ("```powershell\naks-fleet-advisor reconcile-costs\n```", 2),
        ("```powershell\naks-fleet-advisor reconcile-costs --costs examples\fixtures.json\n```", 1),
        ("```powershell\naks-fleet-advisor reconcile-costs --costs examples\rixtures.json\n```", 1),
        ("```powershell\naks-fleet-advisor project-costs `\neviewed-file.json `\n```", 1),
    ],
)
def test_documentation_commands_reject_corruption_and_empty_validation(
    text: str, expected_blocks: int
) -> None:
    with pytest.raises(ValueError):
        verify.documentation_commands(text, expected_blocks=expected_blocks)


@pytest.mark.parametrize(
    "relative,blocks,exits",
    [
        ("docs/cost-reconciliation.md", 2, [0, 0]),
        ("docs/tutorials/reconcile-existing-cost-evidence.md", 4, [0, 3, 0, 0, 0, 3]),
    ],
)
def test_documented_financial_commands_replay_with_honest_status_and_null_savings(
    tmp_path: Path, relative: str, blocks: int, exits: list[int]
) -> None:
    commands = verify.documentation_commands(
        (ROOT / relative).read_bytes().decode("utf-8"), expected_blocks=blocks
    )
    assert len(commands) == len(exits)
    for arguments, expected_exit in zip(commands, exits, strict=True):
        resolved = [
            str(ROOT / value) if value.startswith("examples/") else value for value in arguments[1:]
        ]
        result = subprocess.run(
            [sys.executable, "-m", "aks_fleet_efficiency.cli", *resolved],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected_exit, result.stderr
        output = tmp_path / arguments[arguments.index("--output") + 1]
        evidence = json.loads(output.read_text(encoding="utf-8"))
        if arguments[1] == "reconcile-costs":
            assert evidence["estimated_monthly_savings"] is None
            assert Decimal(evidence["currencies"][0]["total"]) == Decimal("100")
            expected_status = (
                "blocked"
                if "focus" in output.name
                else "attributed"
                if "actual" in output.name
                else "reconciled"
            )
            assert evidence["status"] == expected_status


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
        "ai-evidence-package.schema.json",
        "ai-resource-evidence-package.schema.json",
        "ai-explanation-draft.schema.json",
        "ai-explanation.schema.json",
        "ai-review-intent.schema.json",
        "ai-checklist-draft.schema.json",
        "ai-checklist.schema.json",
        "ai-experiment-intent.schema.json",
        "ai-experiment-draft.schema.json",
        "ai-experiment.schema.json",
        "fleet-insight.schema.json",
        "fleet-context.schema.json",
        "fleet-context-review.schema.json",
        "historical-node-evidence.schema.json",
        "historical-node-review.schema.json",
        "fleet-history-trend.schema.json",
        "history-run.schema.json",
        "history-trend.schema.json",
        "cost-allocation.schema.json",
        "allocation-observation.schema.json",
        "allocation-context.schema.json",
        "cluster-cost-review-order.schema.json",
        "cost-import.schema.json",
        "cost-reconciliation.schema.json",
        "focus-export-review.schema.json",
        "operator-catalog.schema.json",
        "operator-inspection.schema.json",
        "execution-preview.schema.json",
        "retained-assessment-quality.schema.json",
        "source-profile.schema.json",
        "financial-source-profile.schema.json",
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
        "daemonset-status-projection.schema.json",
        "daemonset-membership-review.schema.json",
        "storage-context-projection.schema.json",
        "nap-policy-input.schema.json",
        "nap-policy-review.schema.json",
        "startup-history.schema.json",
        "scheduling-constraint-calculation.schema.json",
        "pod-container-attempts.schema.json",
        "scheduling-completeness-audit.schema.json",
        "scheduling-shape-projection.schema.json",
        "scheduling-shape-diagnostics.schema.json",
        "scheduling-placement-review.schema.json",
        "disruption-protection-projection.schema.json",
        "scheduling-source-collection.schema.json",
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
    docs = next(command for command in commands if "--check-docs" in command)
    assert commands.index(docs) < next(
        index for index, command in enumerate(commands) if "pytest" in command
    )
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


def test_quick_verification_checks_contracts_and_selected_tests_without_full_replay(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(verify, "_run", lambda command: calls.append(command))
    monkeypatch.setattr(
        verify, "run_verification", lambda output: pytest.fail("full verification was invoked")
    )

    assert verify.main(["--quick", "--test", "tests/test_fleet.py"]) == 0

    assert [sys.executable, "-m", "ruff", "check", "."] in calls
    assert [sys.executable, "-m", "mypy", "src", "scripts"] in calls
    assert any(
        "generate_schemas.py" in " ".join(command) and "--check" in command for command in calls
    )
    assert any("generate_operator_catalog.py" in " ".join(command) for command in calls)
    tests = next(command for command in calls if "pytest" in command)
    assert "tests/test_fleet.py" in tests
    assert not any("--cov" in argument for argument in tests)
    assert not any("build" in command or "aks_fleet_efficiency.cli" in command for command in calls)
    assert "full verification was not run" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [["--quick"], ["--test", "tests/test_fleet.py"]])
def test_quick_verification_requires_explicit_mode_and_test_selection(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        verify.main(arguments)
    assert error.value.code == 2


@pytest.mark.parametrize(
    "selection",
    ["README.md", "tests/missing.py", "--maxfail=1", "tests/../src/aks_fleet_efficiency/cli.py"],
)
def test_quick_verification_rejects_non_test_paths_before_running_commands(
    selection: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(verify, "_run", lambda command: calls.append(command))

    assert verify.main(["--quick", f"--test={selection}"]) == 1
    assert calls == []


def test_quick_verification_preserves_failure_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(command: list[str]) -> None:
        raise subprocess.CalledProcessError(17, command)

    monkeypatch.setattr(verify, "_run", fail)
    assert verify.main(["--quick", "--test", "tests/test_fleet.py"]) == 17


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
