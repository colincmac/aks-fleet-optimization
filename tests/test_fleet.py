from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aks_fleet_efficiency import history
from aks_fleet_efficiency.artifacts import write_assessment_artifacts
from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig, OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.fleet import (
    FleetAssessment as FleetAssessmentInput,
)
from aks_fleet_efficiency.fleet import FleetInsightReport, aggregate_fleet
from aks_fleet_efficiency.models import CollectionStatus, NapManagedNode, NapPoolEvidence, Severity
from aks_fleet_efficiency.reporting.markdown import render_fleet_markdown
from aks_fleet_efficiency.rules.engine import analyze

ROOT = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000000"
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def fleet_entry(*, peer_group: str, assessment: OfflineAssessment) -> FleetAssessmentInput:
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    locked = AdvisorConfig.model_validate(
        config.model_dump()
        | {"pack_locks": {item.id: item.digest for item in assessment.report.pack_provenance}}
    )
    return FleetAssessmentInput(
        peer_group=peer_group, assessment=assessment, analysis_config=locked
    )


def assessment_inputs(
    name: str, *, tenant_id: str = TENANT, fixture: str = "pool-assessment"
) -> tuple[AssessmentFragments, OnboardingConfig]:
    replacements = {TENANT: tenant_id, "aks-synthetic": f"aks-{name}"}

    def replace(value: object) -> object:
        encoded = json.dumps(value)
        for old, new in replacements.items():
            encoded = encoded.replace(old, new)
        return json.loads(encoded)

    fragments = AssessmentFragments.model_validate(
        replace(
            json.loads((ROOT / "examples/fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))
        )
    )
    profile = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml")
    profile = OnboardingConfig.model_validate(replace(profile.model_dump(mode="json")))
    return fragments, profile


def assessment(
    name: str, *, tenant_id: str = TENANT, fixture: str = "pool-assessment"
) -> OfflineAssessment:
    fragments, profile = assessment_inputs(name, tenant_id=tenant_id, fixture=fixture)
    return assess_fragments(fragments, profile, as_of=AS_OF)


def fleet_artifacts(directory: Path, name: str, *, as_of: datetime = AS_OF) -> Path:
    fragments, profile = assessment_inputs(name)
    result = assess_fragments(fragments, profile, as_of=as_of)
    write_assessment_artifacts(directory, fragments, result, profile.analysis)
    return directory / "assessment.json"


def historical_node_payload() -> dict[str, Any]:
    cluster = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic"
        "/providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
    )
    start = AS_OF - timedelta(minutes=10)

    def receipt(at: datetime) -> dict[str, object]:
        return {
            "collector": "synthetic-history",
            "status": "complete",
            "requested_scope": [cluster],
            "completed_scope": [cluster],
            "started_at": at,
            "completed_at": at,
            "source_observed_at": at,
            "pagination_complete": True,
        }

    payload = {
        "tenant_id": TENANT,
        "cluster_resource_id": cluster,
        "cluster_uid": "synthetic-uid",
        "source": "synthetic-history",
        "source_version": "1.0.0",
        "profile": "synthetic-node-uid-history",
        "profile_version": "1.0.0",
        "mapping_reference": "synthetic-explicit-historical-node-uids",
        "window_start": start,
        "window_end": AS_OF,
        "step_seconds": 300,
        "cpu_rate_window_seconds": 300,
        "cpu_receipt": receipt(AS_OF),
        "memory_receipt": receipt(AS_OF),
        "points": [
            {
                "timestamp": start + timedelta(seconds=index * 300),
                "membership_receipt": receipt(start + timedelta(seconds=index * 300)),
                "members": [
                    {"node_uid": name, "node_resource_id": f"{cluster}/nodes/{name}"}
                    for name in ["node-a", "node-b"]
                ],
                "contributions": [
                    {
                        "node_uid": name,
                        "node_resource_id": f"{cluster}/nodes/{name}",
                        "cpu_mcpu": value,
                        "memory_working_set_mib": 100.0,
                        "cpu_sampled_at": start + timedelta(seconds=index * 300),
                        "memory_sampled_at": start + timedelta(seconds=index * 300),
                    }
                    for name, value in zip(["node-a", "node-b"], values, strict=True)
                ],
            }
            for index, values in enumerate([(0.0, 1000.0), (1000.0, 0.0), (0.0, 1000.0)])
        ],
    }
    return payload


def test_historical_node_envelope_sums_aligned_values_before_percentiles() -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, review_node_history

    payload = historical_node_payload()
    evidence = HistoricalNodeEvidence.model_validate(payload)
    original = evidence.model_dump_json()
    result = review_node_history(evidence, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert result.cpu_p95_mcpu == 1000.0
    assert result.memory_p99_working_set_mib == 200.0
    assert result.source_admission == "unverified_saved_contributions"
    assert evidence.model_dump_json() == original
    payload["points"][1]["contributions"][0]["cpu_mcpu"] = None
    partial = review_node_history(
        HistoricalNodeEvidence.model_validate(payload),
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    assert partial.cpu_p95_mcpu is None
    assert partial.memory_p99_working_set_mib == 200.0


@pytest.mark.parametrize(
    "problem",
    [
        "missing_membership",
        "missing_point",
        "missing_node",
        "missing_clock",
        "partial",
        "foreign_receipt",
        "stale_cpu",
        "future_cpu",
        "stale_tail",
        "future_membership",
    ],
)
def test_historical_node_evidence_gaps_never_become_zero(problem: str) -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, review_node_history

    payload = historical_node_payload()
    point = payload["points"][1]
    clock = AS_OF
    if problem == "missing_membership":
        point["members"] = None
    elif problem == "missing_point":
        payload["points"].pop(1)
    elif problem == "missing_node":
        point["contributions"].pop()
    elif problem == "missing_clock":
        point["contributions"][0]["cpu_sampled_at"] = None
    elif problem == "partial":
        payload["cpu_receipt"]["status"] = "partial"
        payload["cpu_receipt"]["missing_fields"] = ["synthetic-missing-query"]
    elif problem == "foreign_receipt":
        payload["cpu_receipt"]["requested_scope"] = ["synthetic-foreign-scope"]
        payload["cpu_receipt"]["completed_scope"] = ["synthetic-foreign-scope"]
    elif problem == "stale_cpu":
        point["contributions"][0]["cpu_sampled_at"] -= timedelta(seconds=301)
    elif problem == "future_cpu":
        point["contributions"][0]["cpu_sampled_at"] += timedelta(seconds=1)
    elif problem == "future_membership":
        point["membership_receipt"]["source_observed_at"] += timedelta(seconds=1)
        point["membership_receipt"]["completed_at"] += timedelta(seconds=1)
    else:
        clock += timedelta(seconds=3601)
    result = review_node_history(
        HistoricalNodeEvidence.model_validate(payload),
        as_of=clock,
        maximum_source_age_seconds=3600,
    )
    assert result.cpu_p95_mcpu is None and result.cpu_gaps
    if problem in {"partial", "foreign_receipt", "stale_tail"}:
        assert all(point.cpu_mcpu is None for point in result.points)
    if problem in {"missing_clock", "partial", "foreign_receipt", "stale_cpu", "future_cpu"}:
        assert result.memory_p99_working_set_mib == 200.0
    else:
        assert result.memory_p99_working_set_mib is None and result.memory_gaps


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate_node",
        "duplicate_point",
        "foreign_node",
        "changed_binding",
        "off_grid",
        "negative",
        "boolean",
        "nonfinite",
        "substitute_memory_measure",
        "naive",
    ],
)
def test_historical_node_evidence_rejects_ambiguous_or_malformed_values(problem: str) -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, review_node_history

    payload = historical_node_payload()
    point = payload["points"][1]
    if problem == "duplicate_node":
        point["contributions"].append(point["contributions"][0])
    elif problem == "duplicate_point":
        payload["points"].append(point)
    elif problem == "foreign_node":
        point["contributions"][0]["node_uid"] = "synthetic-foreign-node"
    elif problem == "changed_binding":
        point["contributions"][0]["node_resource_id"] += "-changed"
    elif problem == "off_grid":
        point["timestamp"] += timedelta(seconds=1)
    elif problem in {"negative", "boolean", "nonfinite"}:
        point["contributions"][0]["cpu_mcpu"] = {
            "negative": -1.0,
            "boolean": True,
            "nonfinite": float("inf"),
        }[problem]
    elif problem == "substitute_memory_measure":
        payload["memory_measure"] = "container_memory_working_set_bytes"
    else:
        point["timestamp"] = point["timestamp"].replace(tzinfo=None)
    with pytest.raises(ValueError):
        review_node_history(
            HistoricalNodeEvidence.model_validate(payload),
            as_of=AS_OF,
            maximum_source_age_seconds=3600,
        )


def test_historical_node_empty_roster_and_age_boundary_are_explicit() -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, review_node_history

    payload = historical_node_payload()
    for point in payload["points"]:
        point["members"] = []
        point["contributions"] = []
        point["membership_receipt"]["completed_at"] = AS_OF
    evidence = HistoricalNodeEvidence.model_validate(payload)
    result = review_node_history(
        evidence,
        as_of=AS_OF + timedelta(seconds=3600),
        maximum_source_age_seconds=3600,
    )
    assert result.cpu_p95_mcpu == result.memory_p99_working_set_mib == 0.0
    assert result.source_admission == "unverified_saved_contributions"


@pytest.mark.parametrize("value", [5e307, 1e308])
def test_historical_resource_overflow_does_not_erase_independent_memory(value: float) -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, review_node_history

    payload = historical_node_payload()
    for point in payload["points"]:
        for row in point["contributions"]:
            row["cpu_mcpu"] = value
    result = review_node_history(
        HistoricalNodeEvidence.model_validate(payload),
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    assert result.cpu_p95_mcpu is None and result.cpu_gaps
    assert result.memory_p99_working_set_mib == 200.0


def test_fleet_historical_envelopes_bind_originals_and_align_clusters() -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence

    entries = []
    for name in ["primary", "peer"]:
        entry = fleet_entry(peer_group="synthetic", assessment=assessment(name))
        cluster = entry.assessment.snapshot.clusters[0]
        payload = historical_node_payload()
        payload.update(cluster_resource_id=cluster.resource_id, cluster_uid=cluster.uid)
        shift = payload["window_end"] - entry.assessment.report.observation_window.end
        payload["window_start"] -= shift
        payload["window_end"] -= shift
        for point in payload["points"]:
            point["timestamp"] -= shift
            for field in ["started_at", "completed_at", "source_observed_at"]:
                point["membership_receipt"][field] -= shift
            for contribution in point["contributions"]:
                contribution["cpu_sampled_at"] -= shift
                contribution["memory_sampled_at"] -= shift
        receipts = [payload["cpu_receipt"], payload["memory_receipt"]] + [
            point["membership_receipt"] for point in payload["points"]
        ]
        for receipt in receipts:
            receipt.update(
                requested_scope=[cluster.resource_id], completed_scope=[cluster.resource_id]
            )
        entry.node_history = [HistoricalNodeEvidence.model_validate(payload)]
        entries.append(entry)
    report = aggregate_fleet(entries, generated_at=AS_OF)
    assert report.clusters[0].historical_usage is not None
    history = report.peer_groups[0].historical_usage
    assert history is not None and history.cpu_p95_mcpu == 2000.0
    assert history.memory_p99_working_set_mib == 400.0
    assert "Historical CPU P95 mCPU" in render_fleet_markdown(report)
    entries[0].node_history[0].points[0].contributions[0].cpu_mcpu = None
    partial = aggregate_fleet(entries, generated_at=AS_OF).peer_groups[0].historical_usage
    assert partial is not None and partial.cpu_p95_mcpu is None
    assert partial.memory_p99_working_set_mib == 400.0
    entries[0].node_history[0].cluster_uid = "synthetic-foreign-incarnation"
    with pytest.raises(ValueError, match="fingerprint"):
        aggregate_fleet(entries, generated_at=AS_OF)


def test_historical_node_cli_is_offline_scoped_and_exclusive(tmp_path: Path) -> None:
    from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, HistoricalNodeReview

    evidence = HistoricalNodeEvidence.model_validate(historical_node_payload())
    source = tmp_path / "history.json"
    source.write_text(evidence.model_dump_json(), encoding="utf-8")
    output = tmp_path / "review.json"
    arguments = [
        "fleet",
        "review-node-history",
        "--history",
        str(source),
        "--tenant",
        TENANT,
        "--cluster",
        evidence.cluster_resource_id,
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    runner = CliRunner()
    response = runner.invoke(app, arguments)
    assert response.exit_code == 0, response.output
    result = HistoricalNodeReview.model_validate_json(output.read_bytes())
    assert result.cpu_p95_mcpu == 1000.0
    original = output.read_bytes()
    assert runner.invoke(app, arguments).exit_code == 1
    assert output.read_bytes() == original
    output.unlink()
    invalid = list(arguments)
    invalid[invalid.index("--tenant") + 1] = "SENSITIVE-FOREIGN-TENANT"
    denied = runner.invoke(app, invalid)
    assert denied.exit_code == 2 and not output.exists()
    assert "SENSITIVE-FOREIGN-TENANT" not in denied.output


def fleet_context_payload() -> dict[str, Any]:
    payload = historical_node_payload()
    return {
        "tenant_id": TENANT,
        "cluster_resource_id": payload["cluster_resource_id"],
        "cluster_uid": payload["cluster_uid"],
        "source": "synthetic-registry",
        "source_version": "1.0.0",
        "observed_at": AS_OF,
        "source_profile": "synthetic-fleet-context",
        "source_profile_version": "1.0.0",
        "owner_declarations": [
            {
                "namespace_uid": "synthetic-namespace",
                "workload_uid": "synthetic-workload",
                "owner_ref": "a" * 64,
                "valid_from": AS_OF - timedelta(days=30),
                "valid_until": AS_OF + timedelta(days=1),
            }
        ],
        "market_history": {
            "window_start": payload["window_start"],
            "window_end": payload["window_end"],
            "step_seconds": 300,
            "points": [
                {
                    "timestamp": point["timestamp"],
                    "receipt": point["membership_receipt"],
                    "nodes": [{**row, "market": "spot"} for row in point["members"]],
                }
                for point in payload["points"]
            ],
        },
    }


def test_fleet_context_keeps_declared_ownership_and_market_source_boundaries() -> None:
    from aks_fleet_efficiency.fleet_context import FleetContext, review_fleet_context

    evidence = FleetContext.model_validate(fleet_context_payload())
    arguments = dict(
        tenant_id=TENANT,
        cluster_resource_id=evidence.cluster_resource_id,
        cluster_uid=evidence.cluster_uid,
        window_start=AS_OF - timedelta(days=30),
        window_end=AS_OF,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
        workload_identities=[("synthetic-namespace", "synthetic-workload")],
    )
    result = review_fleet_context(evidence, **arguments)
    assert result.business_owners[0].status == "declared"
    assert result.business_owners[0].owner_ref == "a" * 64
    assert result.market_history is not None
    assert result.market_history.points[0].market_counts == {"spot": 2, "regular": 0, "unknown": 0}
    assert result.market_history.fallback_records is None
    assert result.source_admission == "unverified_saved_context"
    evidence.owner_declarations.append(
        evidence.owner_declarations[0].model_copy(update={"owner_ref": "b" * 64})
    )
    conflicting = review_fleet_context(evidence, **arguments)
    assert conflicting.business_owners[0].status == "conflicting"
    assert conflicting.business_owners[0].owner_ref is None
    evidence.cluster_uid = "synthetic-recreated-cluster"
    with pytest.raises(ValueError):
        review_fleet_context(evidence, **arguments)


@pytest.mark.parametrize(
    "problem",
    [
        "stale_owner",
        "future_owner",
        "owner_window",
        "missing_owner",
        "partial_market",
        "missing_market_point",
        "unknown_market",
        "conflicting_market",
        "duplicate_node",
    ],
)
def test_fleet_context_keeps_independent_gaps_explicit(problem: str) -> None:
    from aks_fleet_efficiency.fleet_context import FleetContext, review_fleet_context

    payload = fleet_context_payload()
    if problem == "stale_owner":
        payload["observed_at"] -= timedelta(seconds=3601)
    elif problem == "future_owner":
        payload["observed_at"] += timedelta(seconds=1)
    elif problem == "owner_window":
        payload["owner_declarations"][0]["valid_from"] = AS_OF
    elif problem == "missing_owner":
        payload["owner_declarations"] = []
    elif problem == "partial_market":
        payload["market_history"]["points"][0]["receipt"].update(
            status="partial",
            missing_fields=["synthetic-market-gap"],
        )
    elif problem == "missing_market_point":
        payload["market_history"]["points"].pop(0)
    elif problem == "unknown_market":
        payload["market_history"]["points"][0]["nodes"][0]["market"] = "unknown"
    elif problem == "conflicting_market":
        payload["market_history"]["points"][0]["nodes"][0]["market"] = "regular"
    else:
        payload["market_history"]["points"][0]["nodes"].append(
            payload["market_history"]["points"][0]["nodes"][0],
        )
    evidence = FleetContext.model_validate(payload)

    def review() -> Any:
        return review_fleet_context(
            evidence,
            tenant_id=TENANT,
            cluster_resource_id=evidence.cluster_resource_id,
            cluster_uid=evidence.cluster_uid,
            window_start=AS_OF - timedelta(days=30),
            window_end=AS_OF,
            as_of=AS_OF,
            maximum_source_age_seconds=3600,
            workload_identities=[("synthetic-namespace", "synthetic-workload")],
        )

    if problem == "duplicate_node":
        with pytest.raises(ValueError):
            review()
        return
    result = review()
    owner = result.business_owners[0]
    assert result.market_history is not None
    point = result.market_history.points[0]
    if problem in {"stale_owner", "future_owner", "owner_window", "missing_owner"}:
        assert owner.status == "unknown" and owner.owner_ref is None
        assert point.market_counts["spot"] == 2
    elif problem == "unknown_market":
        assert owner.status == "declared"
        assert point.market_counts == {"spot": 1, "regular": 0, "unknown": 1}
    else:
        assert owner.status == "declared"
        assert point.market_counts is None and point.reason_codes
    assert result.market_history.fallback_records is None


def test_fleet_context_routes_exact_current_owners_without_changing_findings() -> None:
    from aks_fleet_efficiency.fleet_context import FleetContext

    entries = [
        fleet_entry(
            peer_group="synthetic",
            assessment=assessment(name, fixture="daemonset-overhead-assessment"),
        )
        for name in ["primary", "peer"]
    ]
    baseline = aggregate_fleet(entries, generated_at=AS_OF)
    for entry in entries:
        cluster = entry.assessment.snapshot.clusters[0]
        assert cluster.scheduling is not None
        pod = next(item for item in cluster.scheduling.pods if item.workload_uid is not None)
        payload = fleet_context_payload()
        payload.update(
            cluster_resource_id=cluster.resource_id, cluster_uid=cluster.uid, market_history=None
        )
        payload["owner_declarations"][0].update(
            namespace_uid=pod.namespace_uid,
            workload_uid=pod.workload_uid,
            valid_from=entry.assessment.report.observation_window.start,
        )
        entry.external_context = [FleetContext.model_validate(payload)]
    result = aggregate_fleet(entries, generated_at=AS_OF)
    assert result.summary == baseline.summary
    assert result.rule_counts == baseline.rule_counts
    for cluster in result.clusters:
        assert cluster.external_context is not None
        assert cluster.external_context.business_owners[0].status == "declared"
    assert "business routing" in render_fleet_markdown(result)


@pytest.mark.parametrize(
    ("command", "fixture", "input_flag"),
    [
        ("history", "node-history-evidence.json", "--history"),
        ("nap", "nap-policy-input.json", "--policy"),
    ],
)
def test_new_canonical_evidence_examples_run_through_real_cli(
    tmp_path: Path, command: str, fixture: str, input_flag: str
) -> None:
    source = ROOT / "examples/fixtures" / fixture
    payload = json.loads(source.read_text(encoding="utf-8"))
    args = ["fleet", "review-node-history"] if command == "history" else ["review-nap-policy"]
    output = tmp_path / "review.json"
    response = CliRunner().invoke(
        app,
        [
            *args,
            input_flag,
            str(source),
            "--tenant",
            payload["tenant_id"],
            "--cluster",
            payload["cluster_resource_id"],
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )
    assert response.exit_code == 0, response.output
    result = json.loads(output.read_text(encoding="utf-8"))
    if command == "history":
        assert result["cpu_p95_mcpu"] == 1000.0
        assert result["memory_p99_working_set_mib"] == 200.0
        assert result["source_admission"] == "unverified_saved_contributions"
    else:
        assert result["reasons"]["Empty"]["configured_limit"] == 1
        assert result["reasons"]["Drifted"]["configured_limit"] == 2
        assert result["controller_admission"] == "unverified"


def test_fleet_artifact_trends_preserve_independent_chronology(tmp_path: Path) -> None:
    inputs = []
    for name, samples in [("primary", 3), ("peer", 2)]:
        for offset in range(samples):
            path = fleet_artifacts(
                tmp_path / f"{name}-{offset}", name, as_of=AS_OF + timedelta(hours=offset)
            )
            inputs.append((path.parent, "production"))
    report = history.summarize_fleet_artifacts(inputs, tenant_id=TENANT)
    assert len(report.series) == 2
    assert report.estimated_monthly_savings is None
    assert history.summarize_fleet_artifacts(list(reversed(inputs)), tenant_id=TENANT) == report
    for series in report.series:
        assert series.comparable
        assert len(series.comparisons) == len(series.runs) - 1
        assert series.recurring_findings
        assert all(item.observed_runs == len(series.runs) for item in series.recurring_findings)
        assert series.runs[0].generated_at == AS_OF
        assert series.runs[-1].generated_at == AS_OF + timedelta(hours=len(series.runs) - 1)
        assert all(pair.comparable for pair in series.comparisons)
    assert not (tmp_path / "history").exists()


def test_grafana_fleet_snapshot_renders_only_retained_evidence(tmp_path: Path) -> None:
    inputs = []
    for offset in range(2):
        fragments, config = assessment_inputs("primary", fixture="daemonset-overhead-assessment")
        for node in fragments.kubernetes[0].resources:
            if node.kind == "Node":
                node.status["capacity"] = {"cpu": "3", "memory": "1536Mi"}
                node.status["allocatable"] = {"cpu": "500m", "memory": "1536Mi"}
        as_of = AS_OF + timedelta(hours=offset)
        value = assess_fragments(fragments, config, as_of=as_of)
        directory = tmp_path / str(offset)
        write_assessment_artifacts(directory, fragments, value, config.analysis)
        inputs.append(directory / "assessment.json")
    group = "<tag> | ${__from}"
    args = [
        "fleet",
        "trends",
        "--format",
        "grafana",
        "--as-of",
        as_of.isoformat(),
        "--tenant",
        TENANT,
    ]
    for path in inputs:
        args += ["--assessment", str(path), "--peer-group", group]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    dashboard = json.loads(result.stdout)
    content = "\n".join(panel["options"]["content"] for panel in dashboard["panels"])
    assert all(
        "datasource" not in panel and "targets" not in panel for panel in dashboard["panels"]
    )
    assert "| A - R | -500 | 2368 |" in content
    assert "| C - A | 5000 | 0 |" in content
    assert "aligned_cluster_usage_unavailable" in content
    assert "Comparable latest pair" in content
    assert "Immutably replayed" in content
    assert "Check coverage: Unknown" in content
    assert "Examined subjects" in content
    assert "Blocked records" in content
    assert "<tag>" not in content and "${__from}" not in content
    assert str(tmp_path) not in content


def test_fleet_drift_matrix_separates_recurrence_and_current_coverage(tmp_path: Path) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    latest = AS_OF + timedelta(hours=1)
    second = fleet_artifacts(tmp_path / "second", "primary", as_of=latest)
    singleton = fleet_artifacts(tmp_path / "peer", "peer", as_of=latest)
    result = CliRunner().invoke(
        app,
        [
            "fleet",
            "trends",
            "--format",
            "matrix",
            "--as-of",
            (latest + timedelta(hours=1)).isoformat(),
            "--tenant",
            TENANT,
            "--assessment",
            str(first),
            "--peer-group",
            "production",
            "--assessment",
            str(second),
            "--peer-group",
            "production",
            "--assessment",
            str(singleton),
            "--peer-group",
            "production",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    primary = next(
        row for row in data["rows"] if row["cluster_resource_id"].endswith("aks-primary")
    )
    assert primary["latest"]["age_seconds"] == 3600
    assert primary["latest"]["run"]["window_start"] == "2026-09-29T00:00:00Z"
    assert primary["latest"]["metric_coverage_ratio"] == 1.0
    assert primary["latest_comparison"]["comparable"]
    assert primary["recurring_findings"]
    assert str(tmp_path) not in result.stdout
    peer = next(row for row in data["rows"] if row["cluster_resource_id"].endswith("aks-peer"))
    assert peer["reason_codes"] == ["insufficient_samples"]
    assert peer["latest_comparison"] is None
    assert peer["recurring_findings"] is None


def test_fleet_check_evidence_does_not_turn_stale_evidence_into_a_pass(tmp_path: Path) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    latest = AS_OF + timedelta(days=2)
    second = fleet_artifacts(tmp_path / "second", "primary", as_of=latest)
    inputs = [(first.parent, "production"), (second.parent, "production")]
    row = history.project_fleet_drift_matrix(inputs, tenant_id=TENANT, as_of=latest).rows[0]
    comparison = row.latest_comparison
    prior = row.prior_comparable_resources
    assert comparison is not None and comparison.comparable and prior is not None
    assert any(
        item.rule_id == "AKS-NP-001" and item.state == "blocked" for item in comparison.findings
    )
    assert row.latest.check_evidence is not None and prior.check_evidence is not None
    assert row.latest.check_evidence.coverage_reason == "expected_subject_roster_not_retained"
    assert prior.check_evidence.coverage_reason == row.latest.check_evidence.coverage_reason
    latest_packs = {item.pack_id: item for item in row.latest.check_evidence.packs}
    prior_packs = {item.pack_id: item for item in prior.check_evidence.packs}
    assert prior_packs["AKS-NP-001"].qualified_findings == 1
    blocked = latest_packs["AKS-NP-001"]
    assert (blocked.examined_subjects, blocked.qualified_findings, blocked.blocked_records) == (
        1,
        0,
        1,
    )
    assert blocked.version == prior_packs["AKS-NP-001"].version == "1.0.0"
    assert latest_packs["AKS-NP-003"].examined_subjects == 0


def test_fleet_check_evidence_keeps_inventory_blockers_without_examined_subjects(
    tmp_path: Path,
) -> None:
    inputs = []
    for offset in range(2):
        fragments, config = assessment_inputs("primary")
        fragments.azure[0].clusters[0].node_provisioning_mode = "Auto"
        config.analysis = AdvisorConfig(packs=["AKS-NP-003"])
        as_of = AS_OF + timedelta(hours=offset)
        value = assess_fragments(fragments, config, as_of=as_of)
        directory = tmp_path / str(offset)
        write_assessment_artifacts(directory, fragments, value, config.analysis)
        inputs.append((directory, "production"))

    evidence = (
        history.project_fleet_drift_matrix(inputs, tenant_id=TENANT, as_of=as_of)
        .rows[0]
        .latest.check_evidence
    )
    assert evidence is not None
    (pack,) = evidence.packs
    assert pack.pack_id == "AKS-NP-003"
    assert pack.examined_subjects == pack.qualified_findings == 0
    assert pack.blocked_records == 1
    assert evidence.coverage_reason == "expected_subject_roster_not_retained"


@pytest.mark.parametrize("change", ["source", "policy", "absent", "recreated_cluster", "future"])
def test_fleet_drift_matrix_refuses_changed_basis_without_claiming_resolution(
    tmp_path: Path,
    change: str,
) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    fragments, profile = assessment_inputs("primary")
    if change == "source":
        profile.metric_sources[0].name = "replacement-source"
        profile.clusters[0].metric_source = "replacement-source"
        fragments.metrics[0].source_name = "replacement-source"
        fragments.workload_assessments = []
    elif change == "policy":
        profile.analysis.mode = "baseline"
    elif change == "absent":
        fragments.metrics = []
    elif change == "recreated_cluster":
        metadata = fragments.kubernetes[0]
        metadata.cluster_uid = "synthetic-new-fingerprint"
        next(
            item for item in metadata.resources if item.name == "kube-system"
        ).uid = metadata.cluster_uid
    as_of = AS_OF + timedelta(hours=1)
    result = assess_fragments(fragments, profile, as_of=as_of)
    later = tmp_path / "later"
    write_assessment_artifacts(later, fragments, result, profile.analysis)
    if change == "future":
        command = [
            "fleet",
            "trends",
            "--format",
            "matrix",
            "--as-of",
            AS_OF.isoformat(),
            "--tenant",
            TENANT,
            "--assessment",
            str(first),
            "--peer-group",
            "production",
            "--assessment",
            str(later / "assessment.json"),
            "--peer-group",
            "production",
        ]
        rejected = CliRunner().invoke(app, command)
        assert rejected.exit_code == 2
        assert str(tmp_path) not in rejected.stdout
        return
    matrix = history.project_fleet_drift_matrix(
        [(first.parent, "production"), (later, "production")],
        tenant_id=TENANT,
        as_of=as_of,
    )
    if change == "recreated_cluster":
        assert len(matrix.rows) == 2
        assert all(row.latest_comparison is None for row in matrix.rows)
        return
    row = matrix.rows[0]
    comparison = row.latest_comparison
    assert comparison is not None
    if change == "absent":
        assert comparison.comparable
        assert any(item.state == "not_observed" for item in comparison.findings)
        assert row.latest.metric_coverage_ratio == 0
    else:
        assert not comparison.comparable
        assert row.recurring_findings is None
        assert row.prior_comparable_resources is None


def test_fleet_drift_matrix_blocks_controller_recreation_and_caps_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = []
    for offset in range(2):
        fragments, config = assessment_inputs("primary", fixture="autoscalers-assessment")
        if offset:
            hpa = next(
                item
                for item in fragments.kubernetes[0].resources
                if item.kind == "HorizontalPodAutoscaler"
            )
            hpa.uid = "synthetic-recreated-hpa"
        as_of = AS_OF + timedelta(hours=offset)
        assessment = assess_fragments(fragments, config, as_of=as_of)
        directory = tmp_path / str(offset)
        write_assessment_artifacts(directory, fragments, assessment, config.analysis)
        inputs.append((directory, "production"))

    matrix = history.project_fleet_drift_matrix(inputs, tenant_id=TENANT, as_of=as_of)
    row = matrix.rows[0]
    assert row.reason_codes == ["controller_identity_changed"]
    assert row.latest_comparison is not None and not row.latest_comparison.comparable
    assert row.recurring_findings is None
    monkeypatch.setattr(history, "MAXIMUM_DRIFT_BYTES", 1024)
    with pytest.raises(ValueError, match="projection byte budget"):
        history.project_fleet_drift_matrix(inputs, tenant_id=TENANT, as_of=as_of)


def test_fleet_trends_cli_is_read_only_and_redacts_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    second = fleet_artifacts(tmp_path / "second", "primary", as_of=AS_OF + timedelta(hours=1))
    original = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    original_paths = set(tmp_path.rglob("*"))

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network and history storage are forbidden")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(history, "_publish", denied)
    peer = "<script>synthetic-private-marker</script>"
    arguments = [
        "fleet",
        "trends",
        "--assessment",
        str(first),
        "--peer-group",
        peer,
        "--assessment",
        str(second),
        "--peer-group",
        peer,
        "--tenant",
    ]
    result = CliRunner().invoke(app, [*arguments, TENANT])
    assert result.exit_code == 0, result.output
    report = history.FleetHistoryTrend.model_validate_json(result.stdout)
    assert report.series[0].peer_group == peer
    assert report == history.summarize_fleet_artifacts(
        [(first.parent, peer), (second.parent, peer)], tenant_id=TENANT
    )
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == original
    assert set(tmp_path.rglob("*")) == original_paths
    invalid = CliRunner().invoke(app, [*arguments, "synthetic-private-marker"])
    assert invalid.exit_code == 2
    assert "synthetic-private-marker" not in invalid.output


def test_fleet_trends_keep_incompatible_series_separate(tmp_path: Path) -> None:
    inputs = []
    for name in ["primary", "peer"]:
        first = fleet_artifacts(tmp_path / f"{name}-first", name)
        fragments, profile = assessment_inputs(name)
        if name == "peer":
            profile.analysis.mode = "baseline"
        result = assess_fragments(fragments, profile, as_of=AS_OF + timedelta(hours=1))
        later = tmp_path / f"{name}-later"
        write_assessment_artifacts(later, fragments, result, profile.analysis)
        inputs.extend([(first.parent, "production"), (later, "production")])
    report = history.summarize_fleet_artifacts(inputs, tenant_id=TENANT)
    valid = next(item for item in report.series if item.cluster_resource_id.endswith("aks-primary"))
    incompatible = next(
        item for item in report.series if item.cluster_resource_id.endswith("aks-peer")
    )
    assert valid.comparable and valid.recurring_findings
    assert not incompatible.comparable
    assert incompatible.recurring_findings is None
    assert incompatible.reason_codes == ["comparison_basis_changed"]
    assert {item.state for item in incompatible.comparisons[0].findings} == {"not_comparable"}


@pytest.mark.parametrize("stale", [False, True])
def test_fleet_trends_missing_or_stale_history_never_resolves(tmp_path: Path, stale: bool) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    fragments, profile = assessment_inputs("primary")
    if not stale:
        fragments.metrics = []
    evaluated_at = AS_OF + (timedelta(days=2) if stale else timedelta(hours=1))
    result = assess_fragments(fragments, profile, as_of=evaluated_at)
    later = tmp_path / "later"
    write_assessment_artifacts(later, fragments, result, profile.analysis)
    report = history.summarize_fleet_artifacts(
        [(first.parent, "production"), (later, "production")], tenant_id=TENANT
    )
    series = report.series[0]
    assert series.comparable
    pool = next(item for item in series.comparisons[0].findings if item.rule_id == "AKS-NP-001")
    assert pool.state == ("blocked" if stale else "not_observed")
    assert not any(item.rule_id == "AKS-NP-001" for item in series.recurring_findings or [])


@pytest.mark.parametrize("recreated", [False, True])
def test_fleet_trends_do_not_join_changed_peer_or_fingerprint(
    tmp_path: Path, recreated: bool
) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    fragments, profile = assessment_inputs("primary")
    if recreated:
        fragments.kubernetes[0].cluster_uid = "synthetic-recreated-cluster"
        for resource in fragments.kubernetes[0].resources:
            if resource.kind == "Namespace" and resource.name == "kube-system":
                resource.uid = "synthetic-recreated-cluster"
    result = assess_fragments(fragments, profile, as_of=AS_OF + timedelta(hours=1))
    later = tmp_path / "later"
    write_assessment_artifacts(later, fragments, result, profile.analysis)
    report = history.summarize_fleet_artifacts(
        [(first.parent, "production"), (later, "production" if recreated else "changed-peer")],
        tenant_id=TENANT,
    )
    assert len(report.series) == 2
    assert all(item.reason_codes == ["insufficient_samples"] for item in report.series)
    assert all(item.recurring_findings is None and not item.comparisons for item in report.series)


def test_fleet_trends_reject_duplicates_and_bound_total_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    second = fleet_artifacts(tmp_path / "second", "primary", as_of=AS_OF + timedelta(hours=1))
    inputs = [(first.parent, "production"), (second.parent, "production")]
    with pytest.raises(ValueError, match="distinct"):
        history.summarize_fleet_artifacts([inputs[0], inputs[0]], tenant_id=TENANT)
    combined_bytes = sum(
        (directory / name).stat().st_size
        for directory, _ in inputs
        for name in history.ARTIFACT_NAMES
    )
    monkeypatch.setattr(history, "MAXIMUM_TREND_BYTES", combined_bytes - 1)
    with pytest.raises(ValueError, match="byte limit"):
        history.summarize_fleet_artifacts(inputs, tenant_id=TENANT)
    monkeypatch.undo()
    with pytest.raises(ValueError, match="two and 100"):
        history.summarize_fleet_artifacts(inputs * 51, tenant_id=TENANT)
    with pytest.raises(ValueError, match="two and 100"):
        history.summarize_fleet_artifacts(inputs[:1], tenant_id=TENANT)


@pytest.mark.parametrize("defect", ["fingerprint", "clock", "tenant"])
def test_fleet_trends_reject_unbound_identity_or_ambiguous_time(
    tmp_path: Path, defect: str
) -> None:
    first = fleet_artifacts(tmp_path / "first", "primary")
    fragments, profile = assessment_inputs(
        "primary",
        tenant_id="11111111-1111-1111-1111-111111111111" if defect == "tenant" else TENANT,
    )
    if defect == "fingerprint":
        fragments.kubernetes = []
    elif defect == "clock":
        profile.analysis.mode = "baseline"
    result = assess_fragments(
        fragments, profile, as_of=AS_OF if defect == "clock" else AS_OF + timedelta(hours=1)
    )
    later = tmp_path / "later"
    write_assessment_artifacts(later, fragments, result, profile.analysis)
    with pytest.raises(
        ValueError,
        match={"fingerprint": "fingerprint", "clock": "ordered", "tenant": "tenant"}[defect],
    ):
        history.summarize_fleet_artifacts(
            [(first.parent, "production"), (later, "production")], tenant_id=TENANT
        )


def test_fleet_aggregation_is_deterministic_and_preserves_cluster_evidence() -> None:
    first = assessment("primary")
    second = assessment("peer")
    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=second),
            fleet_entry(peer_group="production", assessment=first),
        ],
        generated_at=AS_OF,
    )

    assert report.comparable
    assert report.comparability_reasons == []
    assert [item.cluster_resource_id for item in report.clusters] == sorted(
        [item.cluster_resource_id for item in report.clusters]
    )
    assert {item.peer_group for item in report.clusters} == {"production"}
    assert report.summary.clusters == 2
    assert report.summary.recommendations == sum(
        item.report.summary.recommendations for item in [first, second]
    )
    assert report.summary.blocked_recommendations == sum(
        item.report.summary.blocked_recommendations for item in [first, second]
    )
    assert report.summary.estimated_monthly_savings is None
    assert sum(report.rule_counts.values()) == report.summary.recommendations
    assert sum(report.blocked_reason_counts.values()) >= report.summary.blocked_recommendations
    assert all(
        sum(item.source_status_counts.values()) == len(item.source_capabilities)
        for item in report.clusters
    )
    assert type(report).model_validate_json(report.model_dump_json()) == report


def test_fleet_breaks_down_current_supply_and_findings_by_cluster_and_peer_group() -> None:
    entries = [
        fleet_entry(peer_group="production", assessment=assessment(name))
        for name in ["primary", "peer"]
    ]

    report = aggregate_fleet(entries, generated_at=AS_OF)

    for cluster in report.clusters:
        assert cluster.supply_inventory.status == "partial"
        assert cluster.supply_inventory.pool_counts == {"fixed": 1}
        assert "nap_nodepool_inventory_unknown" in cluster.supply_inventory.reason_codes
        assert cluster.workload_inventory.status == "available"
        assert cluster.workload_inventory.observed_pods == 0
        assert cluster.workload_inventory.workload_counts == {}
        assert cluster.rule_counts == {"AKS-NP-001": 1, "AKS-NP-002": 1}
        assert sum(cluster.category_counts.values()) == cluster.recommendations
    assert len(report.peer_groups) == 1
    group = report.peer_groups[0]
    assert group.peer_group == "production"
    assert group.comparable
    assert group.clusters == 2
    assert group.rule_counts == {"AKS-NP-001": 2, "AKS-NP-002": 2}
    assert group.category_counts == report.category_counts
    assert group.supply_pool_counts == {"fixed": 2}
    assert group.inventory_status_counts["supply"] == {"partial": 2}
    assert group.workload_counts == {}


def test_fleet_inventory_does_not_turn_stale_evidence_into_zero_counts() -> None:
    first = assessment("primary")
    second = assessment("peer")
    second.snapshot.clusters[0].capacity.azure_observed_at = AS_OF - timedelta(hours=25)
    second.snapshot.clusters[0].scheduling.observed_at = AS_OF - timedelta(hours=25)
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    cluster = next(item for item in report.clusters if item.cluster_name == "aks-peer")
    assert cluster.supply_inventory.status == "unknown"
    assert cluster.supply_inventory.pool_counts is None
    assert cluster.supply_inventory.arm_pool_market.pool_counts is None
    assert cluster.workload_inventory.status == "unknown"
    assert cluster.workload_inventory.workload_counts is None
    assert cluster.workload_inventory.observed_pods is None
    assert cluster.workload_inventory.namespace_distribution is None
    assert cluster.workload_inventory.workload_investigations is None
    assert report.peer_groups[0].inventory_status_counts["supply"] == {"partial": 1, "unknown": 1}


def test_fleet_supply_classes_count_pool_objects_without_inventing_nodes_or_placement() -> None:
    first, second = assessment("primary"), assessment("peer")
    capacity = second.snapshot.clusters[0].capacity
    assert capacity is not None
    capacity.provisioning_mode = "Auto"
    pool = capacity.pools[0].model_copy(deep=True)
    pool.name = "synthetic-cas"
    pool.resource_id = f"{capacity.cluster_resource_id}/agentPools/{pool.name}"
    pool.autoscaling_enabled = True
    capacity.pools.append(pool)
    capacity.nap_api_status["karpenter.sh/v1/nodepools"] = "available"
    capacity.nap_api_status["karpenter.azure.com/v1beta1/aksnodeclasses"] = "available"
    capacity.nap_pools = [
        NapPoolEvidence(
            uid="synthetic-static-uid",
            name="static",
            nodeclass_uid="synthetic-class-uid",
            supply_mode="static",
            static_replicas=3,
        ),
        NapPoolEvidence(
            uid="synthetic-dynamic-uid",
            name="dynamic",
            nodeclass_uid="synthetic-class-uid",
            supply_mode="dynamic",
        ),
        NapPoolEvidence(
            uid="synthetic-unknown-uid",
            name="unknown",
            nodeclass_uid="synthetic-class-uid",
            supply_mode="unknown",
        ),
    ]
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    inventory = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).supply_inventory
    assert inventory.pool_counts == {
        "fixed": 1,
        "cas": 1,
        "nap_static": 1,
        "nap_dynamic": 1,
        "unknown": 1,
    }
    assert inventory.status == "partial"
    assert "unknown_supply_class" in inventory.reason_codes
    assert report.peer_groups[0].supply_pool_counts["nap_static"] == 1
    assert "not nodes" in inventory.unit


@pytest.mark.parametrize("problem", ["missing-class", "unknown-provisioning"])
def test_fleet_does_not_label_unverified_nodepools_as_aks_nap_supply(problem: str) -> None:
    first, second = assessment("primary"), assessment("peer")
    capacity = second.snapshot.clusters[0].capacity
    assert capacity is not None
    capacity.provisioning_mode = "Auto" if problem == "missing-class" else None
    capacity.nap_api_status["karpenter.sh/v1/nodepools"] = "available"
    capacity.nap_pools = [
        NapPoolEvidence(
            uid="synthetic-pool-uid",
            name="synthetic-pool",
            supply_mode="dynamic",
            nodeclass_uid=None if problem == "missing-class" else "synthetic-class-uid",
        )
    ]
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    inventory = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).supply_inventory
    assert inventory.pool_counts == {"fixed": 1, "unknown": 1}
    assert "unverified_nap_supply_class" in inventory.reason_codes


def test_fleet_arm_pool_market_preserves_explicit_unknowns_and_nap_independence() -> None:
    first, second = assessment("primary"), assessment("peer")
    capacity = second.snapshot.clusters[0].capacity
    assert capacity is not None
    capacity.pools[0].spot = True
    for suffix, spot in [("regular", False), ("unknown", None)]:
        pool = capacity.pools[0].model_copy(deep=True)
        pool.name = f"synthetic-{suffix}"
        pool.resource_id = f"{capacity.cluster_resource_id}/agentPools/{pool.name}"
        pool.spot = spot
        capacity.pools.append(pool)
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)
    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )
    observed = next(item for item in report.clusters if item.cluster_name == "aks-peer")
    market = observed.supply_inventory.arm_pool_market
    assert market.status == "partial"
    assert market.pool_counts == {"spot": 1, "regular": 1, "unknown": 1}
    assert market.reason_codes == ["unknown_arm_pool_market"]
    assert market.observed_at == capacity.azure_observed_at
    assert "not Nodes" in market.unit
    assert report.peer_groups[0].arm_pool_market_counts == {
        "spot": 1,
        "regular": 2,
        "unknown": 1,
    }
    assert report.peer_groups[0].inventory_status_counts["arm_pool_market"] == {
        "available": 1,
        "partial": 1,
    }


