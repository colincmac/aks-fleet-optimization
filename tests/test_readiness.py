from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.fixture import FixtureCollector
from aks_fleet_efficiency.config import OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.models import FleetSnapshot, ReadinessReport
from aks_fleet_efficiency.readiness import evaluate_readiness
from aks_fleet_efficiency.reporting.markdown import render_readiness_markdown

SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def onboarding_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scope": {
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "subscription_ids": [SUBSCRIPTION],
        },
        "metric_sources": [
            {
                "name": "synthetic-prometheus",
                "type": "prometheus",
                "endpoint": "https://metrics.example.invalid",
                "authentication": "anonymous",
                "label_mapping": {
                    "cluster_resource_id": "azure_resource_id",
                    "namespace": "namespace",
                    "workload": "workload",
                    "workload_kind": "workload_kind",
                    "container": "container",
                },
                "declared_retention_days": 30,
                "declared_step_seconds": 300,
            }
        ],
        "clusters": [
            {
                "resource_id": CLUSTER,
                "metric_source": "synthetic-prometheus",
                "environment": "nonproduction",
            }
        ],
        "ownership": [
            {"cluster_resource_id": CLUSTER, "namespace": "orders", "owner": "synthetic-owner"}
        ],
        "report_directory": "reports",
    }


def test_onboarding_profile_round_trip_preserves_exact_resource_ids() -> None:
    profile = OnboardingConfig.model_validate(onboarding_payload())
    assert profile.clusters[0].resource_id == CLUSTER
    assert str(profile.scope.subscription_ids[0]) == SUBSCRIPTION
    assert OnboardingConfig.model_validate_json(profile.model_dump_json()) == profile
    assert profile.analysis.thresholds.minimum_observation_days == 30


def test_loading_profile_does_not_create_report_directory(tmp_path: Path) -> None:
    payload = onboarding_payload()
    payload["report_directory"] = str(tmp_path / "not-created")
    configuration = tmp_path / "onboarding.yaml"
    configuration.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_onboarding_config(configuration).report_directory == tmp_path / "not-created"
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "99.0"),
        (("scope", "tenant_id"), "not-a-tenant"),
        (("scope", "subscription_ids"), []),
        (("scope", "subscription_ids"), [SUBSCRIPTION, SUBSCRIPTION]),
        (("clusters", 0, "resource_id"), "/not/an/aks/resource"),
        (("clusters", 0, "metric_source"), "missing-source"),
        (("metric_sources", 0, "endpoint"), "http://metrics.example.invalid"),
        (("metric_sources", 0, "endpoint"), "https://user:synthetic-secret@example.invalid"),
        (("metric_sources", 0, "endpoint"), "https://example.invalid?token=synthetic-secret"),
        (("metric_sources", 0, "endpoint"), "https://example.invalid/#synthetic-secret"),
        (("metric_sources", 0, "authentication"), "write-capable-credential"),
        (("metric_sources", 0, "label_mapping", "namespace"), "invalid-label-name"),
        (("metric_sources", 0, "declared_retention_days"), 0),
        (("metric_sources", 0, "declared_step_seconds"), 0),
    ],
)
def test_invalid_onboarding_profiles_fail_closed(path: tuple[str | int, ...], value: Any) -> None:
    payload = onboarding_payload()
    target: Any = payload
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        OnboardingConfig.model_validate(payload)


def test_clusters_must_belong_to_the_subscription_allowlist() -> None:
    payload = onboarding_payload()
    payload["scope"]["subscription_ids"] = ["00000000-0000-0000-0000-000000000001"]
    with pytest.raises(ValidationError):
        OnboardingConfig.model_validate(payload)


def test_duplicate_cluster_scope_cannot_be_hidden_by_case() -> None:
    payload = onboarding_payload()
    payload["clusters"].append(payload["clusters"][0] | {"resource_id": CLUSTER.upper()})
    with pytest.raises(ValidationError):
        OnboardingConfig.model_validate(payload)


def test_profile_rejects_embedded_credentials_without_echoing_them() -> None:
    payload = onboarding_payload()
    payload["metric_sources"][0]["credentials"] = "synthetic-secret"
    with pytest.raises(ValidationError) as error:
        OnboardingConfig.model_validate(payload)
    assert "synthetic-secret" not in str(error.value)


