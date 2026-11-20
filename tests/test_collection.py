import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aks_fleet_efficiency.assessment import assess_fragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collection import CollectionPlan, CollectionReaders, collect_fragments
from aks_fleet_efficiency.collectors.azure_resource_graph import InventoryPage
from aks_fleet_efficiency.collectors.kubernetes_metadata import REQUIRED_RESOURCES, KubernetesPage
from aks_fleet_efficiency.config import OnboardingConfig

TENANT = "00000000-0000-0000-0000-000000000000"
CLUSTER = (
    f"/subscriptions/{TENANT}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def profile() -> OnboardingConfig:
    return OnboardingConfig.model_validate(
        {
            "scope": {"tenant_id": TENANT, "subscription_ids": [TENANT]},
            "clusters": [{"resource_id": CLUSTER}],
            "report_directory": "reports",
        }
    )


def plan() -> CollectionPlan:
    return CollectionPlan.model_validate(
        {
            "window_start": "2026-09-29T00:00:00Z",
            "window_end": "2026-10-29T00:00:00Z",
            "clusters": [{"resource_id": CLUSTER, "expected_cluster_uid": "synthetic-cluster-uid"}],
        }
    )


class ForbiddenInventory:
    tenant_id = TENANT

    def query(self, **kwargs: object) -> InventoryPage:
        pytest.fail("unauthorized collection performed I/O")


def test_collection_requires_explicit_consent_before_any_reader_call() -> None:
    readers = CollectionReaders(inventory=ForbiddenInventory())
    with pytest.raises(PermissionError, match="explicit"):
        collect_fragments(profile(), plan(), readers, clock=lambda: AS_OF)


def test_foreign_collection_target_is_rejected_before_io() -> None:
    settings = plan().model_dump(mode="json")
    settings["clusters"][0]["resource_id"] = CLUSTER + "-foreign"
    with pytest.raises(ValueError, match="scope"):
        collect_fragments(
            profile(),
            CollectionPlan.model_validate(settings),
            CollectionReaders(inventory=ForbiddenInventory()),
            allow_live=True,
            clock=lambda: AS_OF,
        )


@pytest.mark.parametrize("defect", ["reader-binding", "metric-source", "policy-window"])
def test_invalid_reader_or_policy_preflight_never_calls_inventory(defect: str) -> None:
    request = plan()
    readers = CollectionReaders(inventory=ForbiddenInventory())
    if defect == "reader-binding":
        metadata = Metadata()
        metadata.cluster_resource_id = CLUSTER + "-foreign"
        readers.kubernetes = {CLUSTER: metadata}
    elif defect == "metric-source":
        readers.metrics = {"unapproved": object()}
    else:
        bundle = json.loads(
            Path("examples/fixtures/history-assessment.json").read_text(encoding="utf-8")
        )
        from aks_fleet_efficiency.workload_history import WorkloadAssessmentBinding

        request.workload_assessments = [
            WorkloadAssessmentBinding.model_validate(bundle["workload_assessments"][0])
        ]
    with pytest.raises(ValueError):
        collect_fragments(profile(), request, readers, allow_live=True, clock=lambda: AS_OF)


class Inventory:
    tenant_id = TENANT

    def __init__(self) -> None:
        self.calls = 0

    def query(self, **kwargs: Any) -> InventoryPage:
        self.calls += 1
        return InventoryPage(
            rows=[
                {
                    "id": CLUSTER,
                    "type": "microsoft.containerservice/managedclusters",
                    "name": "aks-synthetic",
                    "subscriptionId": TENANT,
                    "resourceGroup": "rg-synthetic",
                    "location": "eastus",
                    "kubernetesVersion": "1.34.1",
                    "skuTier": "Standard",
                    "nodeProvisioningMode": "Manual",
                    "managedPrometheusEnabled": False,
                    "costAnalysisEnabled": False,
                    "kedaEnabled": False,
                    "vpaEnabled": False,
                    "agentPoolProfiles": [],
                }
            ],
            observed_at=AS_OF,
        )


class Metadata:
    cluster_resource_id = CLUSTER

    def __init__(self) -> None:
        self.calls = 0
        bundle = json.loads(
            Path("examples/fixtures/workload-assessment.json").read_text(encoding="utf-8")
        )
        self.resources = bundle["kubernetes"][0]["resources"]

    def discover(self) -> set[str]:
        self.calls += 1
        return set(REQUIRED_RESOURCES)

    def list_page(self, resource: str, **kwargs: Any) -> KubernetesPage:
        from aks_fleet_efficiency.collectors.kubernetes_metadata import RESOURCE_CATALOG

        self.calls += 1
        items = [
            {
                "apiVersion": item["api_version"],
                "kind": item["kind"],
                "metadata": {
                    "name": item["name"],
                    "namespace": item.get("namespace"),
                    "uid": item["uid"],
                    "ownerReferences": item.get("owner_references", []),
                },
                "spec": item.get("spec", {}),
                "status": item.get("status", {}),
            }
            for item in self.resources
            if item["kind"] == RESOURCE_CATALOG[resource].kind
            and item["api_version"] == resource.rsplit("/", 1)[0]
        ]
        return KubernetesPage(items=items, resource_version="synthetic-version", observed_at=AS_OF)


def test_injected_collectors_produce_one_useful_replayable_assessment() -> None:
    inventory, metadata = Inventory(), Metadata()
    fragments = collect_fragments(
        profile(),
        plan(),
        CollectionReaders(inventory=inventory, kubernetes={CLUSTER: metadata}),
        allow_live=True,
        clock=lambda: AS_OF,
    )
    result = assess_fragments(fragments, profile(), as_of=AS_OF)
    assert inventory.calls == 1
    assert metadata.calls > 1
    assert "AKS-RQ-001" in {item.rule_id for item in result.report.recommendations}
    assert result.status == "partial"
    assert fragments.window_start == datetime(2026, 9, 29, tzinfo=UTC)
    assert fragments.window_end == datetime(2026, 10, 29, tzinfo=UTC)


def test_total_read_budget_prevents_further_network_reads() -> None:
    inventory, metadata = Inventory(), Metadata()
    settings = plan().model_copy(update={"maximum_reads": 1})
    result = collect_fragments(
        profile(),
        settings,
        CollectionReaders(inventory=inventory, kubernetes={CLUSTER: metadata}),
        allow_live=True,
        clock=lambda: AS_OF,
    )
    assert inventory.calls == 1
    assert metadata.calls == 0
    assert result.kubernetes[0].collection.status == "failed"
    assert result.kubernetes[0].collection.errors[0].code == "timeout"


def test_collect_cli_requires_allow_live_before_constructing_clients(tmp_path: Path) -> None:
    settings = tmp_path / "profile.json"
    settings.write_text(profile().model_dump_json(), encoding="utf-8")
    request = tmp_path / "plan.json"
    request.write_text(plan().model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "collect",
            "--config",
            str(settings),
            "--plan",
            str(request),
            "--output",
            str(tmp_path / "bundle.json"),
        ],
    )
    assert result.exit_code == 2
    assert not (tmp_path / "bundle.json").exists()