@pytest.mark.parametrize(
    "problem", ["none", "missing", "wrong-window", "whitespace-owner", "foreign-name", "duplicate"]
)
def test_fleet_review_owner_coverage_is_bound_and_does_not_export_prose(problem: str) -> None:
    first = assessment("primary")
    second = assessment("peer", fixture="history-assessment")
    workload = second.snapshot.clusters[0].workloads[0]
    policy = workload.safety_policy
    assert policy is not None
    policy.owner = "DO-NOT-EXPORT-REVIEW-OWNER"
    policy.slo_reference = "DO-NOT-EXPORT-SLO-REFERENCE"
    policy.reviewed_window_start = second.snapshot.metric_window.start
    policy.reviewed_window_end = second.snapshot.metric_window.end
    if problem == "missing":
        workload.safety_policy = None
    elif problem == "wrong-window":
        policy.reviewed_window_start -= timedelta(days=1)
    elif problem == "whitespace-owner":
        policy.owner = "   "
    elif problem == "foreign-name":
        workload.name = "synthetic-unrelated-workload"
    elif problem == "duplicate":
        second.snapshot.clusters[0].workloads.append(workload.model_copy(deep=True))
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)
    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )
    inventory = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).workload_inventory
    expected = "declared" if problem == "none" else "unknown"
    assert inventory.review_owner_status_counts == {expected: 1}
    assert inventory.workload_investigations is not None
    investigation = inventory.workload_investigations[0]
    assert investigation.workload_uid == workload.uid
    assert investigation.review_owner_status == expected
    assert bool(investigation.reason_codes) == (expected == "unknown")
    assert report.peer_groups[0].review_owner_status_counts == {expected: 1}
    serialized = report.model_dump_json()
    assert "DO-NOT-EXPORT-REVIEW-OWNER" not in serialized
    assert "DO-NOT-EXPORT-SLO-REFERENCE" not in serialized
    rendered = render_fleet_markdown(report)
    assert "Review declarations" in rendered
    assert "not business ownership or change approval" in rendered
    assert "DO-NOT-EXPORT-REVIEW-OWNER" not in rendered
    assert "DO-NOT-EXPORT-SLO-REFERENCE" not in rendered


