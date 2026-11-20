from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import sysconfig
import tempfile
import venv
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aks_fleet_efficiency.models import AnalysisReport

ROOT = Path(__file__).resolve().parents[1]
REPLAY_TIME = "2026-10-29T12:00:00Z"


def documentation_commands(text: str, *, expected_blocks: int) -> list[list[str]]:
    normalized = text.replace("\r\n", "\n")
    if expected_blocks < 1 or any(
        (ord(character) < 32 and character not in "\t\n") or ord(character) == 127
        for character in normalized
    ):
        raise ValueError("Documentation contains control characters or an invalid block count")
    commands: list[list[str]] = []
    fence: str | None = None
    selected = False
    blocks = 0
    block_commands = 0
    pending = ""
    for line in normalized.split("\n"):
        marker = re.fullmatch(r"[ \t]*(`{3,})([a-zA-Z0-9_-]*)[ \t]*", line)
        if fence is None and marker is not None:
            fence = marker[1]
            selected = marker[2].lower() == "powershell"
            block_commands = 0
            blocks += int(selected)
            continue
        if (
            fence is not None
            and marker is not None
            and not marker[2]
            and len(marker[1]) >= len(fence)
        ):
            if selected and (pending or not block_commands):
                raise ValueError(
                    "Documentation command block is empty or has a dangling continuation"
                )
            fence = None
            selected = False
            continue
        if not selected or not line.strip():
            continue
        part = line.strip()
        continued = part.endswith("`")
        if pending and not part.startswith("--"):
            raise ValueError("Documented command continuation must contain CLI options")
        if not pending and not part.startswith("aks-fleet-advisor "):
            raise ValueError("Financial command blocks must use the portable advisor entry point")
        pending = f"{pending} {part.removesuffix('`').rstrip()}".strip()
        if not continued:
            arguments = shlex.split(pending)
            if arguments[1] not in {
                "convert-focus",
                "project-costs",
                "project-allocation",
                "reconcile-costs",
            }:
                raise ValueError("Unsupported documented financial command")
            commands.append(arguments)
            block_commands += 1
            pending = ""
    if fence is not None or blocks != expected_blocks or not commands:
        raise ValueError(
            "Documentation fences are incomplete or the expected command blocks are missing"
        )
    return commands


def verify_documentation() -> None:
    for relative, expected_blocks in [
        ("docs/cost-reconciliation.md", 2),
        ("docs/tutorials/reconcile-existing-cost-evidence.md", 4),
    ]:
        text = (ROOT / relative).read_bytes().decode("utf-8")
        try:
            commands = documentation_commands(text, expected_blocks=expected_blocks)
        except ValueError as error:
            raise ValueError(
                f"Invalid financial documentation commands in {relative}: {error}"
            ) from error
        print(f"Documentation commands valid: {relative} ({len(commands)} commands)")


def _analysis_arguments(output_dir: Path, prefix: str, output_format: str) -> list[str]:
    extension = "json" if output_format == "json" else "md"
    return [
        "analyze",
        "--snapshot",
        str(ROOT / "examples" / "fixtures" / "fleet-snapshot.json"),
        "--config",
        str(ROOT / "examples" / "advisor-config.yaml"),
        "--as-of",
        REPLAY_TIME,
        "--format",
        output_format,
        "--output",
        str(output_dir / f"{prefix}-report.{extension}"),
    ]


def _static_commands() -> list[list[str]]:
    return [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "mypy", "src", "scripts"],
        [sys.executable, str(ROOT / "scripts" / "verify.py"), "--check-docs"],
        [sys.executable, str(ROOT / "scripts" / "generate_schemas.py"), "--check"],
        [sys.executable, str(ROOT / "scripts" / "generate_operator_catalog.py"), "--check"],
    ]


def quick_verification_commands(tests: list[str]) -> list[list[str]]:
    if not tests:
        raise ValueError("Focused verification requires explicit test selections")
    for selection in tests:
        path = (ROOT / selection.split("::", 1)[0]).resolve()
        if (
            selection.startswith("-")
            or not path.is_relative_to(ROOT / "tests")
            or not path.is_file()
            or path.suffix != ".py"
            or not path.name.startswith("test_")
        ):
            raise ValueError("Focused verification accepts existing test files or node IDs only")
    return [*_static_commands(), [sys.executable, "-m", "pytest", *tests, "--durations=10"]]


def run_quick_verification(tests: list[str]) -> None:
    for command in quick_verification_commands(tests):
        _run(command)
    print("Focused checks passed; full verification was not run.", flush=True)


def verification_commands(output_dir: Path) -> list[list[str]]:
    commands = [
        *_static_commands(),
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_promql.py"),
            "--output-dir",
            str(output_dir / "promql"),
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=aks_fleet_efficiency",
            "--cov-report=term-missing",
            f"--cov-report=xml:{output_dir / 'coverage.xml'}",
        ],
    ]
    for output_format in ["json", "markdown"]:
        commands.append(
            [
                sys.executable,
                "-m",
                "aks_fleet_efficiency.cli",
                *_analysis_arguments(output_dir, "source", output_format),
            ]
        )
    return commands


def _run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print(f"Running: {subprocess.list2cmdline(command)}", flush=True)
    started = perf_counter()
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)
    finally:
        print(f"Command elapsed: {perf_counter() - started:.2f}s", flush=True)


def compare_reports(reference: Path, candidate: Path, *, structured: bool = False) -> None:
    expected = reference.read_text(encoding="utf-8")
    actual = candidate.read_text(encoding="utf-8")
    matches = json.loads(expected) == json.loads(actual) if structured else expected == actual
    if not matches:
        raise RuntimeError(f"Report differs: {candidate} does not match {reference}")


def _assessment_arguments(case: str, output_format: str) -> list[str]:
    fixture = {
        "positive": "pool-assessment.json",
        "partial": "pool-assessment-partial.json",
        "workload": "workload-assessment.json",
        "history": "history-assessment.json",
        "scoped": "scoped-assessment.json",
        "azure": "azure-fragments-assessment.json",
        "replicas": "replica-inventory-assessment.json",
        "memory": "memory-assessment.json",
        "autoscalers": "autoscalers-assessment.json",
        "hpa-history": "hpa-history-assessment.json",
        "keda": "keda-assessment.json",
        "replica-floor": "replica-floor-assessment.json",
        "vpa-bounds": "vpa-bounds-assessment.json",
        "memory-envelope": "memory-envelope-assessment.json",
        "memory-limit": "memory-limit-assessment.json",
        "memory-context": "memory-context-assessment.json",
        "cpu-pack-baseline": "history-assessment.json",
        "cpu-pack-guarded": "history-assessment.json",
        "source-ordinary": "ordinary-source-assessment.json",
        "source-managed": "ordinary-source-assessment.json",
    }[case]
    profile = {
        "scoped": "scoped-assessment-config.yaml",
        "azure": "azure-fragments-config.yaml",
        "replicas": "azure-fragments-config.yaml",
        "cpu-pack-baseline": "cpu-pack-config.yaml",
        "cpu-pack-guarded": "cpu-pack-config.yaml",
        "source-ordinary": "ordinary-source-config.yaml",
        "source-managed": "managed-source-config.yaml",
    }.get(case, "pool-assessment-config.yaml")
    arguments = [
        "assess",
        "--fragments",
        str(ROOT / "examples" / "fixtures" / fixture),
        "--config",
        str(ROOT / "examples" / profile),
        "--as-of",
        REPLAY_TIME,
        "--format",
        output_format,
    ]
    if case in {"cpu-pack-baseline", "cpu-pack-guarded"}:
        arguments.extend(["--mode", "guarded" if case.endswith("guarded") else "baseline"])
    return arguments