def test_assessment_artifacts_are_replayable_and_never_overwrite_existing_directory(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "assessment"
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--config",
            "examples/pool-assessment-config.yaml",
            "--as-of",
            AS_OF.isoformat(),
            "--artifacts",
            str(destination),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 3, result.output
    expected = {
        "fragments.json",
        "snapshot.json",
        "analysis-config.json",
        "assessment.json",
        "report.md",
        "manifest.json",
    }
    assert {path.name for path in destination.iterdir()} == expected
    replay = CliRunner().invoke(
        app,
        [
            "analyze",
            "--snapshot",
            str(destination / "snapshot.json"),
            "--config",
            str(destination / "analysis-config.json"),
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
        ],
    )
    assert replay.exit_code == 0, replay.output
    assert (
        json.loads(replay.output)
        == json.loads((destination / "assessment.json").read_text(encoding="utf-8"))["report"]
    )
    before = {path.name: path.read_bytes() for path in destination.iterdir()}
    repeated = CliRunner().invoke(
        app,
        [
            "assess",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--config",
            "examples/pool-assessment-config.yaml",
            "--as-of",
            AS_OF.isoformat(),
            "--artifacts",
            str(destination),
        ],
    )
    assert repeated.exit_code == 1
    assert before == {path.name: path.read_bytes() for path in destination.iterdir()}


def test_artifact_manifest_hashes_exact_persisted_bytes(tmp_path: Path) -> None:
    from hashlib import sha256

    from aks_fleet_efficiency.artifacts import write_assessment_artifacts
    from aks_fleet_efficiency.assessment import AssessmentFragments
    from aks_fleet_efficiency.config import load_onboarding_config

    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/history-assessment.json").read_bytes()
    )
    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    destination = tmp_path / "artifacts"
    write_assessment_artifacts(destination, fragments, result, settings.analysis)
    manifest = json.loads((destination / "manifest.json").read_bytes())
    assert manifest["input_digest"] == result.input_digest
    assert len(manifest["files"]) == 5
    for name, digest in manifest["files"].items():
        assert sha256((destination / name).read_bytes()).hexdigest() == digest