@pytest.mark.parametrize(
    "problem",
    [
        "none",
        "stale-capacity",
        "foreign-capacity",
        "unresolved-node",
        "conflicting-bindings",
        "arm-only",
    ],
)
def test_fleet_current_workload_supply_uses_only_exact_existing_node_bindings(problem: str) -> None:
    first = assessment("primary")
    second = assessment("peer", fixture="daemonset-overhead-assessment")
    cluster = second.snapshot.clusters[0]
    capacity, inventory = cluster.capacity, cluster.scheduling
    assert capacity is not None and inventory is not None
    capacity.provisioning_mode = "Auto"
    capacity.nap_api_status["karpenter.sh/v1/nodepools"] = "available"
    capacity.nap_api_status["karpenter.azure.com/v1beta1/aksnodeclasses"] = "available"
    capacity.nap_pools = [
        NapPoolEvidence(
            uid="synthetic-nap-pool",
            name="synthetic-nap",
            nodeclass_uid="synthetic-class",
            supply_mode="dynamic",
        )
    ]
    assert inventory.pods[0].node_uid is not None
    capacity.nap_managed_nodes = [
        NapManagedNode(
            node_uid=inventory.pods[0].node_uid,
            nodeclaim_uid="synthetic-claim",
            nodepool_uid="synthetic-nap-pool",
        )
    ]
    if problem not in {"conflicting-bindings", "arm-only"}:
        for metadata in second.metadata_evidence:
            metadata.nodes.clear()
    if problem == "arm-only":
        capacity.nap_managed_nodes.clear()
    if problem == "stale-capacity":
        capacity.azure_observed_at = AS_OF - timedelta(hours=25)
    elif problem == "foreign-capacity":
        capacity.cluster_uid = "synthetic-foreign-fingerprint"
    elif problem == "unresolved-node":
        inventory.pods[0].node_uid = None
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)
    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )
    result = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).workload_inventory
    assert result.workload_counts == {"DaemonSet": 1}
    assert result.workload_investigations is not None
    supply = result.workload_investigations[0].observed_supply
    if problem in {"stale-capacity", "foreign-capacity"}:
        assert supply.status == "unknown" and supply.pod_counts is None
    else:
        expected = (
            {"nap_dynamic": 1, "unknown": 1}
            if problem == "none"
            else {"fixed": 1, "unknown": 1}
            if problem == "arm-only"
            else {"unknown": 2}
        )
        assert supply.pod_counts == expected, supply.model_dump()
        assert supply.status == "partial"
        if problem == "conflicting-bindings":
            assert "ambiguous_pod_supply" in supply.reason_codes
    assert "not placement" in supply.unit