ASSESSMENT_CASES = {
    "positive": 0,
    "partial": 3,
    "workload": 3,
    "history": 3,
    "scoped": 3,
    "azure": 3,
    "replicas": 3,
    "memory": 3,
    "autoscalers": 3,
    "hpa-history": 3,
    "keda": 3,
    "replica-floor": 3,
    "vpa-bounds": 3,
    "memory-envelope": 3,
    "memory-limit": 3,
    "memory-context": 3,
    "cpu-pack-baseline": 3,
    "cpu-pack-guarded": 3,
    "source-ordinary": 3,
    "source-managed": 3,
}


def _verify_assessments(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    for case, expected_exit in ASSESSMENT_CASES.items():
        for output_format, extension in [("json", "json"), ("markdown", "md")]:
            command = [*executable, *_assessment_arguments(case, output_format)]
            print(f"Running: {subprocess.list2cmdline(command)}", flush=True)
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != expected_exit:
                raise RuntimeError(
                    f"{prefix} {case} assessment exited {completed.returncode}; "
                    f"expected {expected_exit}"
                )
            destination = output_dir / f"{prefix}-assessment-{case}.{extension}"
            destination.write_text(completed.stdout, encoding="utf-8")
            if output_format == "json" and case in {"cpu-pack-baseline", "cpu-pack-guarded"}:
                _verify_cpu_pack_shape(case, json.loads(completed.stdout))
            if output_format == "json" and case in {"source-ordinary", "source-managed"}:
                _verify_source_shape(json.loads(completed.stdout))
            if output_format == "json" and case in {"keda", "replica-floor", "vpa-bounds"}:
                _verify_autoscaler_shape(case, json.loads(completed.stdout))
            if output_format == "json" and case in {
                "memory-envelope",
                "memory-limit",
                "memory-context",
            }:
                _verify_memory_shape(case, json.loads(completed.stdout))
            if output_format == "markdown":
                golden = (
                    f"expected-{case}.md"
                    if case
                    in {
                        "workload",
                        "history",
                        "scoped",
                        "azure",
                        "replicas",
                        "memory",
                        "autoscalers",
                        "hpa-history",
                        "keda",
                        "replica-floor",
                        "vpa-bounds",
                        "memory-envelope",
                        "memory-limit",
                        "memory-context",
                        "cpu-pack-baseline",
                        "cpu-pack-guarded",
                        "source-ordinary",
                        "source-managed",
                    }
                    else f"expected-pool-{case}.md"
                )
                compare_reports(ROOT / "examples" / golden, destination)


def _verify_autoscaler_shape(case: str, result: dict[str, object]) -> None:
    from aks_fleet_efficiency.models import AnalysisReport

    report = result.get("report")
    if not isinstance(report, dict):
        raise RuntimeError("Autoscaler assessment requires an embedded report")
    analysis = AnalysisReport.model_validate(report)
    rule_id = {"keda": "AKS-AS-004", "replica-floor": "AKS-AS-005", "vpa-bounds": "AKS-AS-007"}[
        case
    ]
    findings = [item for item in analysis.recommendations if item.rule_id == rule_id]
    if len(findings) != 1:
        raise RuntimeError(f"{case} must contain one {rule_id} finding")
    finding = findings[0]
    if (
        finding.proposed_requests is not None
        or finding.proposed_limits is not None
        or finding.estimated_monthly_savings is not None
    ):
        raise RuntimeError(f"{case} cannot propose resource requests or financial savings")
    if case == "replica-floor":
        if finding.current_replica_floor != 2 or finding.proposed_replica_floor != 1:
            raise RuntimeError("Replica-floor shape must preserve the exact 2-to-1 proposal")
    elif finding.current_replica_floor is not None or finding.proposed_replica_floor is not None:
        raise RuntimeError("Autoscaler investigations cannot propose replica changes")
    evidence = {item.metric: item for item in finding.evidence}
    if case == "keda" and evidence["generated_hpa_uid"].value != "synthetic-hpa-uid":
        raise RuntimeError("KEDA shape must retain the exact generated HPA identity")
    if case == "vpa-bounds" and (
        evidence["vpa_target_memory_mib"].value != 512
        or evidence["vpa_target_memory_mib"].unit != "MiB"
    ):
        raise RuntimeError("VPA shape must preserve the target with explicit MiB units")


def _verify_memory_shape(case: str, value: dict[str, object]) -> None:
    from aks_fleet_efficiency.assessment import OfflineAssessment

    result = OfflineAssessment.model_validate(value)
    recommendations = result.report.recommendations
    rule_id = {
        "memory-envelope": "AKS-MEM-003",
        "memory-limit": "AKS-MEM-005",
        "memory-context": "AKS-MEM-004",
    }[case]
    candidates = [item for item in recommendations if item.rule_id == rule_id]
    if len(candidates) != 1:
        raise RuntimeError(f"{case} must contain one {rule_id} finding")
    finding = candidates[0]
    if finding.estimated_monthly_savings is not None:
        raise RuntimeError("Memory assessments cannot establish financial savings")
    if case == "memory-limit":
        if (
            finding.current_limits is None
            or finding.proposed_limits is None
            or finding.current_limits.memory_mib != 1024
            or finding.proposed_limits.memory_mib != 600
            or finding.proposed_requests is not None
        ):
            raise RuntimeError("Limit shape requires a separate exact 1024-to-600 MiB proposal")
    elif case == "memory-envelope":
        resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
        if (
            finding.proposed_requests is None
            or finding.proposed_requests.memory_mib != 313
            or finding.proposed_requests.cpu_mcores is not None
            or finding.proposed_limits is not None
            or resources.memory_observation_basis != "replica-envelope"
            or resources.usage_memory_p99_mib != 192
        ):
            raise RuntimeError(
                "Envelope shape requires per-replica 313 MiB, not summed percentiles"
            )
        if not any(
            history.binding.membership_digest == resources.memory_membership_digest
            and "synthetic-deleted-memory-pod" in history.binding.pod_uids
            for history in result.workload_history
        ):
            raise RuntimeError("Memory envelope must bind the complete historical roster")
    else:
        if not any(
            item.metric == "effective_pod_memory_request" and item.value == 1184
            for item in finding.evidence
        ):
            raise RuntimeError("Effective Pod shape requires 1184 MiB")
        if not any(item.rule_id == "AKS-REL-002" for item in recommendations) or not any(
            item.rule_id == "AKS-REL-003" for item in recommendations
        ):
            raise RuntimeError(
                "Context shape must retain separate termination and eviction findings"
            )
        if any(
            item.proposed_limits is not None or item.proposed_requests is not None
            for item in recommendations
        ):
            raise RuntimeError("Reliability/accounting context cannot propose numeric reductions")


def _verify_cpu_pack_shape(case: str, payload: object) -> None:
    from aks_fleet_efficiency.assessment import OfflineAssessment

    result = OfflineAssessment.model_validate(payload)
    findings = result.report.recommendations
    if len(findings) != 1 or findings[0].rule_id != "AKS-RQ-002":
        raise RuntimeError("CPU pack selection must produce exactly its own finding")
    finding = findings[0]
    if case == "cpu-pack-baseline":
        if result.report.mode != "baseline" or finding.proposed_requests is not None:
            raise RuntimeError("Baseline CPU pack cannot propose numeric requests")
    elif (
        result.report.mode != "guarded"
        or finding.current_requests is None
        or finding.proposed_requests is None
        or finding.current_requests.cpu_mcores != 1000
        or finding.proposed_requests.cpu_mcores != 500
    ):
        raise RuntimeError("Guarded CPU pack must preserve the 1000-to-500 mCPU proposal")


def _verify_source_shape(payload: object) -> None:
    from aks_fleet_efficiency.assessment import OfflineAssessment

    result = OfflineAssessment.model_validate(payload)
    if len(result.baseline_measurements) != 2 or result.workload_history:
        raise RuntimeError(
            "Ordinary source must retain unresolved measurements, not invented history"
        )
    statuses = {item.mode: item.status for item in result.report.source_capabilities}
    if statuses != {"baseline": "available", "guarded": "unsupported"}:
        raise RuntimeError(
            "Ordinary source must expose available baseline and unsupported guarded capability"
        )
    if any(
        item.entity.workload_uid is not None or item.entity.pod_uid is not None
        for item in result.baseline_measurements
    ) or any(item.proposed_requests is not None for item in result.report.recommendations):
        raise RuntimeError("Unresolved baseline cannot authorize history or numeric proposals")


def _verify_cost_reconciliation(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    destination = output_dir / f"{prefix}-costs.json"
    _run(
        [
            *executable,
            "reconcile-costs",
            "--costs",
            str(ROOT / "examples" / "fixtures" / "cost-import.json"),
            "--snapshot",
            str(ROOT / "examples" / "fixtures" / "cost-snapshot.json"),
            "--as-of",
            REPLAY_TIME,
            "--output",
            str(destination),
        ],
        cwd=cwd,
        env=env,
    )
    from aks_fleet_efficiency.cost import CostReconciliation

    result = CostReconciliation.model_validate_json(destination.read_text(encoding="utf-8"))
    if (
        result.status != "reconciled"
        or len(result.currencies) != 1
        or result.currencies[0].total != 100
        or result.currencies[0].by_attribution
        != {
            "allocated": 60,
            "idle": 25,
            "shared": 0,
            "system": 15,
            "unallocated": 0,
        }
        or result.currencies[0].allocation_coverage != 1
        or result.estimated_monthly_savings is not None
    ):
        raise RuntimeError("Cost replay must preserve the exact partition and null savings")
    allocation_destination = output_dir / f"{prefix}-allocation.json"
    _run(
        [
            *executable,
            "project-allocation",
            "--allocation-profile",
            "aks-cost-analysis",
            "--allocation",
            str(ROOT / "examples" / "fixtures" / "aks-cost-analysis-allocation.json"),
            "--output",
            str(allocation_destination),
        ],
        cwd=cwd,
        env=env,
    )
    from aks_fleet_efficiency.cost import CostAllocation
    from aks_fleet_efficiency.cost_sources import project_allocation

    original = json.loads(
        (ROOT / "examples" / "fixtures" / "aks-cost-analysis-allocation.json").read_text(
            encoding="utf-8"
        )
    )
    allocation = CostAllocation.model_validate_json(
        allocation_destination.read_text(encoding="utf-8")
    )
    if allocation != project_allocation("aks-cost-analysis", original):
        raise RuntimeError(
            "Ledger-free allocation projection must preserve original source semantics"
        )


def _verify_wheel(output_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aks-advisor-package-") as temporary:
        scratch = Path(temporary)
        wheels = scratch / "wheels"
        _run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(wheels),
                str(ROOT),
            ]
        )
        artifacts = list(wheels.glob("*.whl"))
        if len(artifacts) != 1:
            raise RuntimeError("Package verification requires exactly one built wheel")
        environment = scratch / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        installed_site = Path(
            sysconfig.get_path(
                "purelib", vars={"base": str(environment), "platbase": str(environment)}
            )
        )
        dependency_paths = sorted({sysconfig.get_path(name) for name in ["purelib", "platlib"]})
        (installed_site / "advisor-verification-dependencies.pth").write_text(
            "\n".join(dependency_paths) + "\n", encoding="utf-8"
        )
        binaries = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        executable = binaries / (
            "aks-fleet-advisor.exe" if os.name == "nt" else "aks-fleet-advisor"
        )
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("PYTHONHOME", None)
        clean_env["PYTHONNOUSERSITE"] = "1"
        _run(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--no-deps",
                str(artifacts[0]),
            ],
            cwd=scratch,
            env=clean_env,
        )
        probe = (
            "import aks_fleet_efficiency, pathlib, sys; "
            "module_path = pathlib.Path(aks_fleet_efficiency.__file__).resolve(); "
            "assert module_path.is_relative_to(pathlib.Path(sys.prefix).resolve()), module_path"
        )
        _run([str(python), "-I", "-c", probe], cwd=scratch, env=clean_env)
        _run([str(executable), "--help"], cwd=scratch, env=clean_env)
        _verify_catalog(output_dir, "wheel", [str(executable)], cwd=scratch, env=clean_env)
        _verify_cost_reconciliation(
            output_dir, "wheel", [str(executable)], cwd=scratch, env=clean_env
        )
        for output_format in ["json", "markdown"]:
            _run(
                [str(executable), *_analysis_arguments(output_dir, "wheel", output_format)],
                cwd=scratch,
                env=clean_env,
            )
        _verify_assessments(output_dir, "wheel", [str(executable)], cwd=scratch, env=clean_env)
        _verify_artifact_replay(output_dir, "wheel", [str(executable)], cwd=scratch, env=clean_env)