def test_failed_artifact_write_never_publishes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aks_fleet_efficiency import artifacts

    def fail(path: Path, text: str) -> None:
        raise OSError("synthetic failure")

    monkeypatch.setattr(artifacts, "write_exclusive", fail)
    destination = tmp_path / "artifacts"
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--config",
            "examples/pool-assessment-config.yaml",
            "--as-of",
            AS_OF.isoformat(),
            "--artifacts",
            str(destination),
        ],
    )
    assert result.exit_code == 1
    assert not (destination / "manifest.json").exists()


@pytest.mark.parametrize("command", ["collect", "assess"])
def test_live_cli_existing_output_never_constructs_clients(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aks_fleet_efficiency import cli

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("output preflight must precede client construction")

    monkeypatch.setattr(cli, "builtin_readers", forbidden)
    output = tmp_path / "existing.json"
    output.write_text("untouched", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            command,
            "--config",
            "examples/pool-assessment-config.yaml",
            "--plan",
            "examples/fixtures/history-assessment.json",
            "--allow-live",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1
    assert output.read_text(encoding="utf-8") == "untouched"


def test_combined_cli_uses_same_collection_and_offline_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    from aks_fleet_efficiency import cli

    @contextmanager
    def injected(settings: OnboardingConfig, request: CollectionPlan, *, allow_live: bool):
        assert allow_live
        yield CollectionReaders(inventory=Inventory(), kubernetes={CLUSTER: Metadata()})

    monkeypatch.setattr(cli, "builtin_readers", injected)
    settings = tmp_path / "profile.json"
    settings.write_text(profile().model_dump_json(), encoding="utf-8")
    request = tmp_path / "plan.json"
    request.write_text(plan().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "collect_fragments",
        lambda settings, request, readers, **kwargs: collect_fragments(
            settings, request, readers, allow_live=True, clock=lambda: AS_OF
        ),
    )
    directory = tmp_path / "artifacts"
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "--config",
            str(settings),
            "--plan",
            str(request),
            "--allow-live",
            "--as-of",
            AS_OF.isoformat(),
            "--artifacts",
            str(directory),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 3, result.output
    replay = CliRunner().invoke(
        app,
        [
            "assess",
            "--config",
            str(settings),
            "--fragments",
            str(directory / "fragments.json"),
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
        ],
    )
    assert replay.exit_code == 3
    assert json.loads(result.output) == json.loads(replay.output)


@pytest.mark.parametrize("budget", ["maximum_objects", "maximum_duration_seconds"])
def test_object_and_deadline_budgets_leave_failed_receipts(budget: str) -> None:
    from datetime import timedelta

    inventory = Inventory()
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return AS_OF + timedelta(seconds=calls if budget == "maximum_duration_seconds" else 0)

    request = plan().model_copy(update={budget: 1})
    result = collect_fragments(
        profile(),
        request,
        CollectionReaders(inventory=inventory, kubernetes={CLUSTER: Metadata()}),
        allow_live=True,
        clock=clock,
    )
    assert result.kubernetes[0].collection.status == "failed"
    assert result.kubernetes[0].collection.errors[0].code == "timeout"


def test_exported_objects_share_the_run_budget_with_live_inventory() -> None:
    from aks_fleet_efficiency.artifacts import read_model
    from aks_fleet_efficiency.models import KubernetesMetadataSnapshot

    exported = read_model(
        Path("examples/fixtures/kubernetes-export.json"), KubernetesMetadataSnapshot
    )
    request = plan().model_copy(update={"maximum_objects": len(exported.resources)})
    result = collect_fragments(
        profile(),
        request,
        CollectionReaders(inventory=Inventory(), metadata_snapshots={CLUSTER: exported}),
        allow_live=True,
        clock=lambda: AS_OF,
    )
    assert result.azure[0].collection.status == "failed"
    assert result.azure[0].collection.errors[0].code == "timeout"


@pytest.mark.parametrize("command", ["analyze", "readiness"])
def test_snapshot_commands_never_overwrite_existing_output(command: str, tmp_path: Path) -> None:
    output = tmp_path / "existing.json"
    output.write_text("untouched", encoding="utf-8")
    arguments = [
        command,
        "--snapshot",
        "examples/fixtures/fleet-snapshot.json",
        "--output",
        str(output),
    ]
    if command == "readiness":
        arguments.extend(["--config", "examples/onboarding-config.yaml"])
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 1
    assert output.read_text(encoding="utf-8") == "untouched"


def test_analyze_sanitizes_invalid_sensitive_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"synthetic-secret": "must-not-be-echoed"}', encoding="utf-8")
    result = CliRunner().invoke(app, ["analyze", "--snapshot", str(snapshot)])
    assert result.exit_code == 2
    assert "synthetic-secret" not in result.output
    assert "must-not-be-echoed" not in result.output


@pytest.mark.parametrize("defect", ["missing-export", "fingerprint", "projection"])
def test_builtin_export_preflight_precedes_client_construction(
    defect: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aks_fleet_efficiency import live_collection

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid export must fail before credentials or clients")

    monkeypatch.setattr(live_collection, "AzureSdkInventoryReader", forbidden)
    request = plan()
    if defect != "missing-export":
        exported = json.loads(Path("examples/fixtures/kubernetes-export.json").read_bytes())
        if defect == "fingerprint":
            exported["cluster_uid"] = "foreign-uid"
        else:
            pod = next(item for item in exported["resources"] if item["kind"] == "Pod")
            pod["spec"]["containers"][0]["env"] = [
                {"name": "FORBIDDEN", "value": "synthetic-secret"}
            ]
        path = tmp_path / "metadata.json"
        path.write_text(json.dumps(exported), encoding="utf-8")
        request.clusters[0].metadata_export = path
    with (
        pytest.raises(ValueError),
        live_collection.builtin_readers(profile(), request, allow_live=True),
    ):
        pytest.fail("invalid export was accepted")


def test_builtin_readers_close_on_caller_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from aks_fleet_efficiency import live_collection

    closed = []

    @contextmanager
    def inventory(settings: OnboardingConfig):
        try:
            yield Inventory()
        finally:
            closed.append(True)

    monkeypatch.setattr(live_collection, "AzureSdkInventoryReader", inventory)
    request = live_collection.load_collection_plan(Path("examples/collection-plan.json"))
    with (
        pytest.raises(RuntimeError, match="synthetic"),
        live_collection.builtin_readers(profile(), request, allow_live=True) as readers,
    ):
        assert CLUSTER in readers.metadata_snapshots
        raise RuntimeError("synthetic caller failure")
    assert closed == [True]