def test_fleet_counts_uid_bound_daemonsets_instead_of_only_vertical_workloads() -> None:
    first = assessment("primary")
    second = assessment("peer", fixture="daemonset-overhead-assessment")

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    inventory = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).workload_inventory
    assert inventory.status == "available"
    assert inventory.workload_counts == {"DaemonSet": 1}
    assert inventory.observed_pods == 2
    assert inventory.unresolved_pods == 0
    assert inventory.namespace_distribution is not None
    assert len(inventory.namespace_distribution) == 1
    namespace = inventory.namespace_distribution[0]
    assert namespace.namespace == "synthetic" and namespace.namespace_uid is not None
    assert namespace.workload_counts == {"DaemonSet": 1}
    assert namespace.observed_pods == 2 and namespace.unresolved_pods == 0
    assert report.peer_groups[0].workload_counts == {"DaemonSet": 1}


@pytest.mark.parametrize("problem", ["unresolved-owner", "excluded", "ambiguous-owner"])
def test_fleet_workload_counts_preserve_unknown_ownership_and_namespace_scope(problem: str) -> None:
    first = assessment("primary")
    second = assessment("peer", fixture="daemonset-overhead-assessment")
    inventory = second.snapshot.clusters[0].scheduling
    assert inventory is not None
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    if problem == "unresolved-owner":
        inventory.pods[0].workload_uid = None
    elif problem == "excluded":
        config.excluded_namespaces.append("synthetic")
    else:
        inventory.pods[0].workload_name = "conflicting-current-owner"
    second.report = analyze(second.snapshot, config, as_of=AS_OF)
    entry = fleet_entry(peer_group="production", assessment=second)
    entry.analysis_config = AdvisorConfig.model_validate(
        config.model_dump() | {"pack_locks": entry.analysis_config.pack_locks}
    )

    report = aggregate_fleet(
        [fleet_entry(peer_group="production", assessment=first), entry], generated_at=AS_OF
    )

    observed = next(item for item in report.clusters if item.cluster_name == "aks-peer")
    if problem == "excluded":
        assert observed.workload_inventory.workload_counts == {}
        assert observed.workload_inventory.observed_pods == 0
        assert observed.workload_inventory.namespace_distribution == []
        assert "synthetic" in observed.excluded_namespaces
        assert not report.peer_groups[0].comparable
    else:
        assert observed.workload_inventory.status == "partial"
        assert observed.workload_inventory.unresolved_pods > 0
        assert observed.workload_inventory.namespace_distribution is not None
        assert observed.workload_inventory.namespace_distribution[0].unresolved_pods > 0
        assert "unresolved_workload_identity" in observed.workload_inventory.reason_codes