def observed_snapshot() -> tuple[OnboardingConfig, FleetSnapshot]:
    payload = (
        FixtureCollector(Path("examples/fixtures/fleet-snapshot.json"))
        .collect()
        .model_dump(mode="json")
    )
    cluster = payload["clusters"][0]
    profile = onboarding_payload()
    profile["clusters"][0]["resource_id"] = cluster["resource_id"]
    profile["ownership"][0]["cluster_resource_id"] = cluster["resource_id"]
    window = {
        "start": "2026-09-29T00:00:00Z",
        "end": "2026-10-29T00:00:00Z",
        "sample_count": 8640,
        "coverage_ratio": 0.97,
    }
    payload.update(generated_at=AS_OF.isoformat(), metric_window=window)
    results = []
    for collector in ["azure-inventory", "kubernetes-metadata", "prometheus"]:
        scope = SUBSCRIPTION if collector == "azure-inventory" else cluster["resource_id"]
        results.append(
            {
                "collector": collector,
                "status": "complete",
                "requested_scope": [scope],
                "completed_scope": [scope],
                "started_at": "2026-10-29T11:00:00Z",
                "completed_at": "2026-10-29T11:01:00Z",
                "source_observed_at": "2026-10-29T11:00:00Z",
                "pagination_complete": True,
            }
        )
    payload["collection_manifest"] = {
        "tenant_id": SUBSCRIPTION,
        "status": "complete",
        "results": results,
        "source_results": results,
    }
    for workload in cluster["workloads"]:
        for container in workload["containers"]:
            container["resources"]["metric_quality"] = {
                metric: {
                    "source": "synthetic-prometheus",
                    "query_version": "synthetic-v1",
                    "step_seconds": 300,
                    "observed_at": AS_OF.isoformat(),
                    "window": window,
                    "unit": unit,
                }
                for metric, unit in {
                    "usage_cpu_p95_mcores": "mCPU",
                    "usage_cpu_p99_mcores": "mCPU",
                    "cpu_throttled_ratio": "ratio",
                    "memory_oom_events": "events",
                }.items()
            }
    return OnboardingConfig.model_validate(profile), FleetSnapshot.model_validate(payload)


def test_offline_readiness_never_claims_live_connectivity_or_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("readiness must not contact a network endpoint")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    profile = OnboardingConfig.model_validate(onboarding_payload())
    report = evaluate_readiness(profile, as_of=AS_OF)
    assert report.mode == "offline"
    assert report.status == "unknown"
    assert any(
        check.code == "source.connectivity" and check.status == "unknown" for check in report.checks
    )
    assert any(
        check.code == "scope.permissions" and check.status == "unknown" for check in report.checks
    )
    assert "https://metrics.example.invalid" not in report.model_dump_json()


def test_observed_history_is_distinct_from_unverified_endpoint_readiness() -> None:
    profile, snapshot = observed_snapshot()
    report = evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF)
    assert report.status == "unknown"
    assert any(
        check.code == "snapshot.history" and check.status == "pass" for check in report.checks
    )
    assert any(
        check.code == "snapshot.collection" and check.status == "pass" for check in report.checks
    )
    assert report == evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF)
    assert report.configuration_digest
    assert report.snapshot_digest


@pytest.mark.parametrize("with_snapshot", [False, True])
def test_source_compatibility_requires_independent_pilot_evidence(with_snapshot: bool) -> None:
    profile, snapshot = observed_snapshot()
    report = evaluate_readiness(profile, snapshot=snapshot if with_snapshot else None, as_of=AS_OF)
    source_checks = {
        check.code: check
        for check in report.checks
        if check.scope == profile.metric_sources[0].name
    }
    for code in (
        "source.historical_identity",
        "source.recording_semantics",
        "source.provenance",
        "source.network",
    ):
        assert code in source_checks
        assert source_checks[code].status == "unknown"
    assert source_checks["source.labels"].status == "pass"
    assert source_checks["source.retention"].status == "pass"
    assert report.status == "unknown"
    assert "https://metrics.example.invalid" not in report.model_dump_json()


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("declared_retention_days", 14, "source.retention"),
        ("declared_step_seconds", 3600, "source.resolution"),
        ("label_mapping", {}, "source.labels"),
    ],
)
def test_declared_source_gaps_block_readiness(field: str, value: Any, code: str) -> None:
    payload = onboarding_payload()
    payload["metric_sources"][0][field] = value
    report = evaluate_readiness(OnboardingConfig.model_validate(payload), as_of=AS_OF)
    assert report.status == "blocked"
    assert any(check.code == code and check.status == "blocked" for check in report.checks)


