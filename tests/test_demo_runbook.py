from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
import yaml
from test_assessment import payload

from aks_fleet_efficiency.assessment import AssessmentFragments
from aks_fleet_efficiency.collection import CollectionPlan
from aks_fleet_efficiency.config import load_onboarding_config

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "phase1-demo"


def test_demo_profiles_are_valid_and_separate_current_from_metrics() -> None:
    current = load_onboarding_config(DEMO / "inventory-profile.yaml")
    assert current.analysis.mode == "baseline"
    assert current.analysis.packs == ["AKS-NP-002", "AKS-SCHED-001"]
    assert not current.metric_sources
    plan = CollectionPlan.model_validate_json((DEMO / "inventory-plan.json").read_bytes())
    assert len(plan.clusters) == len(current.clusters) == 1
    assert plan.clusters[0].resource_id == current.clusters[0].resource_id
    assert plan.clusters[0].entities == []
    assert plan.workload_assessments == []
    assert plan.window_start is None and plan.window_end is None
    assert plan.maximum_duration_seconds <= 600
    managed = load_onboarding_config(DEMO / "managed-prometheus-profile.yaml")
    assert managed.metric_sources[0].type == "azure-managed-prometheus"
    assert managed.metric_sources[0].authentication == "default-azure-credential"
    assert managed.metric_sources[0].catalog_profile == "cadvisor-ksm"
    assert managed.analysis.mode == "baseline"
    assert managed.analysis.thresholds.minimum_observation_days == 30


def yaml_objects() -> list[dict[str, Any]]:
    return [
        item
        for path in DEMO.rglob("*.yaml")
        if not path.name.endswith("profile.yaml")
        for item in yaml.safe_load_all(path.read_text(encoding="utf-8"))
    ]


def test_demo_workloads_are_bounded_isolated_and_nonprivileged() -> None:
    objects = yaml_objects()
    deployment = next(item for item in objects if item["kind"] == "Deployment")
    assert deployment["spec"]["replicas"] == 1
    assert deployment["metadata"]["namespace"] == "fleet-advisor-demo"
    pod = deployment["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert not any(pod.get(field) for field in ["hostNetwork", "hostPID", "hostIPC"])
    container = pod["containers"][0]
    assert not container["image"].endswith(":latest")
    assert container["args"] == ["serve-hostname", "--port=8080"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["requests"] == {"cpu": "100m", "memory": "128Mi"}
    assert container["resources"]["limits"] == {"cpu": "500m", "memory": "512Mi"}
    assert not any(item["kind"] == "Secret" for item in objects)
    service = next(item for item in objects if item["kind"] == "Service")
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["selector"] == deployment["spec"]["selector"]["matchLabels"]
    hpa = next(item for item in objects if item["kind"] == "HorizontalPodAutoscaler")
    assert 1 <= hpa["spec"]["minReplicas"] <= hpa["spec"]["maxReplicas"] <= 2
    assert hpa["spec"]["scaleTargetRef"]["name"] == deployment["metadata"]["name"]
    pdb = next(item for item in objects if item["kind"] == "PodDisruptionBudget")
    assert pdb["spec"]["selector"]["matchLabels"] == service["spec"]["selector"]
    assert pdb["spec"]["maxUnavailable"] == 1


def test_demo_collection_role_is_get_list_only_with_no_sensitive_resources() -> None:
    objects = yaml_objects()
    role = next(item for item in objects if item["kind"] == "ClusterRole")
    for rule in role["rules"]:
        assert set(rule["verbs"]) <= {"get", "list"}
        assert "*" not in rule.get("resources", [])
        assert not set(rule.get("resources", [])) & {
            "secrets",
            "configmaps",
            "events",
            "pods/log",
            "pods/exec",
            "serviceaccounts/token",
            "roles",
            "clusterroles",
        }
    binding = next(item for item in objects if item["kind"] == "ClusterRoleBinding")
    assert binding["roleRef"]["name"] == role["metadata"]["name"]
    assert binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "advisor-demo-reader", "namespace": "fleet-advisor-demo"}
    ]