def test_fleet_partial_source_inventory_is_not_a_complete_empty_result() -> None:
    first = assessment("primary")
    fragments, profile = assessment_inputs("peer")
    receipt = fragments.kubernetes[0].collection
    receipt.status = CollectionStatus.PARTIAL
    receipt.pagination_complete = False
    second = assess_fragments(fragments, profile, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    observed = next(item for item in report.clusters if item.cluster_name == "aks-peer")
    assert observed.supply_inventory.pool_counts is None
    assert observed.supply_inventory.arm_pool_market.pool_counts is None
    assert observed.workload_inventory.workload_counts is None
    assert "incomplete_collection" in observed.supply_inventory.reason_codes
    assert "incomplete_collection" in observed.workload_inventory.reason_codes


def test_fleet_peer_groups_remain_comparable_independently_of_other_groups() -> None:
    values = [assessment(name) for name in ["primary", "peer", "different-window"]]
    values[2].snapshot.metric_window.start += timedelta(hours=1)
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    values[2].report = analyze(values[2].snapshot, config, as_of=AS_OF)
    entries = [
        fleet_entry(peer_group="production" if index < 2 else "other", assessment=value)
        for index, value in enumerate(values)
    ]

    report = aggregate_fleet(entries, generated_at=AS_OF)
    reversed_report = aggregate_fleet(list(reversed(entries)), generated_at=AS_OF)

    assert not report.comparable
    assert report == reversed_report
    production = next(item for item in report.peer_groups if item.peer_group == "production")
    assert production.comparable
    assert production.clusters == 2
    assert production.recommendations == sum(
        item.recommendations for item in report.clusters if item.peer_group == "production"
    )


@pytest.mark.parametrize("problem", ["missing", "foreign", "future"])
def test_fleet_inventory_unavailable_dimensions_remain_null(problem: str) -> None:
    entries = []
    for name in ["primary", "peer"]:
        value = assessment(name)
        cluster = value.snapshot.clusters[0]
        if problem == "missing":
            cluster.capacity = None
            cluster.scheduling = None
        elif problem == "foreign":
            cluster.capacity.cluster_uid = "foreign-fingerprint"
            cluster.scheduling.cluster_uid = "foreign-fingerprint"
        else:
            cluster.capacity.azure_observed_at = AS_OF + timedelta(seconds=1)
            cluster.scheduling.observed_at = AS_OF + timedelta(seconds=1)
        config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
        value.report = analyze(value.snapshot, config, as_of=AS_OF)
        entries.append(fleet_entry(peer_group="production", assessment=value))

    report = aggregate_fleet(entries, generated_at=AS_OF)

    assert all(item.supply_inventory.pool_counts is None for item in report.clusters)
    assert all(item.workload_inventory.workload_counts is None for item in report.clusters)
    assert report.peer_groups[0].supply_pool_counts is None
    assert report.peer_groups[0].workload_counts is None
    assert report.peer_groups[0].arm_pool_market_counts is None
    assert report.peer_groups[0].review_owner_status_counts is None
    assert report.peer_groups[0].inventory_status_counts == {
        "supply": {"unknown": 2},
        "workloads": {"unknown": 2},
        "arm_pool_market": {"unknown": 2},
    }


def test_fleet_complete_empty_supply_is_distinct_from_unknown_supply() -> None:
    entries = []
    for name in ["primary", "peer"]:
        value = assessment(name)
        capacity = value.snapshot.clusters[0].capacity
        capacity.pools.clear()
        capacity.nap_api_status["karpenter.sh/v1/nodepools"] = "absent"
        config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
        value.report = analyze(value.snapshot, config, as_of=AS_OF)
        entries.append(fleet_entry(peer_group="production", assessment=value))

    report = aggregate_fleet(entries, generated_at=AS_OF)

    assert all(item.supply_inventory.status == "available" for item in report.clusters)
    assert report.peer_groups[0].supply_pool_counts == {}
    assert report.peer_groups[0].inventory_status_counts["supply"] == {"available": 2}


def test_fleet_inventory_freshness_equality_is_evaluated_at_original_assessment_time() -> None:
    entries = []
    for name in ["primary", "peer"]:
        value = assessment(name)
        observed = min(
            item.source_observed_at
            for item in value.snapshot.collection_manifest.source_results
            if item.source_observed_at is not None
        )
        config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
        value.report = analyze(value.snapshot, config, as_of=observed + timedelta(hours=24))
        entries.append(fleet_entry(peer_group="production", assessment=value))

    report = aggregate_fleet(entries, generated_at=AS_OF + timedelta(days=30))

    assert all(item.supply_inventory.pool_counts == {"fixed": 1} for item in report.clusters)
    assert all(item.workload_inventory.status == "available" for item in report.clusters)
    assert all(item.generated_at < report.generated_at for item in report.clusters)


def test_fleet_peer_group_labels_remain_inert_in_markdown() -> None:
    from aks_fleet_efficiency.reporting.markdown import render_fleet_markdown

    label = "<script>synthetic</script>\n# invented-heading"
    entries = [
        fleet_entry(peer_group=label, assessment=assessment(name)) for name in ["primary", "peer"]
    ]
    before = [item.model_dump_json() for item in entries]

    report = aggregate_fleet(entries, generated_at=AS_OF)
    rendered = render_fleet_markdown(report)

    assert "<script>" not in rendered
    assert "\n# invented-heading" not in rendered
    assert [item.model_dump_json() for item in entries] == before


def test_fleet_inventory_counts_do_not_require_metrics_or_selecting_inventory_rules() -> None:
    entries = []
    for name in ["primary", "peer"]:
        fragments, profile = assessment_inputs(name, fixture="history-assessment")
        fragments.metrics.clear()
        profile.analysis = AdvisorConfig(packs=["AKS-RQ-002"])
        value = assess_fragments(fragments, profile, as_of=AS_OF)
        locked = AdvisorConfig.model_validate(
            profile.analysis.model_dump()
            | {"pack_locks": {item.id: item.digest for item in value.report.pack_provenance}}
        )
        entries.append(
            FleetAssessmentInput(peer_group="production", assessment=value, analysis_config=locked)
        )

    report = aggregate_fleet(entries, generated_at=AS_OF)

    assert report.summary.recommendations == 0
    assert report.summary.blocked_recommendations > 0
    assert all(item.supply_inventory.pool_counts == {"fixed": 1} for item in report.clusters)
    assert all(item.workload_inventory.status == "available" for item in report.clusters)


def test_fleet_current_resource_envelope_does_not_sum_percentiles_or_invent_usage() -> None:
    entries = []
    for name in ["primary", "peer"]:
        fragments, config = assessment_inputs(name, fixture="daemonset-overhead-assessment")
        nodes = [item for item in fragments.kubernetes[0].resources if item.kind == "Node"]
        nodes[0].status["capacity"] = {"cpu": "3", "memory": "1536Mi"}
        nodes[1].status["capacity"] = {"cpu": "5", "memory": "3072Mi"}
        value = assess_fragments(fragments, config, as_of=AS_OF)
        entries.append(fleet_entry(peer_group="production", assessment=value))

    report = aggregate_fleet(entries, generated_at=AS_OF)

    for cluster in report.clusters:
        envelope = cluster.resource_envelope
        assert envelope.node_capacity.cpu_mcpu == 8000
        assert envelope.node_capacity.memory_mib == 4608
        assert envelope.allocatable.cpu_mcpu == 6000
        assert envelope.allocatable.memory_mib == 3072
        assert envelope.requested.cpu_mcpu == 1500
        assert envelope.requested.memory_mib == 704
        assert envelope.requested.status == "available"
        assert envelope.observed_usage.cpu_mcpu is None
        assert "aligned_cluster_usage_unavailable" in envelope.observed_usage.reason_codes
        gaps = envelope.current_gaps
        assert gaps is not None
        assert gaps.capacity_minus_allocatable.cpu.value == 2000
        assert gaps.capacity_minus_allocatable.memory.value == 1536
        assert gaps.allocatable_minus_requests.cpu.value == 4500
        assert gaps.allocatable_minus_requests.memory.value == 2368
        assert gaps.allocatable_minus_requests.cpu.nodes_expected == 2
        assert gaps.allocatable_minus_requests.cpu.nodes_covered == 2
        assert gaps.requests_minus_usage == "aligned_cluster_usage_unavailable"
    assert report.peer_groups[0].resource_envelope.requested.cpu_mcpu == 3000
    assert report.peer_groups[0].resource_envelope.current_gaps is None


def test_fleet_resource_dimensions_keep_missing_cpu_independent_of_valid_memory() -> None:
    first = assessment("primary")
    fragments, config = assessment_inputs("peer", fixture="daemonset-overhead-assessment")
    pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
    pod.spec["containers"][0]["resources"]["requests"].pop("cpu")
    second = assess_fragments(fragments, config, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    envelope = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).resource_envelope
    assert envelope.requested.cpu_mcpu is None
    assert envelope.requested.memory_mib == 704
    assert envelope.requested.status == "partial"
    assert envelope.allocatable.cpu_mcpu == 6000
    assert envelope.current_gaps is not None
    gap = envelope.current_gaps.allocatable_minus_requests
    assert gap.cpu.value is None
    assert gap.cpu.pods_covered is not None and gap.cpu.pods_expected is not None
    assert gap.cpu.pods_covered < gap.cpu.pods_expected
    assert gap.memory.value == 2368


@pytest.mark.parametrize(
    "problem",
    [
        "unknown-phase",
        "terminal",
        "missing-init",
        "missing-node-list",
        "overflow",
        "excluded",
        "different-window",
        "stale",
    ],
)
def test_fleet_resource_envelopes_fail_closed_without_erasing_independent_dimensions(
    problem: str,
) -> None:
    entries = []
    for name in ["primary", "peer"]:
        fragments, config = assessment_inputs(name, fixture="daemonset-overhead-assessment")
        if name == "peer":
            pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
            if problem == "unknown-phase":
                pod.status["phase"] = "Unknown"
            elif problem == "terminal":
                for item in fragments.kubernetes[0].resources:
                    if item.kind == "Pod":
                        item.status["phase"] = "Succeeded"
            elif problem == "missing-init":
                pod.spec.pop("initContainers")
            elif problem == "missing-node-list":
                fragments.kubernetes[0].resource_versions.pop("v1/nodes")
            elif problem == "overflow":
                for item in fragments.kubernetes[0].resources:
                    if item.kind == "Node":
                        item.status["allocatable"]["cpu"] = "1e305"
            elif problem == "excluded":
                config.analysis.excluded_namespaces.append("synthetic")
        value = assess_fragments(fragments, config, as_of=AS_OF)
        if name == "peer" and problem in {"different-window", "stale"}:
            if problem == "different-window":
                value.snapshot.metric_window.start += timedelta(hours=1)
            else:
                value.snapshot.clusters[0].scheduling.observed_at = AS_OF - timedelta(hours=25)
            value.report = analyze(value.snapshot, config.analysis, as_of=AS_OF)
        locked = AdvisorConfig.model_validate(
            config.analysis.model_dump()
            | {"pack_locks": {item.id: item.digest for item in value.report.pack_provenance}}
        )
        entries.append(
            FleetAssessmentInput(peer_group="production", assessment=value, analysis_config=locked)
        )

    report = aggregate_fleet(entries, generated_at=AS_OF)
    envelope = next(
        item for item in report.clusters if item.cluster_name == "aks-peer"
    ).resource_envelope
    if problem in {"unknown-phase", "missing-init", "missing-node-list", "stale"}:
        assert envelope.requested.cpu_mcpu is None
        assert envelope.requested.memory_mib is None
    elif problem in {"terminal", "excluded"}:
        assert envelope.requested.cpu_mcpu == 0
        assert envelope.requested.memory_mib == 0
        assert envelope.current_gaps is not None
        gap = envelope.current_gaps.allocatable_minus_requests.cpu
        if problem == "excluded":
            assert gap.value is None
            assert gap.reason == "namespace_scope_mismatch"
        else:
            assert gap.value == envelope.allocatable.cpu_mcpu
            assert gap.pods_expected == gap.pods_covered == 0
    elif problem == "overflow":
        assert envelope.allocatable.cpu_mcpu is None
        assert envelope.allocatable.memory_mib == 3072
    if problem in {"different-window", "excluded"}:
        assert report.peer_groups[0].resource_envelope.requested.cpu_mcpu is None
        assert (
            "peer_group_not_comparable"
            in report.peer_groups[0].resource_envelope.requested.reason_codes
        )
    assert envelope.observed_usage.cpu_mcpu is None


def test_fleet_gaps_preserve_signed_requests_and_zero_without_netting_invalid_nodes() -> None:
    fragments, config = assessment_inputs("peer", fixture="daemonset-overhead-assessment")
    nodes = [item for item in fragments.kubernetes[0].resources if item.kind == "Node"]
    for node in nodes:
        node.status["capacity"] = {"cpu": "1", "memory": "1536Mi"}
        node.status["allocatable"] = {"cpu": "500m", "memory": "1536Mi"}
    nodes[0].status["capacity"]["memory"] = "1024Mi"
    nodes[1].status["capacity"]["memory"] = "2048Mi"
    result = assess_fragments(fragments, config, as_of=AS_OF)
    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=assessment("primary")),
            fleet_entry(peer_group="production", assessment=result),
        ],
        generated_at=AS_OF,
    )
    envelope = next(
        cluster.resource_envelope
        for cluster in report.clusters
        if cluster.cluster_name == "aks-peer"
    )
    gaps = envelope.current_gaps
    assert gaps is not None
    assert gaps.allocatable_minus_requests.cpu.value == -500
    assert gaps.capacity_minus_allocatable.memory.value is None
    assert gaps.capacity_minus_allocatable.memory.reason == "invalid_node_accounting"

    nodes[0].status["capacity"]["memory"] = "1536Mi"
    nodes[1].status["capacity"]["memory"] = "1536Mi"
    result = assess_fragments(fragments, config, as_of=AS_OF)
    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=assessment("primary")),
            fleet_entry(peer_group="production", assessment=result),
        ],
        generated_at=AS_OF,
    )
    envelope = next(
        cluster.resource_envelope
        for cluster in report.clusters
        if cluster.cluster_name == "aks-peer"
    )
    assert envelope.current_gaps is not None
    assert envelope.current_gaps.capacity_minus_allocatable.memory.value == 0