def test_unknown_retention_is_not_inferred_from_the_requested_window() -> None:
    payload = onboarding_payload()
    del payload["metric_sources"][0]["declared_retention_days"]
    report = evaluate_readiness(OnboardingConfig.model_validate(payload), as_of=AS_OF)
    assert any(
        check.code == "source.retention" and check.status == "unknown" for check in report.checks
    )


def test_missing_workload_kind_mapping_blocks_source_label_readiness() -> None:
    payload = onboarding_payload()
    del payload["metric_sources"][0]["label_mapping"]["workload_kind"]
    report = evaluate_readiness(OnboardingConfig.model_validate(payload), as_of=AS_OF)
    assert report.status == "blocked"
    assert any(
        check.code == "source.labels" and check.status == "blocked" for check in report.checks
    )


def test_snapshot_from_a_different_tenant_is_blocked() -> None:
    profile, snapshot = observed_snapshot()
    assert snapshot.collection_manifest is not None
    snapshot.collection_manifest.tenant_id = "00000000-0000-0000-0000-000000000001"
    report = evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF)
    assert report.status == "blocked"
    assert any(
        check.code == "snapshot.tenant" and check.status == "blocked" for check in report.checks
    )


def test_missing_expected_cluster_is_not_treated_as_healthy() -> None:
    profile, snapshot = observed_snapshot()
    snapshot.clusters = []
    report = evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF)
    assert report.status == "blocked"
    assert any(
        check.code == "snapshot.scope" and check.status == "blocked" for check in report.checks
    )


def test_snapshot_outside_the_allowlist_is_blocked() -> None:
    profile, snapshot = observed_snapshot()
    snapshot.clusters[0].subscription_id = "00000000-0000-0000-0000-000000000001"
    report = evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF)
    assert report.status == "blocked"
    assert any(
        check.code == "snapshot.scope" and check.status == "blocked" for check in report.checks
    )


def test_readiness_markdown_escapes_collected_strings() -> None:
    report = evaluate_readiness(OnboardingConfig.model_validate(onboarding_payload()), as_of=AS_OF)
    report.checks[0].message = "<script>alert(1)</script>\n# injected [link](javascript:alert(1))"
    rendered = render_readiness_markdown(report)
    assert "<script>" not in rendered
    assert "\n# injected" not in rendered
    assert "[link](javascript:" not in rendered
    assert "offline" in rendered


def test_readiness_cli_returns_unknown_status_without_live_probes(tmp_path: Path) -> None:
    configuration = tmp_path / "onboarding.yaml"
    configuration.write_text(yaml.safe_dump(onboarding_payload()), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "readiness",
            "--config",
            str(configuration),
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 3, result.output
    report = json.loads(result.stdout)
    assert report["status"] == "unknown"
    assert datetime.fromisoformat(report["generated_at"]) == AS_OF


def test_invalid_readiness_config_does_not_echo_credential_values(tmp_path: Path) -> None:
    payload = onboarding_payload()
    payload["metric_sources"][0]["credentials"] = "synthetic-secret"
    configuration = tmp_path / "invalid.yaml"
    configuration.write_text(yaml.safe_dump(payload), encoding="utf-8")
    result = CliRunner().invoke(app, ["readiness", "--config", str(configuration)])
    assert result.exit_code == 2
    assert "synthetic-secret" not in result.output


def test_duplicate_source_names_are_rejected() -> None:
    payload = onboarding_payload()
    payload["metric_sources"].append(payload["metric_sources"][0].copy())
    with pytest.raises(ValidationError):
        OnboardingConfig.model_validate(payload)


def test_ambiguous_owner_mapping_is_rejected() -> None:
    payload = onboarding_payload()
    payload["ownership"].append(payload["ownership"][0] | {"owner": "different-owner"})
    with pytest.raises(ValidationError):
        OnboardingConfig.model_validate(payload)


def test_managed_prometheus_requires_azure_identity_profile() -> None:
    payload = onboarding_payload()
    payload["metric_sources"][0]["type"] = "azure-managed-prometheus"
    with pytest.raises(ValidationError):
        OnboardingConfig.model_validate(payload)
    payload["metric_sources"][0]["authentication"] = "default-azure-credential"
    assert (
        OnboardingConfig.model_validate(payload).metric_sources[0].authentication
        == "default-azure-credential"
    )


def test_bearer_reference_does_not_read_or_echo_the_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = onboarding_payload()
    payload["metric_sources"][0].update(
        authentication="bearer-environment", token_environment_variable="SYNTHETIC_TOKEN"
    )
    monkeypatch.setenv("SYNTHETIC_TOKEN", "synthetic-bearer-secret")
    report = evaluate_readiness(OnboardingConfig.model_validate(payload), as_of=AS_OF)
    assert report.status == "unknown"
    assert "synthetic-bearer-secret" not in report.model_dump_json()


def test_inflated_entity_coverage_cannot_pass_readiness() -> None:
    profile, snapshot = observed_snapshot()
    quality = (
        snapshot.clusters[0]
        .workloads[0]
        .containers[0]
        .resources.metric_quality["usage_cpu_p95_mcores"]
    )
    quality.window.sample_count = 1
    report = evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF)
    assert any(
        check.code == "snapshot.entity-quality" and check.status == "blocked"
        for check in report.checks
    )