def test_demo_collector_refuses_live_without_opt_in_before_reading_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import collect_demo_inventory as demo

    token = Mock()
    clients = Mock()
    monkeypatch.setattr(demo, "demo_readers", clients)
    with pytest.raises(PermissionError, match="allow-live"):
        demo.collect_demo_inventory(
            DEMO / "inventory-profile.yaml",
            DEMO / "inventory-plan.json",
            server="https://synthetic.example.invalid",
            ca_file=tmp_path / "ca.crt",
            token_stream=token,
            output=tmp_path / "fragments.json",
        )
    token.read.assert_not_called()
    clients.assert_not_called()


@pytest.mark.parametrize("problem", ["metrics", "scope", "history", "http", "output"])
def test_demo_collector_rejects_invalid_scope_and_outputs_before_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    from scripts import collect_demo_inventory as demo

    profile = load_onboarding_config(DEMO / "inventory-profile.yaml")
    plan = CollectionPlan.model_validate_json((DEMO / "inventory-plan.json").read_bytes())
    if problem == "metrics":
        profile.analysis.packs = ["AKS-RQ-002"]
    elif problem == "scope":
        plan.clusters[0].resource_id += "-foreign"
    elif problem == "history":
        plan.clusters[0].node_history_reference = "not-approved"
    ca_file = tmp_path / "ca.crt"
    ca_file.write_text("synthetic-public-ca", encoding="utf-8")
    output = tmp_path / "fragments.json"
    if problem == "output":
        output.write_text("keep-existing", encoding="utf-8")
    monkeypatch.setattr(demo, "load_onboarding_config", lambda _: profile)
    monkeypatch.setattr(demo, "read_model", lambda *_: plan)
    clients = Mock()
    monkeypatch.setattr(demo, "demo_readers", clients)
    token = Mock()
    with pytest.raises((ValueError, FileExistsError)):
        demo.collect_demo_inventory(
            DEMO / "inventory-profile.yaml",
            DEMO / "inventory-plan.json",
            server="http://synthetic.invalid" if problem == "http" else "https://synthetic.invalid",
            ca_file=ca_file,
            token_stream=token,
            output=output,
            allow_live=True,
        )
    token.read.assert_not_called()
    clients.assert_not_called()
    if problem == "output":
        assert output.read_text(encoding="utf-8") == "keep-existing"


@pytest.mark.parametrize(
    "token",
    ["", " ", "two tokens", "x" * 16385],
    ids=["empty", "blank", "whitespace", "oversize"],
)
def test_demo_collector_rejects_empty_oversize_or_multiline_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    from scripts import collect_demo_inventory as demo

    ca_file = tmp_path / "ca.crt"
    ca_file.write_text("synthetic-public-ca", encoding="utf-8")
    clients = Mock()
    monkeypatch.setattr(demo, "demo_readers", clients)
    with pytest.raises(ValueError, match="token"):
        demo.collect_demo_inventory(
            DEMO / "inventory-profile.yaml",
            DEMO / "inventory-plan.json",
            server="https://synthetic.invalid",
            ca_file=ca_file,
            token_stream=io.StringIO(token),
            output=tmp_path / "fragments.json",
            allow_live=True,
        )
    clients.assert_not_called()


def test_demo_collector_preserves_partial_receipts_without_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    from scripts import collect_demo_inventory as demo

    fragments = AssessmentFragments.model_validate(payload())
    fragments.kubernetes[0].collection.pagination_complete = False
    from aks_fleet_efficiency.models import CollectionStatus

    fragments.kubernetes[0].collection.status = CollectionStatus.PARTIAL
    ca_file = tmp_path / "ca.crt"
    ca_file.write_text("synthetic-public-ca", encoding="utf-8")

    @contextmanager
    def readers(*args, **kwargs):
        yield Mock()

    monkeypatch.setattr(demo, "demo_readers", readers)
    monkeypatch.setattr(demo, "collect_fragments", lambda *args, **kwargs: fragments)
    target = tmp_path / "fragments.json"
    code = demo.collect_demo_inventory(
        DEMO / "inventory-profile.yaml",
        DEMO / "inventory-plan.json",
        server="https://synthetic.invalid",
        ca_file=ca_file,
        token_stream=io.StringIO("synthetic-secret-token\n"),
        output=target,
        allow_live=True,
    )
    assert code == 3
    assert "synthetic-secret-token" not in target.read_text(encoding="utf-8")
    assert AssessmentFragments.model_validate_json(target.read_bytes()) == fragments