def test_fleet_aggregation_marks_misaligned_windows_not_comparable() -> None:
    first = assessment("primary")
    second = assessment("peer").model_copy(deep=True)
    second.snapshot.metric_window.start += timedelta(hours=1)
    second.report.observation_window.start += timedelta(hours=1)
    second.report.snapshot_digest = sha256(
        json.dumps(
            second.snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    assert not report.comparable
    assert report.comparability_reasons == ["observation_windows_differ"]


def test_fleet_aggregation_rejects_duplicate_cluster_identity() -> None:
    value = assessment("primary")
    with pytest.raises(ValueError, match="distinct cluster identities"):
        aggregate_fleet(
            [
                fleet_entry(peer_group="production", assessment=value),
                fleet_entry(peer_group="secondary", assessment=value),
            ],
            generated_at=AS_OF,
        )


def test_fleet_aggregation_rejects_cross_tenant_inputs() -> None:
    with pytest.raises(ValueError, match="one tenant"):
        aggregate_fleet(
            [
                fleet_entry(peer_group="production", assessment=assessment("primary")),
                fleet_entry(
                    peer_group="production",
                    assessment=assessment(
                        "foreign", tenant_id="11111111-1111-1111-1111-111111111111"
                    ),
                ),
            ],
            generated_at=AS_OF,
        )


def test_fleet_aggregation_rejects_tampered_snapshot() -> None:
    first = assessment("primary")
    second = assessment("peer").model_copy(deep=True)
    second.snapshot.clusters[0].name = "tampered-without-updated-digest"

    with pytest.raises(ValueError, match="snapshot integrity"):
        aggregate_fleet(
            [
                fleet_entry(peer_group="production", assessment=first),
                fleet_entry(peer_group="production", assessment=second),
            ],
            generated_at=AS_OF,
        )


@pytest.mark.parametrize("field", ["rule", "severity", "evidence", "capabilities"])
def test_fleet_aggregation_rejects_edited_reports(field: str) -> None:
    first = assessment("primary")
    second = assessment("peer").model_copy(deep=True)
    if field == "rule":
        second.report.recommendations[0].rule_id = "AKS-FOREIGN-999"
    elif field == "severity":
        second.report.recommendations[0].severity = Severity.CRITICAL
    elif field == "evidence":
        second.report.recommendations[0].evidence.clear()
    else:
        second.report.source_capabilities.clear()

    with pytest.raises(ValueError, match="replay"):
        aggregate_fleet(
            [
                fleet_entry(peer_group="production", assessment=first),
                fleet_entry(peer_group="production", assessment=second),
            ],
            generated_at=AS_OF,
        )


def test_fleet_comparability_preserves_different_coverage_for_the_same_window() -> None:
    first = assessment("primary")
    second = assessment("peer").model_copy(deep=True)
    second.snapshot.metric_window.sample_count -= 1
    second.snapshot.metric_window.coverage_ratio = 0.9
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    second.report = analyze(second.snapshot, config, as_of=AS_OF)

    report = aggregate_fleet(
        [
            fleet_entry(peer_group="production", assessment=first),
            fleet_entry(peer_group="production", assessment=second),
        ],
        generated_at=AS_OF,
    )

    assert report.comparable
    assert {item.observation_window.coverage_ratio for item in report.clusters} == {0.9, 1.0}


@pytest.mark.parametrize("problem", ["missing-locks", "changed-config", "changed-digest"])
def test_fleet_requires_the_original_locked_configuration(problem: str) -> None:
    entries = [
        fleet_entry(peer_group="production", assessment=assessment(name))
        for name in ["primary", "peer"]
    ]
    if problem == "missing-locks":
        entries[1].analysis_config.pack_locks.clear()
    elif problem == "changed-config":
        entries[1].analysis_config.excluded_namespaces.append("other-synthetic-namespace")
    else:
        entries[1].assessment.report.configuration_digest = "unbound"

    with pytest.raises(ValueError, match="locked configuration provenance"):
        aggregate_fleet(entries, generated_at=AS_OF)


def test_fleet_assessment_requires_bounded_peer_group() -> None:
    with pytest.raises(ValueError):
        fleet_entry(peer_group=" ", assessment=assessment("primary"))


def test_fleet_cli_summarizes_explicit_assessments_as_json(tmp_path: Path) -> None:
    paths = [fleet_artifacts(tmp_path / name, name) for name in ["primary", "peer"]]

    result = CliRunner().invoke(
        app,
        [
            "fleet",
            "summarize",
            "--assessment",
            str(paths[0]),
            "--assessment",
            str(paths[1]),
            "--peer-group",
            "production",
            "--peer-group",
            "production",
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = FleetInsightReport.model_validate_json(result.stdout)
    assert report.summary.clusters == 2
    assert report.comparable


def test_fictional_fleet_lab_compares_original_bundles(tmp_path: Path) -> None:
    runner = CliRunner()
    primary = tmp_path / "primary"
    peer = tmp_path / "peer"
    different = tmp_path / "different"
    for destination, fixture, config, pack in [
        (primary, "workload-assessment", "pool-assessment", "AKS-RQ-001"),
        (peer, "fleet-peer-assessment", "fleet-peer", "AKS-RQ-001"),
        (different, "fleet-peer-assessment", "fleet-peer", "AKS-SCHED-001"),
    ]:
        result = runner.invoke(
            app,
            [
                "assess",
                "--fragments",
                str(ROOT / "examples/fixtures" / f"{fixture}.json"),
                "--config",
                str(ROOT / "examples" / f"{config}-config.yaml"),
                "--mode",
                "baseline",
                "--pack",
                pack,
                "--as-of",
                AS_OF.isoformat(),
                "--artifacts",
                str(destination),
            ],
        )
        assert result.exit_code == 3, result.output

    for destination, comparable in [(peer, True), (different, False)]:
        result = runner.invoke(
            app,
            [
                "fleet",
                "summarize",
                "--assessment",
                str(primary / "assessment.json"),
                "--peer-group",
                "nonproduction",
                "--assessment",
                str(destination / "assessment.json"),
                "--peer-group",
                "nonproduction",
                "--as-of",
                AS_OF.isoformat(),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        report = FleetInsightReport.model_validate_json(result.stdout)
        assert report.summary.clusters == 2
        assert report.comparable is comparable
        assert report.rule_counts["AKS-RQ-001"] == (2 if comparable else 1)


def test_fleet_cli_renders_plain_language_markdown_and_rejects_unpaired_groups(
    tmp_path: Path,
) -> None:
    paths = [fleet_artifacts(tmp_path / name, name) for name in ["primary", "peer"]]
    runner = CliRunner()

    markdown = runner.invoke(
        app,
        [
            "fleet",
            "summarize",
            "--assessment",
            str(paths[0]),
            "--assessment",
            str(paths[1]),
            "--peer-group",
            "production",
            "--peer-group",
            "nonproduction",
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "markdown",
        ],
    )
    assert markdown.exit_code == 0, markdown.output
    assert "# AKS Fleet Optimization Insights" in markdown.stdout
    assert "Comparable assessments: yes" in markdown.stdout
    assert "## Peer groups" in markdown.stdout
    assert "Observed pool objects:" in markdown.stdout
    assert "Supply inventory status: `partial`" in markdown.stdout
    assert "Original assessment time:" in markdown.stdout
    assert "Observed workload owners:" in markdown.stdout
    assert "No fleet efficiency score or savings estimate is calculated." in markdown.stdout

    invalid = runner.invoke(
        app,
        [
            "fleet",
            "summarize",
            "--assessment",
            str(paths[0]),
            "--assessment",
            str(paths[1]),
            "--peer-group",
            "SENSITIVE-UNPAIRED",
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert invalid.exit_code == 2
    assert "SENSITIVE-UNPAIRED" not in invalid.output


@pytest.mark.parametrize(
    "missing", ["manifest.json", "fragments.json", "snapshot.json", "analysis-config.json"]
)
def test_fleet_cli_requires_the_original_artifact_bundle(tmp_path: Path, missing: str) -> None:
    paths = [fleet_artifacts(tmp_path / name, name) for name in ["primary", "peer"]]
    (paths[1].parent / missing).unlink()

    result = CliRunner().invoke(
        app,
        [
            "fleet",
            "summarize",
            "--assessment",
            str(paths[0]),
            "--peer-group",
            "production",
            "--assessment",
            str(paths[1]),
            "--peer-group",
            "production",
            "--as-of",
            AS_OF.isoformat(),
        ],
    )

    assert result.exit_code == 2
    assert "Fleet aggregation failed" in result.output


def test_fleet_cli_rejects_rehashed_report_tampering(tmp_path: Path) -> None:
    paths = [fleet_artifacts(tmp_path / name, name) for name in ["primary", "peer"]]
    payload = json.loads(paths[1].read_text(encoding="utf-8"))
    payload["report"]["recommendations"][0]["summary"] = "SENSITIVE-EDITED-CLAIM"
    encoded = json.dumps(payload)
    paths[1].write_text(encoded, encoding="utf-8")
    manifest_path = paths[1].parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["assessment.json"] = sha256(encoded.encode()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "fleet",
            "summarize",
            "--assessment",
            str(paths[0]),
            "--peer-group",
            "production",
            "--assessment",
            str(paths[1]),
            "--peer-group",
            "production",
            "--as-of",
            AS_OF.isoformat(),
        ],
    )

    assert result.exit_code == 2
    assert "SENSITIVE-EDITED-CLAIM" not in result.output