def _verify_artifact_replay(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    artifacts = output_dir / f"{prefix}-artifacts"
    command = [
        *executable,
        *_assessment_arguments("history", "json"),
        "--artifacts",
        str(artifacts),
    ]
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 3:
        raise RuntimeError("Artifact assessment must preserve partial status")
    replay = subprocess.run(
        [
            *executable,
            "analyze",
            "--snapshot",
            str(artifacts / "snapshot.json"),
            "--config",
            str(artifacts / "analysis-config.json"),
            "--as-of",
            REPLAY_TIME,
            "--format",
            "json",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if replay.returncode != 0 or json.loads(replay.stdout) != json.loads(result.stdout)["report"]:
        raise RuntimeError("Artifact snapshot replay differs from assessment report")
    _verify_history(output_dir, prefix, executable, artifacts, cwd=cwd, env=env)
    _verify_ai_export(output_dir, prefix, executable, artifacts, cwd=cwd, env=env)
    _verify_retained_quality(output_dir, prefix, executable, artifacts, cwd=cwd, env=env)
    _verify_cost_review_order(output_dir, prefix, executable, artifacts, cwd=cwd, env=env)
    _verify_supplied_evidence_reviews(output_dir, prefix, executable, cwd=cwd, env=env)
    context_path = output_dir / f"{prefix}-allocation-context.json"
    _run(
        [
            *executable,
            "qualify-allocation",
            "--observation",
            str(ROOT / "examples/fixtures/allocation-observation.json"),
            "--assessment",
            str(artifacts / "assessment.json"),
            "--tenant",
            "00000000-0000-0000-0000-000000000000",
            "--as-of",
            REPLAY_TIME,
            "--output",
            str(context_path),
        ],
        cwd=cwd,
        env=env,
    )
    from aks_fleet_efficiency.cost import AllocationContext, AllocationObservation

    context = AllocationContext.model_validate_json(context_path.read_text(encoding="utf-8"))
    original_observation = AllocationObservation.model_validate_json(
        (ROOT / "examples/fixtures/allocation-observation.json").read_bytes()
    )
    if context.status != "qualified" or context.observation != original_observation:
        raise RuntimeError("Allocation context must preserve the exact source observation")
    refused = subprocess.run(
        [
            *executable,
            "collect",
            "--config",
            str(ROOT / "examples/pool-assessment-config.yaml"),
            "--plan",
            str(ROOT / "examples/collection-plan.json"),
            "--output",
            str(output_dir / f"{prefix}-refused.json"),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if refused.returncode != 2 or (output_dir / f"{prefix}-refused.json").exists():
        raise RuntimeError("Collection without explicit consent must fail before output or I/O")


def _verify_retained_quality(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    artifacts: Path,
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    from aks_fleet_efficiency.operator import RetainedAssessmentQuality

    exported = output_dir / f"{prefix}-retained-queries"
    _run(
        [
            *executable,
            "catalog",
            "export",
            "AKS-RQ-002",
            "--config",
            str(ROOT / "examples/cpu-pack-config.yaml"),
            "--entities",
            str(ROOT / "examples/cpu-pack-entities.json"),
            "--source",
            "synthetic",
            "--grafana",
            "--assessment-artifacts",
            str(artifacts),
            "--output",
            str(exported),
        ],
        cwd=cwd,
        env=env,
    )
    quality = RetainedAssessmentQuality.model_validate_json(
        (exported / "retained-quality.json").read_text(encoding="utf-8")
    )
    if quality.live_quality != "unknown" or any(
        record.status == "matched" for record in quality.records
    ):
        raise RuntimeError("Imported canonical summaries cannot invent execution provenance")
    dashboard = json.loads((exported / "dashboard.json").read_text(encoding="utf-8"))
    panels = [panel for panel in dashboard["panels"] if panel["type"] == "text"]
    if len(panels) != 2 or "unknown" not in panels[0]["options"]["content"].lower():
        raise RuntimeError("Retained export must preserve unknown live dashboard quality")


def _verify_cost_review_order(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    artifacts: Path,
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    from aks_fleet_efficiency.config import load_onboarding_config
    from aks_fleet_efficiency.cost import ClusterCostReviewOrder
    from aks_fleet_efficiency.fleet import FleetInsightReport

    original = json.loads((artifacts / "assessment.json").read_text(encoding="utf-8"))
    cluster = original["snapshot"]["clusters"][0]
    cluster_id, fingerprint = cluster["resource_id"], cluster["uid"]
    peer_id = cluster_id + "-cost-review-peer"
    peer_fingerprint = "synthetic-cost-review-peer-fingerprint"

    def rebind(value: object) -> object:
        if isinstance(value, dict):
            return {key: rebind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rebind(item) for item in value]
        if isinstance(value, str):
            if value == cluster_id or value.startswith(cluster_id + "/"):
                return peer_id + value[len(cluster_id) :]
            if value == fingerprint:
                return peer_fingerprint
            if value == cluster["name"]:
                return peer_id.rsplit("/", 1)[-1]
        return value

    peer_fragments = output_dir / f"{prefix}-cost-peer-fragments.json"
    peer_profile = output_dir / f"{prefix}-cost-peer-profile.json"
    peer_artifacts = output_dir / f"{prefix}-cost-peer-artifacts"
    fixture = json.loads((artifacts / "fragments.json").read_text(encoding="utf-8"))
    peer_fragments.write_text(json.dumps(rebind(fixture)), encoding="utf-8")
    profile = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml")
    peer_profile.write_text(json.dumps(rebind(profile.model_dump(mode="json"))), encoding="utf-8")
    assessed = subprocess.run(
        [
            *executable,
            "assess",
            "--fragments",
            str(peer_fragments),
            "--config",
            str(peer_profile),
            "--as-of",
            REPLAY_TIME,
            "--format",
            "json",
            "--artifacts",
            str(peer_artifacts),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if assessed.returncode not in {0, 3}:
        raise RuntimeError("Synthetic exact-peer assessment failed in cost-review verifier")
    arguments = [
        *executable,
        "order-cost-review",
        "--tenant",
        "00000000-0000-0000-0000-000000000000",
        "--as-of",
        REPLAY_TIME,
    ]
    for index, (directory, resource_id, uid, amount) in enumerate(
        [
            (artifacts, cluster_id, fingerprint, "100"),
            (peer_artifacts, peer_id, peer_fingerprint, "200"),
        ]
    ):
        observation = json.loads(
            (ROOT / "examples/fixtures/allocation-observation.json").read_text(encoding="utf-8")
        )
        observation["cluster_resource_id"], observation["cluster_uid"] = resource_id, uid
        allocation = observation["allocation"]
        currency = allocation["amounts"][0]["currency"]
        allocation["amounts"] = [
            {
                "category": "allocated",
                "granularity": "cluster",
                "cluster_resource_id": resource_id,
                "identity_basis": "current-only",
                "reference": "synthetic-cluster-review-binding",
                "amount": amount,
                "currency": currency,
            },
            *[item for item in allocation["amounts"] if item["category"] != "allocated"],
        ]
        path = output_dir / f"{prefix}-cost-review-observation-{index}.json"
        path.write_text(json.dumps(observation), encoding="utf-8")
        arguments.extend(
            [
                "--assessment",
                str(directory / "assessment.json"),
                "--observation",
                str(path),
            ]
        )
    output = output_dir / f"{prefix}-cluster-cost-review.json"
    _run([*arguments, "--output", str(output)], cwd=cwd, env=env)
    result = ClusterCostReviewOrder.model_validate_json(output.read_text(encoding="utf-8"))
    if (
        str(result.rows[0].allocated_amount) != "200"
        or result.engineering_order_changed
        or result.estimated_monthly_savings is not None
    ):
        raise RuntimeError("Cluster cost review must not alter engineering priority or savings")
    for format_name, extension in [("json", "json"), ("markdown", "md")]:
        path = output_dir / f"{prefix}-fleet-inventory.{extension}"
        _run(
            [
                *executable,
                "fleet",
                "summarize",
                "--assessment",
                str(artifacts / "assessment.json"),
                "--peer-group",
                "synthetic-peers",
                "--assessment",
                str(peer_artifacts / "assessment.json"),
                "--peer-group",
                "synthetic-peers",
                "--as-of",
                REPLAY_TIME,
                "--format",
                format_name,
                "--output",
                str(path),
            ],
            cwd=cwd,
            env=env,
        )
        if extension == "json":
            FleetInsightReport.model_validate_json(path.read_text(encoding="utf-8"))


def _verify_ai_export(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    artifacts: Path,
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    from aks_fleet_efficiency.advisory import (
        AdvisoryProvenance,
        AIChecklist,
        AIChecklistDraft,
        AIChecklistStep,
        AIEvidencePackage,
        AIExperiment,
        AIExperimentCheck,
        AIExperimentDraft,
        AIExperimentIntent,
        AIExplanation,
        AIExplanationClaim,
        AIExplanationDraft,
        AIResourceEvidencePackage,
        AIReviewIntent,
        EvidenceCitation,
        content_digest,
    )

    package_path = output_dir / f"{prefix}-ai-package.json"
    arguments = [
        *executable,
        "ai",
        "export",
        "--assessment",
        str(artifacts / "assessment.json"),
        "--tenant",
        "00000000-0000-0000-0000-000000000000",
        "--as-of",
        REPLAY_TIME,
        "--output",
        str(package_path),
    ]
    refused = subprocess.run(
        arguments, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if refused.returncode != 2 or package_path.exists():
        raise RuntimeError("AI export requires explicit consent before output")
    _run([*arguments, "--allow-ai-export"], cwd=cwd, env=env)
    package = AIEvidencePackage.model_validate_json(package_path.read_text(encoding="utf-8"))
    if not package.records:
        raise RuntimeError("Synthetic AI replay requires finding or blocked summaries")
    richer_path = output_dir / f"{prefix}-ai-measurements.json"
    richer_arguments = list(arguments)
    richer_arguments[richer_arguments.index("--output") + 1] = str(richer_path)
    _run([*richer_arguments, "--allow-ai-export", "--allow-ai-measurements"], cwd=cwd, env=env)
    richer = AIResourceEvidencePackage.model_validate_json(richer_path.read_text(encoding="utf-8"))
    if (
        richer.summary != package
        or not richer.measurements
        or any(item.status != "withheld" or item.value is not None for item in richer.measurements)
    ):
        raise RuntimeError("Canonical unproven measurement provenance must stay withheld")
    record = package.records[0]
    draft = AIExplanationDraft(
        package_digest=content_digest(package),
        generated_at=package.generated_at,
        expires_at=package.expires_at,
        provenance=AdvisoryProvenance(
            provider="synthetic-not-invoked",
            model="synthetic-not-invoked",
            prompt_revision="0" * 64,
            skill_revision="0" * 64,
            tool_revision="0" * 64,
        ),
        claims=(
            AIExplanationClaim(
                fact=record,
                citation=EvidenceCitation(
                    record_id=record.record_id, record_digest=content_digest(record)
                ),
                interpretation="Synthetic unverified interpretation; not AI output or approval.",
            ),
        ),
    )
    draft_path = output_dir / f"{prefix}-ai-draft.json"
    draft_path.write_text(draft.model_dump_json(), encoding="utf-8")
    result = subprocess.run(
        [
            *executable,
            "ai",
            "validate-explanation",
            "--assessment",
            str(artifacts / "assessment.json"),
            "--tenant",
            "00000000-0000-0000-0000-000000000000",
            "--as-of",
            REPLAY_TIME,
            "--package",
            str(package_path),
            "--draft",
            str(draft_path),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    explanation = AIExplanation.model_validate_json(result.stdout)
    if content_digest(explanation.claims[0].fact) != content_digest(record):
        raise RuntimeError("AI handoff must preserve original copied facts")
    (output_dir / f"{prefix}-ai-explanation.json").write_text(result.stdout, encoding="utf-8")
    intent = AIReviewIntent(
        package_digest=content_digest(package),
        scope_id=record.scope_id,
        objective="review-missing-evidence",
    )
    checklist = AIChecklistDraft(
        intent_digest=content_digest(intent),
        explanation=draft,
        steps=tuple(
            AIChecklistStep.model_validate({"kind": kind, "citation": draft.claims[0].citation})
            for kind in [
                "define_test_and_abort_criteria",
                "verify_rollback_prerequisites",
                "retain_no_change_option",
            ]
        ),
    )
    intent_path = output_dir / f"{prefix}-ai-intent.json"
    checklist_path = output_dir / f"{prefix}-ai-checklist-draft.json"
    intent_path.write_text(intent.model_dump_json(), encoding="utf-8")
    checklist_path.write_text(checklist.model_dump_json(), encoding="utf-8")
    result = subprocess.run(
        [
            *executable,
            "ai",
            "validate-checklist",
            "--assessment",
            str(artifacts / "assessment.json"),
            "--tenant",
            "00000000-0000-0000-0000-000000000000",
            "--as-of",
            REPLAY_TIME,
            "--package",
            str(package_path),
            "--intent",
            str(intent_path),
            "--draft",
            str(checklist_path),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    admitted = AIChecklist.model_validate_json(result.stdout)
    if admitted.intent_digest != content_digest(intent):
        raise RuntimeError("AI checklist must preserve the exact synthetic review intent")
    (output_dir / f"{prefix}-ai-checklist.json").write_text(result.stdout, encoding="utf-8")
    experiment_intent = AIExperimentIntent(
        package_digest=content_digest(package),
        scope_id=record.scope_id,
        objective="review-missing-evidence",
        dimension="evidence_only",
        controller="none",
    )
    experiment = AIExperimentDraft(
        intent_digest=content_digest(experiment_intent),
        dimension="evidence_only",
        controller="none",
        explanation=draft,
        hypothesis="Synthetic review prompts only; no model or action invoked.",
        alternatives=("retain_current_configuration", "collect_missing_evidence"),
        unresolved_prerequisites=("owner_review", "source_completeness"),
        checks=tuple(
            AIExperimentCheck.model_validate({"kind": kind, "citation": draft.claims[0].citation})
            for kind in ["baseline", "canary", "observe", "abort", "rollback", "no_change"]
        ),
    )
    experiment_intent_path = output_dir / f"{prefix}-ai-experiment-intent.json"
    experiment_draft_path = output_dir / f"{prefix}-ai-experiment-draft.json"
    experiment_intent_path.write_text(experiment_intent.model_dump_json(), encoding="utf-8")
    experiment_draft_path.write_text(experiment.model_dump_json(), encoding="utf-8")
    result = subprocess.run(
        [
            *executable,
            "ai",
            "validate-experiment",
            "--assessment",
            str(artifacts / "assessment.json"),
            "--tenant",
            "00000000-0000-0000-0000-000000000000",
            "--as-of",
            REPLAY_TIME,
            "--package",
            str(package_path),
            "--intent",
            str(experiment_intent_path),
            "--draft",
            str(experiment_draft_path),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    admitted_experiment = AIExperiment.model_validate_json(result.stdout)
    if admitted_experiment.intent_digest != content_digest(experiment_intent):
        raise RuntimeError("AI experiment must preserve exact synthetic intent")
    (output_dir / f"{prefix}-ai-experiment.json").write_text(result.stdout, encoding="utf-8")


def _verify_supplied_evidence_reviews(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    from aks_fleet_efficiency.assessment import AssessmentFragments
    from aks_fleet_efficiency.daemonsets import DaemonSetMembershipReview
    from aks_fleet_efficiency.nap_policy import NapPolicyReview
    from aks_fleet_efficiency.node_history import HistoricalNodeReview
    from aks_fleet_efficiency.storage import StorageContextProjection

    for name, fixture, arguments in [
        (
            "node-history",
            "node-history-evidence.json",
            ["fleet", "review-node-history", "--history"],
        ),
        ("nap-policy", "nap-policy-input.json", ["review-nap-policy", "--policy"]),
    ]:
        source = ROOT / "examples/fixtures" / fixture
        payload = json.loads(source.read_text(encoding="utf-8"))
        output = output_dir / f"{prefix}-{name}-review.json"
        _run(
            [
                *executable,
                *arguments,
                str(source),
                "--tenant",
                payload["tenant_id"],
                "--cluster",
                payload["cluster_resource_id"],
                "--as-of",
                REPLAY_TIME,
                "--output",
                str(output),
            ],
            cwd=cwd,
            env=env,
        )
        if name == "node-history":
            history = HistoricalNodeReview.model_validate_json(output.read_bytes())
            if history.cpu_p95_mcpu != 1000.0 or history.memory_p99_working_set_mib != 200.0:
                raise RuntimeError("Canonical Node history must retain aligned resource arithmetic")
        else:
            policy = NapPolicyReview.model_validate_json(output.read_bytes())
            if (
                policy.reasons["Empty"].configured_limit != 1
                or policy.reasons["Drifted"].configured_limit != 2
            ):
                raise RuntimeError("Canonical NAP policy must preserve reason-specific ceilings")
    original_path = ROOT / "examples/fixtures/daemonset-overhead-assessment.json"
    metadata = AssessmentFragments.model_validate_json(original_path.read_bytes()).kubernetes[0]
    native = {
        key: [
            {
                "apiVersion": row.api_version,
                "kind": row.kind,
                "metadata": {
                    "name": row.name,
                    "namespace": row.namespace,
                    "uid": row.uid,
                    "labels": row.labels,
                    "ownerReferences": row.owner_references,
                },
                "spec": row.spec,
                "status": row.status,
            }
            for row in metadata.resources
            if row.kind == kind
        ]
        for key, kind in [("daemonsets", "DaemonSet"), ("nodes", "Node")]
    }
    for name, flag, payload in [
        ("daemonset", "--native-objects", native),
        ("storage", "--native-storage", {"objects": [], "receipts": {}}),
    ]:
        native_path = output_dir / f"{prefix}-{name}-native.json"
        native_path.write_text(json.dumps(payload), encoding="utf-8")
        output = output_dir / f"{prefix}-{name}-review.json"
        _run(
            [
                *executable,
                "review-daemonsets" if name == "daemonset" else "review-storage",
                "--fragments",
                str(original_path),
                flag,
                str(native_path),
                "--tenant",
                metadata.tenant_id,
                "--cluster",
                metadata.cluster_resource_id,
                "--as-of",
                REPLAY_TIME,
                "--max-source-age-seconds",
                "7200",
                "--output",
                str(output),
            ],
            cwd=cwd,
            env=env,
        )
        if name == "daemonset":
            daemonsets = DaemonSetMembershipReview.model_validate_json(output.read_bytes())
            if not daemonsets.comparisons or any(
                row.modeled_desired_node_uids is not None for row in daemonsets.daemonsets
            ):
                raise RuntimeError(
                    "Old saved DaemonSet shape must retain unknown desired membership"
                )
        else:
            storage = StorageContextProjection.model_validate_json(output.read_bytes())
            if not storage.source_issues or storage.claims:
                raise RuntimeError(
                    "Missing storage evidence must not become an observed population"
                )


def _verify_history(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    artifacts: Path,
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    from aks_fleet_efficiency.history import FleetHistoryTrend, HistoryRun, HistoryTrend

    store = output_dir / f"{prefix}-history"
    options = ["--store", str(store), "--tenant", "00000000-0000-0000-0000-000000000000"]
    later_artifacts = output_dir / f"{prefix}-history-later-artifacts"
    later_arguments = [
        "2026-10-29T13:00:00Z" if argument == REPLAY_TIME else argument
        for argument in _assessment_arguments("history", "json")
    ]
    later = subprocess.run(
        [*executable, *later_arguments, "--artifacts", str(later_artifacts)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if later.returncode != 3:
        raise RuntimeError("History replay must retain partial assessment status")
    stateless = subprocess.run(
        [
            *executable,
            "compare",
            "--previous",
            str(artifacts),
            "--current",
            str(later_artifacts),
            "--tenant",
            "00000000-0000-0000-0000-000000000000",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    stateless_trend = HistoryTrend.model_validate_json(stateless.stdout)
    runs = []
    for source in [artifacts, later_artifacts, later_artifacts]:
        result = subprocess.run(
            [*executable, "history", "import", "--artifacts", str(source), *options],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        runs.append(HistoryRun.model_validate_json(result.stdout))
    if runs[1] != runs[2] or any(run.savings is not None for run in runs):
        raise RuntimeError("History imports must be idempotent and preserve null savings")
    for name, arguments in [
        ("runs", ["list"]),
        ("trend", ["compare", "--previous", runs[0].run_id, "--current", runs[1].run_id]),
    ]:
        result = subprocess.run(
            [*executable, "history", *arguments, *options],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        if name == "runs" and len(json.loads(result.stdout)) != 2:
            raise RuntimeError("History store must retain exactly two immutable runs")
        if name == "trend":
            trend = HistoryTrend.model_validate_json(result.stdout)
            if not trend.comparable or trend.savings is not None:
                raise RuntimeError("History replay must remain comparable without savings")
            if trend != stateless_trend:
                raise RuntimeError("Stateless comparison must match the imported history pair")
        (output_dir / f"{prefix}-history-{name}.json").write_text(result.stdout, encoding="utf-8")
    (output_dir / f"{prefix}-history-stateless-trend.json").write_text(
        stateless.stdout, encoding="utf-8"
    )
    fleet_trends = subprocess.run(
        [
            *executable,
            "fleet",
            "trends",
            "--assessment",
            str(artifacts / "assessment.json"),
            "--peer-group",
            "synthetic-peer",
            "--assessment",
            str(later_artifacts / "assessment.json"),
            "--peer-group",
            "synthetic-peer",
            "--tenant",
            "00000000-0000-0000-0000-000000000000",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    fleet_report = FleetHistoryTrend.model_validate_json(fleet_trends.stdout)
    if len(fleet_report.series) != 1 or fleet_report.series[0].comparisons != [stateless_trend]:
        raise RuntimeError("Fleet trends must preserve the exact stateless pair comparison")
    (output_dir / f"{prefix}-history-fleet-trends.json").write_text(
        fleet_trends.stdout, encoding="utf-8"
    )


def run_verification(output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for command in verification_commands(output_dir):
        _run(command)
    compare_reports(ROOT / "examples" / "expected-report.md", output_dir / "source-report.md")
    _verify_catalog(output_dir, "source", [sys.executable, "-m", "aks_fleet_efficiency.cli"])
    _verify_cost_reconciliation(
        output_dir, "source", [sys.executable, "-m", "aks_fleet_efficiency.cli"]
    )
    _verify_assessments(output_dir, "source", [sys.executable, "-m", "aks_fleet_efficiency.cli"])
    _verify_artifact_replay(
        output_dir, "source", [sys.executable, "-m", "aks_fleet_efficiency.cli"]
    )
    _verify_wheel(output_dir)
    for name in ["runs", "trend", "stateless-trend", "fleet-trends"]:
        compare_reports(
            output_dir / f"source-history-{name}.json",
            output_dir / f"wheel-history-{name}.json",
            structured=True,
        )
    for name in ["package", "explanation", "checklist", "measurements", "experiment"]:
        compare_reports(
            output_dir / f"source-ai-{name}.json",
            output_dir / f"wheel-ai-{name}.json",
            structured=True,
        )
    for name in ["node-history", "nap-policy", "storage", "daemonset"]:
        compare_reports(
            output_dir / f"source-{name}-review.json",
            output_dir / f"wheel-{name}-review.json",
            structured=True,
        )
    for name in ["manifest.json", "retained-quality.json", "dashboard.json"]:
        compare_reports(
            output_dir / "source-retained-queries" / name,
            output_dir / "wheel-retained-queries" / name,
            structured=True,
        )
    compare_reports(
        output_dir / "source-costs.json", output_dir / "wheel-costs.json", structured=True
    )
    compare_reports(
        output_dir / "source-allocation.json", output_dir / "wheel-allocation.json", structured=True
    )
    compare_reports(
        output_dir / "source-allocation-context.json",
        output_dir / "wheel-allocation-context.json",
        structured=True,
    )
    compare_reports(
        output_dir / "source-cluster-cost-review.json",
        output_dir / "wheel-cluster-cost-review.json",
        structured=True,
    )
    compare_reports(
        output_dir / "source-fleet-inventory.json",
        output_dir / "wheel-fleet-inventory.json",
        structured=True,
    )
    compare_reports(
        output_dir / "source-fleet-inventory.md", output_dir / "wheel-fleet-inventory.md"
    )
    compare_reports(
        output_dir / "source-report.json", output_dir / "wheel-report.json", structured=True
    )
    compare_reports(output_dir / "source-report.md", output_dir / "wheel-report.md")
    for case in ASSESSMENT_CASES:
        for extension in ["json", "md"]:
            compare_reports(
                output_dir / f"source-assessment-{case}.{extension}",
                output_dir / f"wheel-assessment-{case}.{extension}",
                structured=extension == "json",
            )
    compare_reports(
        output_dir / "source-catalog.json", output_dir / "wheel-catalog.json", structured=True
    )
    compare_reports(
        output_dir / "source-operator-catalog.json",
        output_dir / "wheel-operator-catalog.json",
        structured=True,
    )
    compare_reports(
        output_dir / "source-execution-preview.json",
        output_dir / "wheel-execution-preview.json",
        structured=True,
    )
    source_queries = output_dir / "source-cpu-queries"
    wheel_queries = output_dir / "wheel-cpu-queries"
    source_names = {path.name for path in source_queries.iterdir()}
    if source_names != {path.name for path in wheel_queries.iterdir()}:
        raise RuntimeError("Source/wheel query export assets differ")
    for name in sorted(source_names):
        compare_reports(
            source_queries / name, wheel_queries / name, structured=name.endswith(".json")
        )
    for case in [
        "missing-request",
        "request-risk",
        "pool-review",
        "scheduling-review",
        "capacity-review",
    ]:
        for extension in ["json", "md"]:
            compare_reports(
                output_dir / f"source-review-{case}.{extension}",
                output_dir / f"wheel-review-{case}.{extension}",
                structured=extension == "json",
            )
    for case in [
        "oom-pack",
        "memory-safety-pack",
        "memory-request-pack",
        "pod-memory-pack",
        "memory-limit-pack",
        "restart-pack",
        "termination-pack",
        "eviction-pack",
    ]:
        for extension in ["json", "md"]:
            compare_reports(
                output_dir / f"source-memory-{case}.{extension}",
                output_dir / f"wheel-memory-{case}.{extension}",
                structured=extension == "json",
            )
    for case in [
        "fixed-replica-pack",
        "interaction-pack",
        "hpa-pinning-pack",
        "keda-pack",
        "hpa-floor-pack",
        "hpa-change-pack",
        "vpa-bounds-pack",
    ]:
        for mode in ["baseline", "guarded"]:
            for extension in ["json", "md"]:
                compare_reports(
                    output_dir / f"source-autoscaler-{case}-{mode}.{extension}",
                    output_dir / f"wheel-autoscaler-{case}-{mode}.{extension}",
                    structured=extension == "json",
                )
    source_hpa = output_dir / "source-autoscaler-queries"
    wheel_hpa = output_dir / "wheel-autoscaler-queries"
    names = {path.name for path in source_hpa.iterdir()}
    if names != {path.name for path in wheel_hpa.iterdir()}:
        raise RuntimeError("Source/wheel autoscaler query exports differ")
    for name in sorted(names):
        compare_reports(source_hpa / name, wheel_hpa / name, structured=name.endswith(".json"))
    source_pool = output_dir / "source-pool-queries"
    wheel_pool = output_dir / "wheel-pool-queries"
    names = {path.name for path in source_pool.iterdir()}
    if names != {path.name for path in wheel_pool.iterdir()}:
        raise RuntimeError("Source/wheel pool query exports differ")
    for name in sorted(names):
        compare_reports(source_pool / name, wheel_pool / name, structured=name.endswith(".json"))
    print("Verification passed: source and installed-wheel reports match.", flush=True)


def _verify_catalog(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    manifests = []
    from aks_fleet_efficiency.catalog import load_catalog

    for pack_id in sorted(load_catalog().manifests):
        result = subprocess.run(
            [*executable, "catalog", "show", pack_id],
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        manifests.append(json.loads(result.stdout))
    (output_dir / f"{prefix}-catalog.json").write_text(
        json.dumps(manifests, indent=2) + "\n", encoding="utf-8"
    )
    _run(
        [
            *executable,
            "catalog",
            "guide",
            "--format",
            "json",
            "--output",
            str(output_dir / f"{prefix}-operator-catalog.json"),
        ],
        cwd=cwd,
        env=env,
    )
    _run(
        [
            *executable,
            "configure",
            "--no-interactive",
            "--config",
            str(ROOT / "examples" / "cpu-pack-config.yaml"),
            "--pack",
            "AKS-RQ-002",
            "--review-ratio",
            "AKS-RQ-002=0.3",
            "--output",
            str(output_dir / f"{prefix}-operator-profile.yaml"),
        ],
        cwd=cwd,
        env=env,
    )
    _run(
        [
            *executable,
            "preview",
            "--config",
            str(output_dir / f"{prefix}-operator-profile.yaml"),
            "--plan",
            str(ROOT / "examples" / "operator-plan.json"),
            "--as-of",
            REPLAY_TIME,
            "--output",
            str(output_dir / f"{prefix}-execution-preview.json"),
        ],
        cwd=cwd,
        env=env,
    )
    _run(
        [
            *executable,
            "catalog",
            "export",
            "AKS-RQ-002",
            "--pack",
            "AKS-MEM-001",
            "--config",
            str(ROOT / "examples" / "cpu-pack-config.yaml"),
            "--entities",
            str(ROOT / "examples" / "cpu-pack-entities.json"),
            "--source",
            "synthetic",
            "--grafana",
            "--output",
            str(output_dir / f"{prefix}-cpu-queries"),
        ],
        cwd=cwd,
        env=env,
    )
    _run(
        [
            *executable,
            "catalog",
            "export",
            "AKS-NP-001",
            "--config",
            str(ROOT / "examples" / "cpu-pack-config.yaml"),
            "--entities",
            str(ROOT / "examples" / "pool-pack-entities.json"),
            "--source",
            "synthetic",
            "--output",
            str(output_dir / f"{prefix}-pool-queries"),
        ],
        cwd=cwd,
        env=env,
    )
    _verify_review_packs(output_dir, prefix, executable, cwd=cwd, env=env)
    _verify_memory_packs(output_dir, prefix, executable, cwd=cwd, env=env)
    _verify_autoscaler_packs(output_dir, prefix, executable, cwd=cwd, env=env)
    _run(
        [
            *executable,
            "catalog",
            "export",
            "AKS-AS-005",
            "--config",
            str(ROOT / "examples" / "cpu-pack-config.yaml"),
            "--entities",
            str(ROOT / "examples" / "autoscaler-pack-entities.json"),
            "--source",
            "synthetic",
            "--mode",
            "guarded",
            "--output",
            str(output_dir / f"{prefix}-autoscaler-queries"),
        ],
        cwd=cwd,
        env=env,
    )


def _verify_pack_replay(
    output_dir: Path,
    stem: str,
    executable: list[str],
    case: str,
    pack_id: str,
    mode: str,
    *,
    cwd: Path,
    env: dict[str, str] | None,
    golden: bool = True,
) -> AnalysisReport:
    from aks_fleet_efficiency.config import AdvisorConfig
    from aks_fleet_efficiency.models import AnalysisReport

    config = AdvisorConfig.model_validate({"mode": mode, "packs": [pack_id]})
    config_path = output_dir / f"{stem}-config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    command = [
        *executable,
        "analyze",
        "--snapshot",
        str(ROOT / "examples/fixtures" / f"{case}-snapshot.json"),
        "--config",
        str(config_path),
        "--as-of",
        REPLAY_TIME,
    ]
    result = subprocess.run(
        [*command, "--format", "json"],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    report = AnalysisReport.model_validate_json(result.stdout)
    if report.mode != mode or [item.id for item in report.pack_provenance] != [pack_id]:
        raise RuntimeError("Selected pack replay must preserve the requested mode and scope")
    (output_dir / f"{stem}.json").write_text(result.stdout, encoding="utf-8")
    config.pack_locks = {item.id: item.digest for item in report.pack_provenance}
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    markdown = subprocess.run(
        [*command, "--format", "markdown"],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    markdown_path = output_dir / f"{stem}.md"
    markdown_path.write_text(markdown.stdout, encoding="utf-8")
    if golden:
        compare_reports(ROOT / "examples" / f"expected-{case}.md", markdown_path)
    replay = subprocess.run(
        [*command, "--format", "json"],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    if json.loads(replay.stdout) != json.loads(result.stdout):
        raise RuntimeError("Selected pack locked replay differs")
    return report


def _verify_autoscaler_packs(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    cases = [
        ("fixed-replica-pack", "AKS-AS-001"),
        ("interaction-pack", "AKS-AS-002"),
        ("hpa-pinning-pack", "AKS-AS-003"),
        ("keda-pack", "AKS-AS-004"),
        ("hpa-floor-pack", "AKS-AS-005"),
        ("hpa-change-pack", "AKS-AS-006"),
        ("vpa-bounds-pack", "AKS-AS-007"),
    ]
    for case, pack_id in cases:
        for mode in ["baseline", "guarded"]:
            report = _verify_pack_replay(
                output_dir,
                f"{prefix}-autoscaler-{case}-{mode}",
                executable,
                case,
                pack_id,
                mode,
                cwd=cwd,
                env=env,
                golden=mode == "guarded",
            )
            if pack_id == "AKS-AS-005" and mode == "baseline":
                if report.recommendations or not any(
                    item.rule_id == pack_id and "guarded_mode_required" in item.reason_codes
                    for item in report.blocked_recommendations
                ):
                    raise RuntimeError("Baseline floor pack must block numeric proposals")
            else:
                if len(report.recommendations) != 1 or report.recommendations[0].rule_id != pack_id:
                    raise RuntimeError("Autoscaler pack must produce exactly its selected finding")
                finding = report.recommendations[0]
                if (
                    finding.proposed_requests is not None
                    or finding.proposed_limits is not None
                    or finding.estimated_monthly_savings is not None
                ):
                    raise RuntimeError("Autoscaler packs cannot propose resources or savings")
                if pack_id == "AKS-AS-005":
                    if (finding.current_replica_floor, finding.proposed_replica_floor) != (2, 1):
                        raise RuntimeError(
                            "Guarded floor pack must preserve the positive 2-to-1 proposal"
                        )
                elif finding.proposed_replica_floor is not None:
                    raise RuntimeError("Autoscaler investigations cannot propose replica floors")


def _verify_memory_packs(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    for case, pack_id in [
        ("oom-pack", "AKS-MEM-001"),
        ("memory-safety-pack", "AKS-MEM-002"),
        ("memory-request-pack", "AKS-MEM-003"),
        ("pod-memory-pack", "AKS-MEM-004"),
        ("memory-limit-pack", "AKS-MEM-005"),
        ("restart-pack", "AKS-REL-001"),
        ("termination-pack", "AKS-REL-002"),
        ("eviction-pack", "AKS-REL-003"),
    ]:
        report = _verify_pack_replay(
            output_dir,
            f"{prefix}-memory-{case}",
            executable,
            case,
            pack_id,
            "guarded",
            cwd=cwd,
            env=env,
        )
        if len(report.recommendations) != 1 or report.recommendations[0].rule_id != pack_id:
            raise RuntimeError("Memory pack must produce exactly its selected finding")
        finding = report.recommendations[0]
        if finding.estimated_monthly_savings is not None:
            raise RuntimeError("Memory/reliability packs cannot establish savings")
        if pack_id == "AKS-MEM-003" and (
            finding.proposed_requests is None
            or finding.proposed_requests.memory_mib != 313
            or finding.proposed_requests.cpu_mcores is not None
            or finding.proposed_limits is not None
        ):
            raise RuntimeError("Request pack must preserve separate per-replica 313 MiB")
        if pack_id == "AKS-MEM-005" and (
            finding.proposed_limits is None
            or finding.proposed_limits.memory_mib != 600
            or finding.proposed_requests is not None
        ):
            raise RuntimeError("Limit pack must preserve separate 600 MiB limit")
        if pack_id == "AKS-MEM-004" and not any(
            item.metric == "effective_pod_memory_request" and item.value == 1184
            for item in finding.evidence
        ):
            raise RuntimeError("Accounting pack must retain 1184 MiB current context")


def _verify_review_packs(
    output_dir: Path,
    prefix: str,
    executable: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
) -> None:
    for case, pack_id in [
        ("missing-request", "AKS-RQ-001"),
        ("request-risk", "AKS-RQ-003"),
        ("pool-review", "AKS-NP-001"),
        ("scheduling-review", "AKS-SCHED-001"),
        ("capacity-review", "AKS-NP-002"),
    ]:
        report = _verify_pack_replay(
            output_dir,
            f"{prefix}-review-{case}",
            executable,
            case,
            pack_id,
            "baseline",
            cwd=cwd,
            env=env,
        )
        if len(report.recommendations) != 1 or report.recommendations[0].rule_id != pack_id:
            raise RuntimeError("Review pack must emit exactly its selected finding")
        finding = report.recommendations[0]
        if (
            finding.proposed_requests is not None
            or finding.proposed_limits is not None
            or finding.proposed_replica_floor is not None
            or finding.estimated_monthly_savings is not None
        ):
            raise RuntimeError("Review pack cannot authorize resources or savings")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the shared local and CI verification gates.")
    parser.add_argument(
        "--output-dir", type=Path, help="Retain synthetic reports and coverage here."
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check-docs", action="store_true", help="Check scoped financial command blocks only."
    )
    modes.add_argument(
        "--quick",
        action="store_true",
        help="Run static/contract checks and selected tests, without full replay or packaging.",
    )
    parser.add_argument(
        "--test",
        action="append",
        default=[],
        dest="tests",
        help="Test file or pytest node ID for --quick; repeat for each selected slice.",
    )
    arguments = parser.parse_args(argv)
    if arguments.tests and not arguments.quick:
        parser.error("--test requires --quick")
    if arguments.quick and not arguments.tests:
        parser.error("--quick requires at least one --test selection")
    if arguments.quick and arguments.output_dir is not None:
        parser.error("--output-dir is only supported by full verification")
    started = perf_counter()
    try:
        if arguments.check_docs:
            verify_documentation()
        elif arguments.quick:
            run_quick_verification(arguments.tests)
        elif arguments.output_dir is not None:
            run_verification(arguments.output_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="aks-advisor-verify-") as temporary:
                run_verification(Path(temporary))
    except subprocess.CalledProcessError as error:
        print(f"Verification stopped: command exited with {error.returncode}.", file=sys.stderr)
        return error.returncode
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        return 1
    if not arguments.check_docs:
        print(f"Verification elapsed: {perf_counter() - started:.2f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