def test_stale_snapshot_is_blocked_without_modifying_input() -> None:
    profile, snapshot = observed_snapshot()
    before = snapshot.model_dump_json()
    report = evaluate_readiness(profile, snapshot=snapshot, as_of=AS_OF + timedelta(days=2))
    assert report.status == "blocked"
    assert any(
        check.code == "snapshot.freshness" and check.status == "blocked" for check in report.checks
    )
    assert snapshot.model_dump_json() == before


def test_naive_readiness_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_readiness(
            OnboardingConfig.model_validate(onboarding_payload()), as_of=datetime(2026, 10, 29)
        )


def test_readiness_contract_cannot_claim_ready_with_unknown_checks() -> None:
    report = evaluate_readiness(OnboardingConfig.model_validate(onboarding_payload()), as_of=AS_OF)
    payload = report.model_dump(mode="json") | {"status": "ready"}
    with pytest.raises(ValidationError):
        ReadinessReport.model_validate(payload)
    assert ReadinessReport.model_validate_json(report.model_dump_json()) == report


def test_blocked_readiness_cli_writes_report_and_returns_four(tmp_path: Path) -> None:
    payload = onboarding_payload()
    payload["metric_sources"][0]["declared_retention_days"] = 14
    configuration = tmp_path / "onboarding.yaml"
    configuration.write_text(yaml.safe_dump(payload), encoding="utf-8")
    destination = tmp_path / "readiness.json"
    result = CliRunner().invoke(
        app,
        [
            "readiness",
            "--config",
            str(configuration),
            "--format",
            "json",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 4, result.output
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "blocked"


def test_readiness_does_not_create_missing_output_parents(tmp_path: Path) -> None:
    configuration = tmp_path / "onboarding.yaml"
    configuration.write_text(yaml.safe_dump(onboarding_payload()), encoding="utf-8")
    destination = tmp_path / "not-created" / "readiness.md"
    result = CliRunner().invoke(
        app, ["readiness", "--config", str(configuration), "--output", str(destination)]
    )
    assert result.exit_code == 1
    assert "parent directory must exist" in result.output
    assert not destination.parent.exists()


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("onboarding-config.schema.json", OnboardingConfig),
        ("readiness-report.schema.json", ReadinessReport),
    ],
)
def test_readiness_schemas_match_models(filename: str, model: type[BaseModel]) -> None:
    committed = json.loads(Path("schemas", filename).read_text(encoding="utf-8"))
    assert committed == model.model_json_schema()


def test_example_onboarding_profile_and_cli_remain_explicitly_unverified() -> None:
    example = Path("examples/onboarding-config.yaml")
    profile = load_onboarding_config(example)
    assert profile.schema_version == "1.0"
    assert profile.analysis.thresholds.minimum_observation_days == 30
    result = CliRunner().invoke(
        app,
        ["readiness", "--config", str(example), "--as-of", AS_OF.isoformat(), "--format", "json"],
    )
    assert result.exit_code == 3, result.output
    report = ReadinessReport.model_validate_json(result.stdout)
    assert report.mode == "offline"
    assert report.status == "unknown"