def test_demo_reader_uses_explicit_ca_bearer_and_tenant_bound_cli_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from scripts import collect_demo_inventory as demo

    profile = load_onboarding_config(DEMO / "inventory-profile.yaml")
    plan = CollectionPlan.model_validate_json((DEMO / "inventory-plan.json").read_bytes())
    configuration = SimpleNamespace()
    sdk = SimpleNamespace(Configuration=Mock(return_value=configuration), ApiClient=MagicMock())
    identity = SimpleNamespace(AzureCliCredential=MagicMock())
    modules = {"kubernetes.client": sdk, "azure.identity": identity}
    monkeypatch.setattr(demo, "import_module", modules.__getitem__)
    inventory = MagicMock()
    reader = Mock()
    monkeypatch.setattr(demo, "AzureSdkInventoryReader", inventory)
    monkeypatch.setattr(demo, "KubernetesSdkReader", reader)
    ca_file = tmp_path / "ca.crt"
    with demo.demo_readers(
        profile, plan, "https://synthetic.invalid", ca_file, "synthetic-token"
    ) as clients:
        assert clients.kubernetes[profile.clusters[0].resource_id] == reader.return_value
        assert clients.inventory == inventory.return_value.__enter__.return_value
    assert configuration.verify_ssl is True
    assert configuration.debug is False
    assert configuration.retries == 0
    assert configuration.ssl_ca_cert == str(ca_file.resolve())
    assert configuration.api_key == {"BearerToken": "synthetic-token"}
    assert configuration.api_key_prefix == {"BearerToken": "Bearer"}
    identity.AzureCliCredential.assert_called_once_with(
        tenant_id=str(profile.scope.tenant_id), process_timeout=10
    )
    assert inventory.call_args.kwargs["credential"] == (
        identity.AzureCliCredential.return_value.__enter__.return_value
    )


def test_demo_helper_main_reports_invalid_yaml_without_echoing_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import collect_demo_inventory as demo

    profile = tmp_path / "profile.yaml"
    profile.write_text("invalid: [ synthetic-private-value", encoding="utf-8")
    code = demo.main(
        [
            "--config",
            str(profile),
            "--plan",
            str(DEMO / "inventory-plan.json"),
            "--server",
            "https://synthetic.invalid",
            "--ca-file",
            str(tmp_path / "ca.crt"),
            "--output",
            str(tmp_path / "fragments.json"),
            "--token-stdin",
            "--allow-live",
        ]
    )
    assert code == 2
    error = capsys.readouterr().err
    assert "Collection rejected" in error
    assert "synthetic-private-value" not in error


def test_demo_preview_is_offline_and_has_no_metric_requests() -> None:
    from datetime import UTC, datetime

    from aks_fleet_efficiency.operator import preview_execution

    profile = load_onboarding_config(DEMO / "inventory-profile.yaml")
    plan = CollectionPlan.model_validate_json((DEMO / "inventory-plan.json").read_bytes())
    preview = preview_execution(profile, plan, as_of=datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert preview.query_plan.requests == 0
    assert not preview.queries


def test_demo_manifest_current_metadata_produces_review_and_replays() -> None:
    from test_assessment import AS_OF, profile

    from aks_fleet_efficiency.assessment import assess_fragments
    from aks_fleet_efficiency.collectors.kubernetes_metadata import project_metadata
    from aks_fleet_efficiency.config import AdvisorConfig
    from aks_fleet_efficiency.rules.engine import analyze

    value = payload()
    value["metrics"] = []
    value["workload_assessments"] = []
    deployment = next(item for item in yaml_objects() if item["kind"] == "Deployment")
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["spec"] = project_metadata(
        "v1/pods",
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod["name"],
                "namespace": pod["namespace"],
                "uid": pod["uid"],
            },
            "spec": deployment["spec"]["template"]["spec"],
        },
    ).spec
    config = profile()
    config.analysis = AdvisorConfig(packs=["AKS-NP-002", "AKS-SCHED-001"])
    result = assess_fragments(AssessmentFragments.model_validate(value), config, as_of=AS_OF)
    assert {item.rule_id for item in result.report.recommendations} == {
        "AKS-NP-002",
        "AKS-SCHED-001",
    }
    assert all(
        item.proposed_requests is None
        and item.proposed_limits is None
        and item.proposed_replica_floor is None
        and item.estimated_monthly_savings is None
        for item in result.report.recommendations
    )
    assert analyze(result.snapshot, config.analysis, as_of=AS_OF) == result.report
