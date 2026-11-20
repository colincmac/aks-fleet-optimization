from __future__ import annotations

import io
import json
import tomllib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest

from aks_fleet_efficiency.collectors import kubernetes_metadata as kubernetes_module
from aks_fleet_efficiency.collectors.kubernetes_metadata import (
    REQUIRED_RESOURCES,
    KubernetesMetadataCollector,
    KubernetesPage,
    KubernetesReadError,
    KubernetesSdkReader,
    project_current_container_attempts,
    project_metadata,
)
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import (
    AzureClusterInventory,
    CollectionStatus,
    KubernetesMetadataSnapshot,
    KubernetesObjectMetadata,
    PodContainerAttempts,
)
from aks_fleet_efficiency.scheduling import (
    SchedulingCompletenessAudit,
    SchedulingPlacementReview,
    SchedulingShapeDiagnostics,
    SchedulingSourceCollection,
    audit_scheduling_completeness,
    calculate_scheduling_constraints,
    diagnose_scheduling_shapes,
    project_daemonset_status,
    project_disruption_protection,
    project_scheduling_shapes,
    review_scheduling_placement,
)
from aks_fleet_efficiency.startup import project_startup_history

SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)
CLUSTER_UID = "synthetic-kube-system-uid"
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def profile() -> OnboardingConfig:
    return OnboardingConfig.model_validate(
        {
            "scope": {"tenant_id": SUBSCRIPTION, "subscription_ids": [SUBSCRIPTION]},
            "clusters": [{"resource_id": CLUSTER}],
            "report_directory": "reports",
        }
    )


def metadata(name: str, uid: str, namespace: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"name": name, "uid": uid}
    if namespace is not None:
        value["namespace"] = namespace
    return value


class FakeKubernetesReader:
    cluster_resource_id = CLUSTER

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {name: [] for name in REQUIRED_RESOURCES}
        self.rows["v1/namespaces"] = [
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": metadata("kube-system", CLUSTER_UID),
            },
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": metadata("orders", "namespace-uid"),
            },
        ]
        self.calls: list[tuple[str, str | None]] = []
        self.errors: dict[str, str] = {}

    def discover(self) -> set[str]:
        return set(self.rows)

    def list_page(
        self, resource: str, *, continue_token: str | None, page_size: int
    ) -> KubernetesPage:
        self.calls.append((resource, continue_token))
        if resource in self.errors:
            raise KubernetesReadError(self.errors[resource])
        return KubernetesPage(
            items=self.rows[resource], resource_version="synthetic-rv", observed_at=AS_OF
        )


def collect(reader: FakeKubernetesReader, **options: Any) -> Any:
    return KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=reader,
        clock=lambda: AS_OF,
        sleep=lambda _: None,
        **options,
    ).collect()


def test_collector_projects_workload_metadata_without_sensitive_pod_fields() -> None:
    reader = FakeKubernetesReader()
    reader.rows["apps/v1/deployments"] = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": metadata("orders", "deployment-uid", "orders"),
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "api",
                                "resources": {"requests": {"cpu": "250m", "memory": "128Mi"}},
                                "env": [{"name": "PASSWORD", "value": "synthetic-secret"}],
                                "args": ["synthetic-private-argument"],
                                "envFrom": [{"secretRef": {"name": "synthetic-secret-reference"}}],
                                "livenessProbe": {
                                    "periodSeconds": 7,
                                    "httpGet": {
                                        "path": "/synthetic-private-health-path",
                                        "httpHeaders": [
                                            {
                                                "name": "Authorization",
                                                "value": "synthetic-private-header",
                                            }
                                        ],
                                    },
                                },
                                "readinessProbe": {
                                    "failureThreshold": 2,
                                    "exec": {"command": ["synthetic-private-probe-command"]},
                                },
                            }
                        ]
                    }
                },
            },
        }
    ]
    result = collect(reader)
    assert result.collection.status == "complete"
    assert result.cluster_uid == CLUSTER_UID
    deployment = next(resource for resource in result.resources if resource.kind == "Deployment")
    assert deployment.uid == "deployment-uid"
    assert deployment.spec["replicas"] == 3
    projected_container = deployment.spec["template"]["spec"]["containers"][0]
    assert projected_container["livenessProbe"] == {"periodSeconds": 7}
    assert projected_container["readinessProbe"] == {"failureThreshold": 2}
    serialized = result.model_dump_json()
    assert '"250m"' in serialized
    assert "synthetic-secret" not in serialized
    assert "synthetic-private-argument" not in serialized
    assert "synthetic-private-health-path" not in serialized
    assert "synthetic-private-header" not in serialized
    assert "synthetic-private-probe-command" not in serialized
    assert "envFrom" not in serialized


def current_attempt_inputs(
    change: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[KubernetesMetadataSnapshot, dict[str, Any]]:
    reader = FakeKubernetesReader()
    add_workload_chain(reader)
    pod = reader.rows["v1/pods"][0]
    pod["metadata"].update(
        creationTimestamp=(AS_OF - timedelta(hours=1)).isoformat(),
        resourceVersion="synthetic-pod-version",
    )
    pod["status"] = {
        "containerStatuses": [
            {
                "name": "api",
                "restartCount": 0,
                "containerID": "containerd://SENSITIVE-CURRENT-ID",
                "state": {"running": {"startedAt": (AS_OF - timedelta(minutes=5)).isoformat()}},
                "ready": True,
                "started": True,
                "message": "SENSITIVE-STATUS-TEXT",
                "image": "SENSITIVE-IMAGE",
            }
        ]
    }
    if change is not None:
        change(pod)
    return collect(reader), pod


def scheduling_audit_input() -> KubernetesMetadataSnapshot:
    snapshot, _ = current_attempt_inputs()
    node_name = "synthetic-reservation-node"
    snapshot.resources.append(
        KubernetesObjectMetadata(
            api_version="v1",
            kind="Node",
            name=node_name,
            uid="synthetic-reservation-node-uid",
            spec={},
            status={
                "capacity": {"cpu": "2", "memory": "2Gi", "pods": "20"},
                "allocatable": {"cpu": "2", "memory": "2Gi", "pods": "20"},
            },
        )
    )
    pod = next(item for item in snapshot.resources if item.kind == "Pod")
    pod.spec.update(
        nodeName=node_name,
        initContainers=[],
        overhead={},
        resources={},
        containers=[{"name": "api", "resources": {"requests": {"cpu": "250m", "memory": "128Mi"}}}],
    )
    pod.status = {"phase": "Running"}
    system = KubernetesObjectMetadata.model_validate(pod.model_dump())
    system.name = "synthetic-system-pod"
    system.uid = "synthetic-system-pod-uid"
    system.namespace = "kube-system"
    system.owner_references = []
    system.spec["containers"] = [
        {"name": "system", "resources": {"requests": {"cpu": "500m", "memory": "256Mi"}}}
    ]
    snapshot.resources.append(system)
    return snapshot


def test_scheduling_audit_counts_system_reservations_without_claiming_fit() -> None:
    snapshot = scheduling_audit_input()
    original = snapshot.model_dump_json()
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert audit.fit_status == "blocked"
    assert {"pod_os", "host_ports", "scheduler_configuration"} <= set(audit.unobserved_dimensions)
    assert audit.tenant_id == SUBSCRIPTION and audit.cluster_uid == CLUSTER_UID
    assert audit.collection == snapshot.collection
    assert len(audit.metadata_digest) == 64
    node = audit.nodes[0]
    assert node.node_uid == "synthetic-reservation-node-uid"
    assert node.observed_cpu_request_mcpu == 750
    assert node.observed_memory_request_mib == 384
    assert node.observed_nonterminal_pod_count == 2
    assert set(node.pod_uids) == {"pod-uid", "synthetic-system-pod-uid"}
    assert snapshot.model_dump_json() == original


def test_scheduling_audit_accepts_the_documented_saved_fixture() -> None:
    from aks_fleet_efficiency.assessment import AssessmentFragments

    path = Path(__file__).resolve().parents[1] / "examples/fixtures/pool-assessment.json"
    fragments = AssessmentFragments.model_validate_json(path.read_text(encoding="utf-8"))
    audit = audit_scheduling_completeness(
        fragments.kubernetes[0], as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert audit.fit_status == "blocked"
    assert audit.nodes and "scheduler_configuration" in audit.unobserved_dimensions


def test_scheduling_audit_keeps_cpu_memory_and_count_quality_independent() -> None:
    snapshot = scheduling_audit_input()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    pod.spec["containers"] = [{"name": "api", "resources": {"requests": {"cpu": "250m"}}}]
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    node = audit.nodes[0]
    assert node.observed_cpu_request_mcpu == 750
    assert node.observed_memory_request_mib is None
    assert node.observed_nonterminal_pod_count == 2
    assert node.issues == ["unknown_memory_request"]
    assert audit.fit_status == "blocked"


def test_scheduling_audit_missing_pod_budget_cannot_be_assumed_empty() -> None:
    snapshot = scheduling_audit_input()
    next(item for item in snapshot.resources if item.uid == "pod-uid").spec.pop("resources")
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    node = audit.nodes[0]
    assert node.observed_cpu_request_mcpu is None and node.observed_memory_request_mib is None
    assert node.observed_nonterminal_pod_count == 2
    assert "unknown_pod_resource_budget" in node.issues


@pytest.mark.parametrize("phase", ["Succeeded", "Failed", "Unknown", None])
def test_scheduling_audit_terminal_and_unknown_phases(phase: str | None) -> None:
    snapshot = scheduling_audit_input()
    pod = next(item for item in snapshot.resources if item.uid == "synthetic-system-pod-uid")
    pod.status = {"phase": phase} if phase is not None else {}
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    node = audit.nodes[0]
    if phase in {"Succeeded", "Failed"}:
        assert node.observed_cpu_request_mcpu == 250
        assert node.observed_memory_request_mib == 128
        assert node.observed_nonterminal_pod_count == 1
        assert node.pod_uids == ["pod-uid"]
        assert audit.terminal_pod_uids == [pod.uid]
    else:
        assert node.observed_cpu_request_mcpu is None
        assert node.observed_memory_request_mib is None
        assert node.observed_nonterminal_pod_count is None
        assert "unknown_pod_phase" in node.issues
        assert pod.uid in node.pod_uids


def test_scheduling_audit_keeps_pending_competitors_visible_without_assignment() -> None:
    snapshot = scheduling_audit_input()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    pod.status = {"phase": "Pending"}
    pod.spec.pop("nodeName")
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert audit.pending_pod_uids == ["pod-uid"]
    assert audit.unresolved_assignment_pod_uids == ["pod-uid"]
    assert audit.nodes[0].pod_uids == ["synthetic-system-pod-uid"]
    assert audit.nodes[0].observed_cpu_request_mcpu is None
    assert "unresolved_pod_assignment" in audit.issues


@pytest.mark.parametrize("defect", ["partial", "missing-clock", "stale", "future", "missing-list"])
def test_scheduling_audit_blocks_totals_for_incomplete_or_invalid_sources(defect: str) -> None:
    snapshot = scheduling_audit_input()
    if defect == "partial":
        snapshot.collection.status = CollectionStatus.PARTIAL
        snapshot.collection.missing_fields.append("synthetic-gap")
    elif defect == "missing-clock":
        snapshot.collection.source_observed_at = None
    elif defect == "stale":
        snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3601)
    elif defect == "future":
        snapshot.generated_at = AS_OF + timedelta(seconds=1)
    else:
        snapshot.resource_versions.pop("v1/pods")
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert audit.issues and audit.fit_status == "blocked"
    assert audit.collection == snapshot.collection
    assert audit.nodes[0].observed_cpu_request_mcpu is None
    assert audit.nodes[0].observed_memory_request_mib is None
    assert audit.nodes[0].observed_nonterminal_pod_count is None


def test_scheduling_audit_source_age_boundary_does_not_refresh_receipts() -> None:
    snapshot = scheduling_audit_input()
    snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3600)
    audit = audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert audit.nodes[0].observed_cpu_request_mcpu == 750
    assert audit.collection.source_observed_at == AS_OF - timedelta(seconds=3600)
    assert SchedulingCompletenessAudit.model_validate_json(audit.model_dump_json()) == audit
    payload = audit.model_dump(mode="json")
    payload["fit_status"] = "satisfied"
    with pytest.raises(ValueError):
        SchedulingCompletenessAudit.model_validate(payload)


@pytest.mark.parametrize("defect", ["duplicate-uid", "duplicate-name", "fingerprint", "scope"])
def test_scheduling_audit_rejects_ambiguous_or_foreign_metadata(defect: str) -> None:
    snapshot = scheduling_audit_input()
    if defect.startswith("duplicate"):
        node = next(item for item in snapshot.resources if item.kind == "Node")
        duplicate = KubernetesObjectMetadata.model_validate(node.model_dump())
        if defect == "duplicate-name":
            duplicate.uid = "synthetic-other-node-uid"
        snapshot.resources.append(duplicate)
    elif defect == "fingerprint":
        snapshot.cluster_uid = "synthetic-foreign-fingerprint"
    else:
        snapshot.cluster_resource_id += "-foreign"
    with pytest.raises(ValueError):
        audit_scheduling_completeness(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)


@pytest.mark.parametrize("age", [0, -1, True, 1.5])
def test_scheduling_audit_rejects_invalid_source_age_budgets(age: Any) -> None:
    with pytest.raises(ValueError):
        audit_scheduling_completeness(
            scheduling_audit_input(), as_of=AS_OF, maximum_source_age_seconds=age
        )


def native_scheduling_inputs() -> tuple[
    KubernetesMetadataSnapshot, list[dict[str, Any]], list[dict[str, Any]]
]:
    snapshot = scheduling_audit_input()
    rows = []
    for item in snapshot.resources:
        if item.kind not in {"Pod", "Node"}:
            continue
        rows.append(
            {
                "apiVersion": "v1",
                "kind": item.kind,
                "metadata": {
                    "name": item.name,
                    "namespace": item.namespace,
                    "uid": item.uid,
                    "labels": item.labels,
                    "ownerReferences": item.owner_references,
                    "resourceVersion": "synthetic-object-version",
                },
                "spec": json.loads(json.dumps(item.spec)),
                "status": json.loads(json.dumps(item.status)),
            }
        )
    pods = [row for row in rows if row["kind"] == "Pod"]
    nodes = [row for row in rows if row["kind"] == "Node"]
    pods[0]["spec"].update(os={"name": "linux"}, hostNetwork=False, schedulingGates=[])
    pods[0]["spec"]["containers"][0]["ports"] = [{"hostPort": 8080, "hostIP": "SENSITIVE-ADDRESS"}]
    pods[0]["spec"]["containers"][0]["env"] = [{"name": "TOKEN", "value": "SENSITIVE-ENVIRONMENT"}]
    nodes[0]["metadata"]["labels"]["kubernetes.io/os"] = "linux"
    nodes[0]["status"]["conditions"] = [
        {"type": "Ready", "status": "True", "message": "SENSITIVE-CONDITION"}
    ]
    for row in rows:
        projected = project_metadata("v1/pods" if row["kind"] == "Pod" else "v1/nodes", row)
        index = next(
            index for index, item in enumerate(snapshot.resources) if item.uid == projected.uid
        )
        snapshot.resources[index] = projected
    return snapshot, pods, nodes


def test_scheduling_shape_projection_is_explicit_and_does_not_admit_fit() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    original = json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True)
    projection = project_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert projection.mapping_reference == "kubernetes-core-v1@v1.36.0"
    assert projection.audit.fit_status == "blocked"
    assert projection.source_binding == "unverified_supplied_native_objects"
    pod = next(item for item in projection.pods if item.pod_uid == pods[0]["metadata"]["uid"])
    assert pod.os_name == "linux"
    assert pod.features["host_network"] == "absent"
    assert pod.features["host_ports"] == "present"
    assert pod.features["scheduling_gates"] == "absent"
    assert pod.features["resource_claims"] == "unknown"
    assert projection.nodes[0].allocatable_pod_slots == 20
    assert projection.nodes[0].conditions["Ready"] == "True"
    serialized = projection.model_dump_json()
    assert all(
        value not in serialized
        for value in (
            "SENSITIVE-ADDRESS",
            "SENSITIVE-ENVIRONMENT",
            "SENSITIVE-CONDITION",
            '"env"',
            '"hostIP"',
        )
    )
    assert json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True) == original


@pytest.mark.parametrize(
    "defect", ["missing-pod", "duplicate-pod", "foreign-pod", "changed-projection", "bad-version"]
)
def test_scheduling_shapes_reject_incomplete_or_substituted_native_rows(defect: str) -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    if defect == "missing-pod":
        pods.pop()
    elif defect == "duplicate-pod":
        pods.append(json.loads(json.dumps(pods[0])))
    elif defect == "foreign-pod":
        pods[0]["metadata"]["uid"] = "foreign-pod-uid"
    elif defect == "changed-projection":
        pods[0]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "500m"
    else:
        pods[0]["metadata"]["resourceVersion"] = True
    with pytest.raises(ValueError):
        project_scheduling_shapes(
            snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
        )


def test_scheduling_shapes_malformed_new_fields_stay_unknown() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    pods[0]["spec"]["os"]["name"] = ["SENSITIVE-INVALID-OS"]
    projection = project_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert projection.pods[0].os_name == "unknown"
    assert projection.nodes[0].conditions["MemoryPressure"] == "Unknown"
    assert "SENSITIVE-INVALID-OS" not in projection.model_dump_json()
    assert projection.audit.fit_status == "blocked"


def test_scheduling_shapes_detect_unsupported_pod_budget_resources() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    pods[0]["spec"]["resources"] = {"requests": {"example.invalid/accelerator": "1"}}
    for container in pods[0]["spec"]["containers"]:
        container["resources"]["limits"] = {}
    projected = project_metadata("v1/pods", pods[0])
    index = next(
        index for index, item in enumerate(snapshot.resources) if item.uid == projected.uid
    )
    snapshot.resources[index] = projected
    projection = project_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert projection.pods[0].features["pod_resource_budget"] == "present"
    assert projection.pods[0].features["extended_resources"] == "present"
    assert "example.invalid/accelerator" not in projection.model_dump_json()


def test_scheduling_shapes_detect_claim_references_before_dropping_their_bodies() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    pods[0]["spec"]["resourceClaims"] = []
    pods[0]["spec"]["containers"][0]["resources"]["claims"] = [
        {"name": "SENSITIVE-CLAIM-REFERENCE"}
    ]
    projection = project_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert projection.pods[0].features["resource_claims"] == "present"
    assert "SENSITIVE-CLAIM-REFERENCE" not in projection.model_dump_json()


def test_scheduling_diagnostics_separate_unsupported_shapes_from_unknown_evidence() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    original = json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True)
    diagnostics = diagnose_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    pod = next(item for item in diagnostics.pods if item.pod_uid == pods[0]["metadata"]["uid"])
    assert "host_ports" in pod.unsupported_features
    assert "volumes" in pod.unknown_features
    assert pod.status == "unsupported"
    assert diagnostics.nodes[0].unknown_conditions == [
        "DiskPressure",
        "MemoryPressure",
        "NetworkUnavailable",
        "PIDPressure",
    ]
    assert diagnostics.fit_status == "blocked"
    assert diagnostics.admission_blockers == (
        "producer_completeness_unverified",
        "scheduler_configuration_unverified",
    )
    assert diagnostics.projection.audit.collection == snapshot.collection
    assert "SENSITIVE-" not in diagnostics.model_dump_json()
    assert json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True) == original


def test_scheduling_diagnostics_missing_features_never_become_supported() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    for pod in pods:
        pod["spec"].pop("os", None)
        pod["spec"].pop("schedulerName", None)
    diagnostics = diagnose_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert all("pod_os_unknown" in item.issues for item in diagnostics.pods)
    assert all("scheduler_name_unknown" in item.issues for item in diagnostics.pods)
    assert all(item.status != "within_initial_shape" for item in diagnostics.pods)
    assert diagnostics.fit_status == "blocked"


def simple_native_scheduling_inputs() -> tuple[
    KubernetesMetadataSnapshot, list[dict[str, Any]], list[dict[str, Any]]
]:
    snapshot, pods, nodes = native_scheduling_inputs()
    for pod in pods:
        pod["spec"].update(
            os={"name": "linux"},
            schedulerName="default-scheduler",
            hostNetwork=False,
            volumes=[],
            resourceClaims=[],
            schedulingGates=[],
            nodeSelector={},
            affinity={},
            topologySpreadConstraints=[],
            tolerations=[],
            priorityClassName="",
            runtimeClassName="",
            resources={},
            initContainers=[],
            overhead={},
        )
        for container in pod["spec"]["containers"]:
            container["ports"] = []
            container["resources"]["limits"] = {}
    nodes[0]["metadata"]["labels"].update(
        {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64"}
    )
    nodes[0]["spec"].update(taints=[], unschedulable=False)
    nodes[0]["status"]["conditions"] = [
        {"type": condition, "status": "True" if condition == "Ready" else "False"}
        for condition in [
            "Ready",
            "MemoryPressure",
            "DiskPressure",
            "PIDPressure",
            "NetworkUnavailable",
        ]
    ]
    for row in [*pods, *nodes]:
        projected = project_metadata("v1/pods" if row["kind"] == "Pod" else "v1/nodes", row)
        index = next(
            index for index, item in enumerate(snapshot.resources) if item.uid == projected.uid
        )
        snapshot.resources[index] = projected
    return snapshot, pods, nodes


def test_scheduling_calculation_preserves_competitors_and_adds_back_candidate_once() -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    original = json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True)
    result = calculate_scheduling_constraints(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    pair = next(item for item in result.pairs if item.pod_uid == "pod-uid")
    assert pair.status == "satisfied"
    assert pair.cpu_available_mcpu == 1500
    assert pair.cpu_required_mcpu == 250
    assert pair.pod_slots_available == 19
    assert pair.pod_slots_required == 1
    assert result.fit_status == "blocked"
    assert result.source_admission == "unverified"
    assert result.scheduler_admission == "unverified"
    assert json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True) == original


@pytest.mark.parametrize(
    ("cpu", "memory", "slots", "status"),
    [
        ("750m", "384Mi", "2", "satisfied"),
        ("749m", "384Mi", "2", "unsatisfied"),
        ("750m", "383Mi", "2", "unsatisfied"),
        ("750m", "384Mi", "1", "unsatisfied"),
    ],
)
def test_scheduling_calculation_exact_resource_boundaries(
    cpu: str, memory: str, slots: str, status: str
) -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    nodes[0]["status"]["allocatable"].update(cpu=cpu, memory=memory, pods=slots)
    projected = project_metadata("v1/nodes", nodes[0])
    snapshot.resources = [
        projected if item.uid == projected.uid else item for item in snapshot.resources
    ]
    result = calculate_scheduling_constraints(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert next(item for item in result.pairs if item.pod_uid == "pod-uid").status == status


@pytest.mark.parametrize("problem", ["memory", "system-cpu", "stale", "pending", "shape", "group"])
def test_scheduling_calculation_never_bypasses_missing_or_unsupported_evidence(
    problem: str,
) -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    if problem == "stale":
        snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3601)
    elif problem == "memory":
        pods[0]["spec"]["containers"][0]["resources"]["requests"].pop("memory")
    elif problem == "system-cpu":
        pods[1]["spec"]["containers"][0]["resources"]["requests"].pop("cpu")
    elif problem == "pending":
        pods[1]["spec"].pop("nodeName")
        pods[1]["status"]["phase"] = "Pending"
    elif problem == "group":
        pods[0]["spec"]["schedulingGroup"] = {"podGroupName": "synthetic-group"}
    else:
        pods[0]["spec"]["volumes"] = [{"name": "synthetic", "emptyDir": {}}]
    for row in pods:
        projected = project_metadata("v1/pods", row)
        snapshot.resources = [
            projected if item.uid == projected.uid else item for item in snapshot.resources
        ]
    result = calculate_scheduling_constraints(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    pair = next(item for item in result.pairs if item.pod_uid == "pod-uid")
    assert pair.status == "blocked"
    assert pair.issues
    assert result.fit_status == "blocked"
    if problem == "memory":
        assert pair.cpu_available_mcpu == 1500
        assert pair.memory_available_mib is None


def test_scheduling_calculation_malformed_resize_state_is_unknown_not_ignored() -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    pods[0]["status"]["containerStatuses"] = None
    projected = project_metadata("v1/pods", pods[0])
    snapshot.resources = [
        projected if item.uid == projected.uid else item for item in snapshot.resources
    ]
    result = calculate_scheduling_constraints(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert all(item.status == "blocked" for item in result.pairs)


def test_scheduling_calculation_reports_scattering_without_aggregate_placement() -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    other = json.loads(json.dumps(nodes[0]))
    other["metadata"].update(uid="synthetic-other-node", name="synthetic-other-node")
    nodes[0]["status"]["allocatable"].update(cpu="500m", memory="1Gi")
    other["status"]["allocatable"].update(cpu="2", memory="1Mi")
    nodes.append(other)
    snapshot.resources = [item for item in snapshot.resources if item.kind != "Node"] + [
        project_metadata("v1/nodes", row) for row in nodes
    ]
    result = calculate_scheduling_constraints(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    candidate = next(item for item in result.fragmentation if item.pod_uid == "pod-uid")
    assert candidate.status == "scattered_across_nodes"
    assert result.simultaneous_placement == "not_calculated"
    assert result.removable_nodes == "not_calculated"
    assert result.fit_status == "blocked"


def test_scheduling_diagnostics_simple_shape_does_not_establish_fit_or_refresh_clocks() -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    diagnostics = diagnose_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert all(item.status == "within_initial_shape" for item in diagnostics.pods)
    assert diagnostics.nodes[0].status == "within_initial_shape"
    assert diagnostics.fit_status == diagnostics.projection.audit.fit_status == "blocked"
    assert diagnostics.projection.audit.nodes[0].observed_cpu_request_mcpu == 750
    assert diagnostics.projection.audit.collection == snapshot.collection
    assert (
        SchedulingShapeDiagnostics.model_validate_json(diagnostics.model_dump_json()) == diagnostics
    )
    payload = diagnostics.model_dump(mode="json")
    payload["fit_status"] = "satisfied"
    with pytest.raises(ValueError):
        SchedulingShapeDiagnostics.model_validate(payload)
    payload["fit_status"] = "blocked"
    payload["admission_blockers"] = []
    with pytest.raises(ValueError):
        SchedulingShapeDiagnostics.model_validate(payload)


@pytest.mark.parametrize("state", ["True", "Unknown", None, "invalid"])
def test_scheduling_diagnostics_node_pressure_and_missing_conditions(state: str | None) -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    conditions = nodes[0]["status"]["conditions"]
    conditions[:] = [item for item in conditions if item["type"] != "MemoryPressure"]
    if state is not None:
        conditions.append({"type": "MemoryPressure", "status": state})
    diagnostics = diagnose_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    node = diagnostics.nodes[0]
    if state == "True":
        assert node.status == "unsupported"
        assert node.unsuitable_conditions == ["MemoryPressure"]
    else:
        assert node.status == "unknown"
        assert node.unknown_conditions == ["MemoryPressure"]


@pytest.mark.parametrize(
    ("field", "value", "feature"),
    [
        ("hostNetwork", True, "host_network"),
        ("resourceClaims", [{"name": "SENSITIVE-CLAIM"}], "resource_claims"),
        ("schedulingGates", [{"name": "SENSITIVE-GATE"}], "scheduling_gates"),
    ],
)
def test_scheduling_diagnostics_present_features_are_not_ignored(
    field: str, value: Any, feature: str
) -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    pods[0]["spec"][field] = value
    diagnostics = diagnose_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    pod = next(item for item in diagnostics.pods if item.pod_uid == pods[0]["metadata"]["uid"])
    assert pod.status == "unsupported"
    assert pod.unsupported_features == [feature]
    assert "SENSITIVE-" not in diagnostics.model_dump_json()


@pytest.mark.parametrize("defect", ["partial", "stale", "cpu-gap", "memory-gap"])
def test_scheduling_diagnostics_simple_shapes_cannot_clear_reservation_gaps(defect: str) -> None:
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    if defect == "partial":
        snapshot.collection.status = CollectionStatus.PARTIAL
        snapshot.collection.missing_fields.append("synthetic-gap")
    elif defect == "stale":
        snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3601)
    else:
        resource = "cpu" if defect == "cpu-gap" else "memory"
        pods[0]["spec"]["containers"][0]["resources"]["requests"].pop(resource)
        projected = project_metadata("v1/pods", pods[0])
        index = next(
            index for index, item in enumerate(snapshot.resources) if item.uid == projected.uid
        )
        snapshot.resources[index] = projected
    diagnostics = diagnose_scheduling_shapes(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert all(item.status == "within_initial_shape" for item in diagnostics.pods)
    audit = diagnostics.projection.audit
    assert audit.nodes[0].issues
    assert audit.fit_status == diagnostics.fit_status == "blocked"
    if defect == "memory-gap":
        assert audit.nodes[0].observed_cpu_request_mcpu == 750
        assert audit.nodes[0].observed_memory_request_mib is None
    elif defect == "cpu-gap":
        assert audit.nodes[0].observed_cpu_request_mcpu is None
        assert audit.nodes[0].observed_memory_request_mib == 384


@pytest.mark.parametrize("value", ["synthetic-zone-a", "synthetic-zone-b", None])
def test_placement_review_distinguishes_retained_mismatch_from_unknown_labels(
    value: str | None,
) -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    pod.spec["nodeSelector"] = {"topology.kubernetes.io/zone": "synthetic-zone-a"}
    node = next(item for item in snapshot.resources if item.kind == "Node")
    if value is None:
        node.labels.pop("topology.kubernetes.io/zone", None)
    else:
        node.labels["topology.kubernetes.io/zone"] = value
    original = snapshot.model_dump_json()
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    pair = next(item for item in review.pairs if item.pod_uid == pod.uid)
    expected = (
        "unknown" if value is None else "matched" if value == "synthetic-zone-a" else "excluded"
    )
    assert pair.constraints["node_selector"] == expected
    assert pair.status == (
        "unknown"
        if value is None
        else "no_observed_exclusion"
        if value == "synthetic-zone-a"
        else "excluded_by_observed_constraint"
    )
    assert review.fit_status == "blocked"
    assert review.audit.collection == snapshot.collection
    assert snapshot.model_dump_json() == original


def test_placement_review_rejects_pair_budget_without_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import scheduling as module

    snapshot, _, _ = simple_native_scheduling_inputs()
    monkeypatch.setattr(module, "MAXIMUM_PLACEMENT_PAIRS", 1)
    with pytest.raises(ValueError, match="pair budget"):
        review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)


@pytest.mark.parametrize(
    ("operator", "values", "label", "expected"),
    [
        ("In", ["3"], "3", "matched"),
        ("NotIn", ["3"], "3", "excluded"),
        ("Exists", [], "3", "matched"),
        ("DoesNotExist", [], "3", "excluded"),
        ("DoesNotExist", [], None, "unknown"),
        ("In", ["3"], None, "unknown"),
        ("Gt", ["2"], "3", "matched"),
        ("Gt", ["3"], "3", "excluded"),
        ("Lt", ["4"], "3", "matched"),
        ("Gt", ["-1"], "0", "matched"),
        ("Gt", ["1_000"], "3", "unknown"),
        ("Gt", ["2"], "unparseable", "unknown"),
        ("Lt", [str(2**63)], "3", "unknown"),
        ("In", [], "3", "unknown"),
        ("Unsupported", [], "3", "unknown"),
    ],
)
def test_placement_review_required_affinity_uses_exact_three_valued_requirements(
    operator: str,
    values: list[str],
    label: str | None,
    expected: str,
) -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    pod.spec["affinity"] = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "topology.kubernetes.io/zone",
                                "operator": operator,
                                "values": values,
                            }
                        ]
                    }
                ]
            }
        }
    }
    node = next(item for item in snapshot.resources if item.kind == "Node")
    if label is not None:
        node.labels["topology.kubernetes.io/zone"] = label
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    pair = next(item for item in review.pairs if item.pod_uid == pod.uid)
    assert pair.constraints["required_node_affinity"] == expected
    assert review.fit_status == "blocked"


@pytest.mark.parametrize(
    "shape", ["empty-terms", "empty-term", "or-match", "or-unknown", "and-mismatch", "node-name"]
)
def test_placement_review_affinity_combines_terms_and_requirements(shape: str) -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    node = next(item for item in snapshot.resources if item.kind == "Node")
    node.labels["topology.kubernetes.io/zone"] = "synthetic-zone"
    match = {"key": "topology.kubernetes.io/zone", "operator": "In", "values": ["synthetic-zone"]}
    mismatch = match | {"values": ["synthetic-other-zone"]}
    unknown = match | {"key": "unretained.example/label"}
    terms: list[dict[str, Any]] = []
    expected = "excluded"
    if shape == "empty-term":
        terms = [{}]
    elif shape == "or-match":
        terms = [{"matchExpressions": [unknown]}, {"matchExpressions": [match]}]
        expected = "matched"
    elif shape == "or-unknown":
        terms = [{"matchExpressions": [unknown]}, {"matchExpressions": [mismatch]}]
        expected = "unknown"
    elif shape == "and-mismatch":
        terms = [{"matchExpressions": [unknown, mismatch]}]
    elif shape == "node-name":
        terms = [
            {"matchFields": [{"key": "metadata.name", "operator": "In", "values": [node.name]}]}
        ]
        expected = "matched"
    pod.spec["affinity"] = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": terms}
        }
    }
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert (
        next(item for item in review.pairs if item.pod_uid == pod.uid).constraints[
            "required_node_affinity"
        ]
        == expected
    )


@pytest.mark.parametrize(
    "shape",
    [
        "none",
        "equal",
        "exists",
        "wildcard",
        "wrong-value",
        "missing-operator",
        "soft",
        "no-execute",
    ],
)
def test_placement_review_taints_require_explicit_supported_tolerations(shape: str) -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    node = next(item for item in snapshot.resources if item.kind == "Node")
    node.spec["taints"] = [{"key": "dedicated", "value": "synthetic", "effect": "NoSchedule"}]
    toleration = {
        "key": "dedicated",
        "value": "synthetic",
        "effect": "NoSchedule",
        "operator": "Equal",
    }
    expected = "matched"
    if shape == "none":
        expected = "excluded"
    elif shape == "exists":
        toleration.update(operator="Exists", value="")
    elif shape == "wildcard":
        toleration.update(key="", operator="Exists", value="", effect="")
    elif shape == "wrong-value":
        toleration["value"] = "other"
        expected = "excluded"
    elif shape == "missing-operator":
        toleration.pop("operator")
        expected = "unknown"
    elif shape == "soft":
        node.spec["taints"][0]["effect"] = "PreferNoSchedule"
    elif shape == "no-execute":
        node.spec["taints"][0]["effect"] = "NoExecute"
        toleration["effect"] = "NoExecute"
        toleration["tolerationSeconds"] = 0
    if shape not in {"none", "soft"}:
        pod.spec["tolerations"] = [toleration]
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert (
        next(item for item in review.pairs if item.pod_uid == pod.uid).constraints["hard_taints"]
        == expected
    )
    assert "disruption_feasibility" in review.unassessed_dimensions


def test_placement_review_cordon_respects_explicit_unschedulable_toleration() -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    node = next(item for item in snapshot.resources if item.kind == "Node")
    node.spec["unschedulable"] = True
    pod.spec["tolerations"] = [
        {"key": "node.kubernetes.io/unschedulable", "operator": "Exists", "effect": "NoSchedule"}
    ]
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    pairs = {item.pod_uid: item for item in review.pairs}
    assert pairs[pod.uid].constraints["cordon"] == "matched"
    assert pairs["synthetic-system-pod-uid"].constraints["cordon"] == "excluded"


@pytest.mark.parametrize("problem", ["partial", "stale", "future", "missing-list", "missing-clock"])
def test_placement_review_source_gaps_cannot_become_exclusions_or_matches(problem: str) -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    if problem == "partial":
        snapshot.collection.status = CollectionStatus.PARTIAL
        snapshot.collection.missing_fields.append("synthetic-incomplete-list")
    elif problem == "stale":
        snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3601)
    elif problem == "future":
        snapshot.generated_at = AS_OF + timedelta(seconds=1)
    elif problem == "missing-list":
        snapshot.resource_versions.pop("v1/nodes")
    else:
        snapshot.collection.source_observed_at = None
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert review.pairs and all(item.status == "unknown" and item.issues for item in review.pairs)
    assert all(set(item.constraints.values()) == {"unknown"} for item in review.pairs)
    assert review.audit.collection == snapshot.collection


def test_placement_review_does_not_infer_pinning_from_current_node_assignment() -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    node = next(item for item in snapshot.resources if item.kind == "Node")
    other = KubernetesObjectMetadata.model_validate(node.model_dump())
    other.uid, other.name = "synthetic-second-node-uid", "synthetic-second-node"
    snapshot.resources.append(other)
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert len(review.pairs) == 4
    assert all(item.status == "no_observed_exclusion" for item in review.pairs)
    assert review.fit_status == "blocked"
    snapshot.resources.reverse()
    reordered = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert reordered.pairs == review.pairs
    assert reordered.audit.metadata_digest != review.audit.metadata_digest


def test_placement_review_rejects_excessive_constraint_work_before_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import scheduling as module

    snapshot, _, _ = simple_native_scheduling_inputs()
    monkeypatch.setattr(module, "MAXIMUM_PLACEMENT_WORK", 1)
    with pytest.raises(ValueError, match="work budget"):
        review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)


def test_placement_review_pending_assignment_does_not_erase_independent_constraint_facts() -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    pod = next(item for item in snapshot.resources if item.uid == "pod-uid")
    pod.spec.pop("nodeName")
    pod.status["phase"] = "Pending"
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert review.audit.pending_pod_uids == [pod.uid]
    assert "unresolved_pod_assignment" in review.audit.issues
    assert all(item.status == "no_observed_exclusion" for item in review.pairs)
    assert review.audit.nodes[0].observed_cpu_request_mcpu is None
    assert review.fit_status == "blocked"


def test_placement_review_cli_is_offline_scoped_and_exclusive(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from aks_fleet_efficiency.cli import app

    snapshot, _, _ = simple_native_scheduling_inputs()
    source = tmp_path / "fragments.json"
    bundle = json.loads(
        (Path(__file__).resolve().parents[1] / "examples/fixtures/pool-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    bundle["kubernetes"] = [snapshot.model_dump(mode="json")]
    source.write_text(json.dumps(bundle), encoding="utf-8")
    original = source.read_bytes()
    output = tmp_path / "placement.json"
    arguments = [
        "review-placement",
        "--fragments",
        str(source),
        "--tenant",
        SUBSCRIPTION,
        "--cluster",
        CLUSTER,
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fit_status"] == "blocked"
    assert len(saved["pairs"]) == 2
    assert saved["audit"]["cluster_resource_id"] == CLUSTER
    assert source.read_bytes() == original
    output.write_text("SYNTHETIC-EXISTING-OUTPUT", encoding="utf-8")
    assert CliRunner().invoke(app, arguments).exit_code != 0
    assert output.read_text(encoding="utf-8") == "SYNTHETIC-EXISTING-OUTPUT"


@pytest.mark.parametrize("problem", ["tenant", "cluster", "duplicate", "sensitive-input"])
def test_placement_review_cli_refuses_foreign_or_invalid_input_without_echo(
    tmp_path: Path,
    problem: str,
) -> None:
    from typer.testing import CliRunner

    from aks_fleet_efficiency.cli import app

    snapshot, _, _ = simple_native_scheduling_inputs()
    records = [snapshot.model_dump(mode="json")]
    if problem == "duplicate":
        records *= 2
    elif problem == "sensitive-input":
        records[0]["resources"][0]["spec"] = {"SENSITIVE-UNAPPROVED-BODY": "SENSITIVE-INPUT-VALUE"}
    source = tmp_path / "fragments.json"
    bundle = json.loads(
        (Path(__file__).resolve().parents[1] / "examples/fixtures/pool-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    bundle["kubernetes"] = records
    source.write_text(json.dumps(bundle), encoding="utf-8")
    output = tmp_path / "placement.json"
    result = CliRunner().invoke(
        app,
        [
            "review-placement",
            "--fragments",
            str(source),
            "--tenant",
            "foreign-tenant" if problem == "tenant" else SUBSCRIPTION,
            "--cluster",
            CLUSTER + "-foreign" if problem == "cluster" else CLUSTER,
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code != 0
    assert not output.exists()
    assert "SENSITIVE-" not in result.output


def test_placement_review_documented_fixture_exercises_nonempty_current_pairs() -> None:
    from aks_fleet_efficiency.assessment import AssessmentFragments

    path = (
        Path(__file__).resolve().parents[1] / "examples/fixtures/daemonset-overhead-assessment.json"
    )
    fragments = AssessmentFragments.model_validate_json(path.read_text(encoding="utf-8"))
    review = review_scheduling_placement(
        fragments.kubernetes[0], as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert len(review.pairs) == 4
    assert len({item.pod_uid for item in review.pairs}) == 2
    assert len({item.node_uid for item in review.pairs}) == 2
    assert review.fit_status == "blocked"


def test_placement_review_serialization_never_admits_fit_or_clears_source_blockers() -> None:
    snapshot, _, _ = simple_native_scheduling_inputs()
    review = review_scheduling_placement(snapshot, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert SchedulingPlacementReview.model_validate_json(review.model_dump_json()) == review
    payload = review.model_dump(mode="json")
    payload["fit_status"] = "satisfied"
    with pytest.raises(ValueError):
        SchedulingPlacementReview.model_validate(payload)
    payload["fit_status"] = "blocked"
    payload["admission_blockers"] = []
    with pytest.raises(ValueError):
        SchedulingPlacementReview.model_validate(payload)


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("true", "true"),
        ("false", "false"),
        ("True", "unknown"),
        (True, "unknown"),
        (None, "unknown"),
        ("SENSITIVE-INVALID-VALUE", "unknown"),
    ],
)
def test_disruption_protection_projection_is_exact_and_never_copies_annotation_text(
    annotation: Any,
    expected: str,
) -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    pods[0]["metadata"]["annotations"] = {
        "karpenter.sh/do-not-disrupt": annotation,
        "SENSITIVE-UNAPPROVED-KEY": "SENSITIVE-UNAPPROVED-VALUE",
    }
    original = json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True)
    projection = project_disruption_protection(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    observation = next(
        item for item in projection.observations if item.uid == pods[0]["metadata"]["uid"]
    )
    assert observation.state == expected
    assert observation.effectiveness == "unknown"
    assert projection.audit.collection == snapshot.collection
    assert "SENSITIVE-" not in projection.model_dump_json()
    assert json.dumps([snapshot.model_dump(mode="json"), pods, nodes], sort_keys=True) == original


def test_disruption_protection_absence_requires_explicit_observed_annotation_map() -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    pods[0]["metadata"]["annotations"] = {}
    nodes[0]["metadata"]["annotations"] = {"karpenter.sh/do-not-disrupt": "true"}
    projection = project_disruption_protection(
        snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    states = {item.uid: item.state for item in projection.observations}
    assert states[pods[0]["metadata"]["uid"]] == "absent"
    assert states[pods[1]["metadata"]["uid"]] == "unknown"
    assert states[nodes[0]["metadata"]["uid"]] == "true"


@pytest.mark.parametrize("problem", ["missing", "duplicate", "substituted"])
def test_disruption_protection_rejects_foreign_or_incomplete_rosters(problem: str) -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    if problem == "missing":
        pods.pop()
    elif problem == "duplicate":
        pods.append(pods[0])
    else:
        pods[0]["metadata"]["uid"] = "foreign-pod-uid"
    with pytest.raises(ValueError):
        project_disruption_protection(
            snapshot, pods=pods, nodes=nodes, as_of=AS_OF, maximum_source_age_seconds=3600
        )


def scheduling_reader_input() -> FakeKubernetesReader:
    snapshot, pods, nodes = native_scheduling_inputs()
    reader = FakeKubernetesReader()
    for resource in reader.rows:
        definition = kubernetes_module.RESOURCE_CATALOG[resource]
        originals = [
            item
            for item in snapshot.resources
            if item.kind == definition.kind and item.api_version == resource.rsplit("/", 1)[0]
        ]
        reader.rows[resource] = [
            {
                "apiVersion": item.api_version,
                "kind": item.kind,
                "metadata": {
                    "name": item.name,
                    "namespace": item.namespace,
                    "uid": item.uid,
                    "labels": item.labels,
                    "ownerReferences": item.owner_references,
                },
                "spec": item.spec,
                "status": item.status,
            }
            for item in originals
        ]
    reader.rows["v1/pods"] = pods
    reader.rows["v1/nodes"] = nodes
    nodes[0]["metadata"]["annotations"] = {"karpenter.sh/do-not-disrupt": "true"}
    return reader


def test_scheduling_producer_records_execution_without_expanding_default_metadata() -> None:
    reader = scheduling_reader_input()
    baseline = collect(reader).model_dump_json()
    producer = KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=reader,
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    )
    result = producer.collect_scheduling(as_of=AS_OF, maximum_source_age_seconds=3600)
    assert result.mapping_reference == "kubernetes-core-v1@v1.36.0"
    assert result.fit_status == "blocked"
    assert result.execution_binding == "executed_injected_reader_unverified_source"
    assert result.metadata.model_dump_json() == baseline
    assert len(result.observations) == 3
    pod = next(item for item in result.observations if item.uid == "pod-uid")
    assert pod.shape.features["host_ports"] == "present"
    assert len(pod.approved_projection_digest) == 64
    node = next(item for item in result.observations if item.kind == "Node")
    assert node.protection.state == "true"
    assert {item.resource for item in result.lists} == {"v1/namespaces", "v1/nodes", "v1/pods"}
    assert all(item.pagination_complete and item.successful_pages == 1 for item in result.lists)
    assert all(item.source_observed_at == AS_OF for item in result.lists)
    assert "SENSITIVE-" not in result.model_dump_json()
    assert "karpenter.sh/do-not-disrupt" not in baseline
    assert collect(reader).model_dump_json() == baseline


@pytest.mark.parametrize(
    "problem",
    [
        "none",
        "version-change",
        "repeated-token",
        "page-limit",
        "missing-clock",
        "retry",
        "forbidden",
        "duplicate",
    ],
)
def test_scheduling_producer_records_pagination_and_does_not_salvage_rejected_lists(
    problem: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = scheduling_reader_input()
    original_page = reader.list_page
    attempts = 0

    def paged(resource: str, *, continue_token: str | None, page_size: int) -> KubernetesPage:
        nonlocal attempts
        if resource != "v1/pods":
            return original_page(resource, continue_token=continue_token, page_size=page_size)
        attempts += 1
        reader.calls.append((resource, continue_token))
        if problem == "forbidden":
            raise KubernetesReadError("forbidden")
        if problem == "retry" and attempts == 1:
            raise KubernetesReadError("throttled", retry_after_seconds=1)
        first = continue_token is None
        index = 0 if first or problem == "duplicate" else 1
        return KubernetesPage(
            items=[reader.rows[resource][index]],
            resource_version="changed-version"
            if not first and problem == "version-change"
            else "synthetic-pod-list-version",
            continue_token="synthetic-next" if first or problem == "repeated-token" else None,
            observed_at=None
            if first and problem == "missing-clock"
            else AS_OF - timedelta(seconds=60 if first else 0),
        )

    monkeypatch.setattr(reader, "list_page", paged)
    delays: list[float] = []
    result = KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=reader,
        clock=lambda: AS_OF,
        sleep=delays.append,
        max_pages=1 if problem == "page-limit" else 3,
    ).collect_scheduling(as_of=AS_OF)
    listing = next(item for item in result.lists if item.resource == "v1/pods")
    accepted = problem in {"none", "missing-clock", "retry"}
    assert listing.pagination_complete is accepted
    pods = [item for item in result.observations if item.kind == "Pod"]
    assert len(pods) == (2 if accepted else 0)
    assert result.fit_status == "blocked"
    if accepted:
        assert listing.successful_pages == 2
        assert listing.observed_objects == 2
        assert listing.source_observed_at == (
            None if problem == "missing-clock" else AS_OF - timedelta(seconds=60)
        )
    else:
        assert result.metadata.collection.status == CollectionStatus.PARTIAL
        assert "v1/pods" in result.metadata.collection.missing_fields
    if problem == "retry":
        assert listing.failed_attempts == result.metadata.collection.retry_count == 1
        assert delays == [1]
    assert "synthetic-next" not in result.model_dump_json()


@pytest.mark.parametrize("field", ["MAXIMUM_SCHEDULING_OBJECTS", "MAXIMUM_SCHEDULING_BYTES"])
def test_scheduling_producer_refuses_exceeded_capture_budgets(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kubernetes_module, field, 1)
    reader = scheduling_reader_input()
    with pytest.raises(ValueError):
        KubernetesMetadataCollector(
            profile(),
            cluster_resource_id=CLUSTER,
            expected_cluster_uid=CLUSTER_UID,
            reader=reader,
            clock=lambda: AS_OF,
            sleep=lambda _: None,
        ).collect_scheduling(as_of=AS_OF)


def test_scheduling_producer_verifies_fingerprint_before_reading_other_objects() -> None:
    reader = scheduling_reader_input()
    with pytest.raises(ValueError):
        KubernetesMetadataCollector(
            profile(),
            cluster_resource_id=CLUSTER,
            expected_cluster_uid="foreign-fingerprint",
            reader=reader,
            clock=lambda: AS_OF,
            sleep=lambda _: None,
        ).collect_scheduling(as_of=AS_OF)
    assert reader.calls == [("v1/namespaces", None)]


@pytest.mark.parametrize("problem", ["identity", "digest", "audit-scope", "list-version", "fit"])
def test_scheduling_producer_contract_rejects_inconsistent_saved_bindings(problem: str) -> None:
    result = KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=scheduling_reader_input(),
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    ).collect_scheduling(as_of=AS_OF)
    assert SchedulingSourceCollection.model_validate_json(result.model_dump_json()) == result
    saved = result.model_dump(mode="json")
    if problem == "identity":
        saved["observations"][0]["uid"] = "foreign-object"
    elif problem == "digest":
        saved["observations"][0]["approved_projection_digest"] = "0" * 64
    elif problem == "audit-scope":
        saved["audit"]["cluster_resource_id"] += "-foreign"
    elif problem == "list-version":
        saved["lists"][0]["resource_version"] = "foreign-version"
    else:
        saved["fit_status"] = "satisfied"
    with pytest.raises(ValueError):
        SchedulingSourceCollection.model_validate(saved)


def test_scheduling_sdk_reader_captures_facts_before_returning_sanitized_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient()
    row = scheduling_reader_input().rows["v1/pods"][0]
    row["metadata"]["annotations"] = {
        "karpenter.sh/do-not-disrupt": "true",
        "private": "SENSITIVE-ANNOTATION",
    }
    client.responses["/api/v1/pods"] = {
        "apiVersion": "v1",
        "kind": "PodList",
        "metadata": {"resourceVersion": "synthetic-list-version"},
        "items": [row],
    }
    default = sdk_reader(monkeypatch, client)
    old_page = default.list_page("v1/pods", continue_token=None, page_size=100)
    opted_in = kubernetes_module.SchedulingKubernetesSdkReader(
        profile(),
        cluster_resource_id=CLUSTER,
        api_client=client,
    )
    page = opted_in.list_page("v1/pods", continue_token=None, page_size=100)
    assert old_page.scheduling_observations is None
    assert page.items == old_page.items
    assert page.scheduling_observations is not None
    assert page.scheduling_observations[0].shape.features["host_ports"] == "present"
    assert page.scheduling_observations[0].protection.state == "true"
    assert "SENSITIVE-" not in json.dumps(page.items)
    assert "SENSITIVE-" not in page.scheduling_observations[0].model_dump_json()
    assert all(method == "GET" for _, method, _ in client.calls)
    assert client.last_response is not None and client.last_response.closed


def test_scheduling_producer_replays_complete_sdk_transport_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = scheduling_reader_input()
    client = FakeApiClient()
    versions = sorted({resource.rsplit("/", 1)[0] for resource in source.rows})
    groups: dict[str, list[dict[str, str]]] = {}
    for version in versions:
        if version != "v1":
            group, group_version = version.split("/", 1)
            groups.setdefault(group, []).append({"version": group_version})
        discovery_path = "/api/v1" if version == "v1" else f"/apis/{version}"
        client.responses[discovery_path] = {
            "resources": [
                {
                    "name": resource.rsplit("/", 1)[1],
                    "kind": kubernetes_module.RESOURCE_CATALOG[resource].kind,
                    "namespaced": kubernetes_module.RESOURCE_CATALOG[resource].namespaced,
                    "verbs": ["list"],
                }
                for resource in source.rows
                if resource.rsplit("/", 1)[0] == version
            ]
        }
    client.responses["/apis"] = {
        "groups": [{"name": name, "versions": items} for name, items in sorted(groups.items())]
    }
    for resource, items in source.rows.items():
        definition = kubernetes_module.RESOURCE_CATALOG[resource]
        path = f"/api/{resource}" if resource.startswith("v1/") else f"/apis/{resource}"
        client.responses[path] = {
            "apiVersion": resource.rsplit("/", 1)[0],
            "kind": f"{definition.kind}List",
            "metadata": {"resourceVersion": f"synthetic-{definition.kind}-version"},
            "items": items,
        }
    sdk_reader(monkeypatch, client)
    reader = kubernetes_module.SchedulingKubernetesSdkReader(
        profile(),
        cluster_resource_id=CLUSTER,
        api_client=client,
    )
    result = KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=reader,
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    ).collect_scheduling(as_of=AS_OF)
    assert result.metadata.collection.status == CollectionStatus.COMPLETE
    assert len(result.observations) == 3
    assert all(item.pagination_complete for item in result.lists)
    assert (
        next(item for item in result.observations if item.kind == "Node").protection.state == "true"
    )
    assert result.fit_status == "blocked" and result.scheduler_admission == "unverified"
    assert "SENSITIVE-" not in result.model_dump_json()
    assert all(method == "GET" for _, method, _ in client.calls)


@pytest.mark.parametrize(
    "annotations", [None, [], "SENSITIVE-NONMAP", {"other": "SENSITIVE-OTHER"}]
)
def test_disruption_protection_does_not_infer_old_or_malformed_annotation_values(
    annotations: Any,
) -> None:
    snapshot, pods, nodes = native_scheduling_inputs()
    pods[0]["metadata"]["annotations"] = annotations
    result = project_disruption_protection(
        snapshot,
        pods=pods,
        nodes=nodes,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    item = next(item for item in result.observations if item.uid == pods[0]["metadata"]["uid"])
    assert item.state == ("absent" if isinstance(annotations, dict) else "unknown")
    assert item.effectiveness == "unknown"
    assert "SENSITIVE-" not in result.model_dump_json()


def test_scheduling_producer_normalizes_injected_execution_and_source_clocks_to_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = scheduling_reader_input()
    offset_clock = datetime.fromisoformat("2026-10-29T14:00:00+02:00")
    original_page = reader.list_page

    def offset_page(resource: str, *, continue_token: str | None, page_size: int) -> KubernetesPage:
        return replace(
            original_page(resource, continue_token=continue_token, page_size=page_size),
            observed_at=offset_clock,
        )

    monkeypatch.setattr(reader, "list_page", offset_page)
    result = KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=reader,
        clock=lambda: offset_clock,
        sleep=lambda _: None,
    ).collect_scheduling(as_of=AS_OF)
    for listing in result.lists:
        assert listing.source_observed_at is not None
        for value in (listing.started_at, listing.completed_at, listing.source_observed_at):
            assert value == AS_OF
            assert value.utcoffset() == timedelta(0)


def test_scheduling_producer_refuses_default_sanitizing_sdk_reader_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient()
    reader = sdk_reader(monkeypatch, client)
    with pytest.raises(ValueError, match="opt-in SDK reader"):
        KubernetesMetadataCollector(
            profile(),
            cluster_resource_id=CLUSTER,
            expected_cluster_uid=CLUSTER_UID,
            reader=reader,
            clock=lambda: AS_OF,
            sleep=lambda _: None,
        ).collect_scheduling(as_of=AS_OF)
    assert not client.calls


def daemonset_membership_inputs() -> tuple[
    KubernetesMetadataSnapshot, list[dict[str, Any]], list[dict[str, Any]]
]:
    from aks_fleet_efficiency.assessment import AssessmentFragments

    metadata = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/daemonset-overhead-assessment.json").read_bytes()
    ).kubernetes[0]
    original_nodes = [row for row in metadata.resources if row.kind == "Node"]
    controllers = [row for row in metadata.resources if row.kind == "DaemonSet"]
    nodes = []
    for row in original_nodes:
        row.spec["taints"] = [
            {"key": "node.kubernetes.io/unschedulable", "value": "", "effect": "NoSchedule"}
        ]
        nodes.append(
            {
                "apiVersion": row.api_version,
                "kind": row.kind,
                "metadata": {
                    "name": row.name,
                    "uid": row.uid,
                    "resourceVersion": "synthetic-rv",
                    "labels": row.labels,
                },
                "spec": row.spec,
                "status": row.status,
            }
        )
    native_controllers = [
        {
            "apiVersion": row.api_version,
            "kind": row.kind,
            "metadata": {
                "name": row.name,
                "namespace": row.namespace,
                "uid": row.uid,
                "labels": row.labels,
                "resourceVersion": "synthetic-rv",
                "generation": 1,
            },
            "spec": row.spec
            | {
                "template": {
                    "spec": {
                        "nodeName": "",
                        "nodeSelector": {},
                        "affinity": {},
                        "tolerations": [],
                        "hostNetwork": False,
                        "containers": [
                            {
                                "name": "synthetic",
                                "env": [{"name": "SENSITIVE-ENV", "value": "SENSITIVE-VALUE"}],
                            }
                        ],
                    }
                }
            },
            "status": row.status | {"observedGeneration": 1},
        }
        for row in controllers
    ]
    native_by_uid = {row["metadata"]["uid"]: row for row in native_controllers}
    metadata.resources = [
        project_metadata("apps/v1/daemonsets", native_by_uid[row.uid])
        if row.kind == "DaemonSet"
        else row
        for row in metadata.resources
    ]
    return metadata, native_controllers, nodes


def test_daemonset_membership_models_controller_tolerations_not_scheduler_fit() -> None:
    from aks_fleet_efficiency.daemonsets import review_daemonset_membership

    metadata, native_controllers, nodes = daemonset_membership_inputs()
    original_nodes = [row for row in metadata.resources if row.kind == "Node"]
    controllers = [row for row in metadata.resources if row.kind == "DaemonSet"]
    result = review_daemonset_membership(
        metadata,
        daemonsets=native_controllers,
        nodes=nodes,
        as_of=AS_OF,
        maximum_source_age_seconds=7200,
    )
    assert len(result.comparisons) == len(original_nodes) * len(controllers) > 0
    assert all(row.selection == "selected" for row in result.comparisons)
    assert result.daemonsets[0].modeled_desired_node_uids == sorted(
        row.uid for row in original_nodes
    )
    assert result.desired_membership_admission == "unverified"
    assert result.fit_status == "blocked"
    assert "SENSITIVE" not in result.model_dump_json()


def storage_projection_inputs() -> tuple[
    KubernetesMetadataSnapshot, list[dict[str, Any]], dict[str, Any]
]:
    from aks_fleet_efficiency.assessment import AssessmentFragments

    metadata = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/daemonset-overhead-assessment.json").read_bytes()
    ).kubernetes[0]
    node = next(row for row in metadata.resources if row.kind == "Node")
    namespace = next(
        row for row in metadata.resources if row.kind == "Namespace" and row.name != "kube-system"
    )
    node.labels["topology.kubernetes.io/zone"] = "synthetic-zone"
    receipt = metadata.collection.model_copy(update={"collector": "synthetic-storage"})
    objects: list[dict[str, Any]] = [
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "synthetic-claim",
                "namespace": namespace.name,
                "uid": "synthetic-claim-uid",
                "resourceVersion": "synthetic-rv",
            },
            "spec": {
                "volumeName": "synthetic-volume",
                "storageClassName": "synthetic-class",
                "accessModes": ["ReadWriteOnce"],
                "volumeMode": "Filesystem",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {
                "name": "synthetic-volume",
                "uid": "synthetic-volume-uid",
                "resourceVersion": "synthetic-rv",
            },
            "spec": {
                "claimRef": {
                    "name": "synthetic-claim",
                    "namespace": namespace.name,
                    "uid": "synthetic-claim-uid",
                },
                "storageClassName": "synthetic-class",
                "accessModes": ["ReadWriteOnce"],
                "volumeMode": "Filesystem",
                "csi": {
                    "driver": "synthetic.csi",
                    "volumeHandle": "SENSITIVE-HANDLE",
                    "volumeAttributes": {"sensitive": "SENSITIVE-ATTRIBUTE"},
                    "nodePublishSecretRef": {"name": "SENSITIVE-SECRET"},
                },
                "nodeAffinity": {
                    "required": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "topology.kubernetes.io/zone",
                                        "operator": "In",
                                        "values": ["synthetic-zone"],
                                    }
                                ]
                            }
                        ]
                    }
                },
            },
        },
        {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "StorageClass",
            "metadata": {
                "name": "synthetic-class",
                "uid": "synthetic-class-uid",
                "resourceVersion": "synthetic-rv",
            },
            "provisioner": "synthetic.csi",
            "volumeBindingMode": "WaitForFirstConsumer",
            "allowedTopologies": [],
            "parameters": {"sensitive": "SENSITIVE-PARAMETER"},
            "mountOptions": ["SENSITIVE-MOUNT"],
        },
        {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "CSINode",
            "metadata": {
                "name": node.name,
                "uid": "synthetic-csinode",
                "resourceVersion": "synthetic-rv",
                "ownerReferences": [
                    {"apiVersion": "v1", "kind": "Node", "name": node.name, "uid": node.uid}
                ],
            },
            "spec": {
                "drivers": [
                    {
                        "name": "synthetic.csi",
                        "nodeID": "SENSITIVE-NODE-ID",
                        "allocatable": {"count": 0},
                        "topologyKeys": ["topology.kubernetes.io/zone"],
                    }
                ]
            },
        },
        {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "CSIDriver",
            "metadata": {
                "name": "synthetic.csi",
                "uid": "synthetic-driver",
                "resourceVersion": "synthetic-rv",
            },
            "spec": {
                "attachRequired": True,
                "tokenRequests": [{"audience": "SENSITIVE-AUDIENCE"}],
            },
        },
    ]
    receipts = {
        key: receipt
        for key in [
            "PersistentVolumeClaim",
            "PersistentVolume",
            "StorageClass",
            "CSINode",
            "CSIDriver",
        ]
    }
    return metadata, objects, receipts


def test_storage_projection_binds_claim_uids_and_withholds_full_feasibility() -> None:
    from aks_fleet_efficiency.storage import project_storage_context

    metadata, objects, receipts = storage_projection_inputs()
    node = next(row for row in metadata.resources if row.kind == "Node")
    namespace = next(
        row for row in metadata.resources if row.kind == "Namespace" and row.name != "kube-system"
    )
    original = json.dumps([metadata.model_dump(mode="json"), objects], sort_keys=True)
    result = project_storage_context(
        metadata,
        objects=objects,
        receipts=receipts,
        as_of=AS_OF,
        maximum_source_age_seconds=7200,
    )
    assert result.claims[0].namespace_uid == namespace.uid
    assert result.claims[0].bound_volume_uid == "synthetic-volume-uid"
    assert result.csi_nodes[0].drivers[0].maximum_volumes == 0
    pair = next(row for row in result.comparisons if row.node_uid == node.uid)
    assert pair.bound_volume_topology == "matched"
    assert pair.storage_feasibility == "unknown"
    assert result.fit_status == "blocked"
    assert "SENSITIVE" not in result.model_dump_json()
    assert json.dumps([metadata.model_dump(mode="json"), objects], sort_keys=True) == original


@pytest.mark.parametrize(
    "problem",
    [
        "claim_uid",
        "missing_volume",
        "csi_owner",
        "negative_count",
        "boolean_count",
        "large_count",
        "missing_count",
        "malformed_mode",
        "malformed_topology",
        "stale",
        "partial",
        "missing_receipt",
    ],
)
def test_storage_projection_missing_or_malformed_fields_stay_unknown(problem: str) -> None:
    from aks_fleet_efficiency.storage import project_storage_context

    metadata, objects, receipts = storage_projection_inputs()
    age = 7200
    if problem == "claim_uid":
        objects[1]["spec"]["claimRef"]["uid"] = "synthetic-recreated-claim"
    elif problem == "missing_volume":
        objects.pop(1)
    elif problem == "csi_owner":
        objects[3]["metadata"]["ownerReferences"][0]["uid"] = "synthetic-recreated-node"
    elif problem in {"negative_count", "boolean_count", "large_count", "missing_count"}:
        objects[3]["spec"]["drivers"][0]["allocatable"]["count"] = {
            "negative_count": -1,
            "boolean_count": True,
            "large_count": 2**31,
            "missing_count": None,
        }[problem]
    elif problem == "malformed_mode":
        objects[0]["spec"]["volumeMode"] = {"sensitive": "SENSITIVE-MODE"}
    elif problem == "malformed_topology":
        objects[1]["spec"]["nodeAffinity"]["required"]["nodeSelectorTerms"][0]["matchExpressions"][
            0
        ]["key"] = []
    elif problem == "stale":
        age = 7199
    elif problem == "partial":
        receipts["PersistentVolume"] = receipts["PersistentVolume"].model_copy(
            update={
                "status": CollectionStatus.PARTIAL,
                "missing_fields": ["synthetic-source-gap"],
            }
        )
    else:
        del receipts["PersistentVolume"]
    result = project_storage_context(
        metadata,
        objects=objects,
        receipts=receipts,
        as_of=AS_OF,
        maximum_source_age_seconds=age,
    )
    if problem in {
        "claim_uid",
        "missing_volume",
        "malformed_topology",
        "stale",
        "partial",
        "missing_receipt",
    }:
        assert all(row.bound_volume_topology == "unknown" for row in result.comparisons)
    elif problem == "csi_owner":
        assert result.csi_nodes[0].node_uid is None
    elif problem == "malformed_mode":
        assert result.claims[0].volume_mode is None
    else:
        assert result.csi_nodes[0].drivers[0].maximum_volumes is None
    assert result.fit_status == "blocked"
    assert "SENSITIVE" not in result.model_dump_json()


@pytest.mark.parametrize(
    "problem",
    ["lagging", "unknown_host_network", "missing_version", "stale", "deleting", "unmatched_taint"],
)
def test_daemonset_membership_gaps_do_not_become_admitted_coverage(problem: str) -> None:
    from aks_fleet_efficiency.daemonsets import review_daemonset_membership

    metadata, controllers, nodes = daemonset_membership_inputs()
    age = 7200
    if problem == "lagging":
        controllers[0]["status"]["observedGeneration"] = 0
    elif problem == "unknown_host_network":
        del controllers[0]["spec"]["template"]["spec"]["hostNetwork"]
    elif problem == "missing_version":
        del nodes[0]["metadata"]["resourceVersion"]
    elif problem == "deleting":
        controllers[0]["metadata"]["deletionTimestamp"] = AS_OF.isoformat()
    elif problem == "stale":
        age = 7199
    else:
        nodes[0]["spec"]["taints"] = [
            {"key": "synthetic/isolated", "value": "true", "effect": "NoSchedule"}
        ]
    replacements = {
        row["metadata"]["uid"]: project_metadata("apps/v1/daemonsets", row) for row in controllers
    }
    replacements.update(
        {row["metadata"]["uid"]: project_metadata("v1/nodes", row) for row in nodes}
    )
    metadata.resources = [replacements.get(row.uid, row) for row in metadata.resources]
    result = review_daemonset_membership(
        metadata,
        daemonsets=controllers,
        nodes=nodes,
        as_of=AS_OF,
        maximum_source_age_seconds=age,
    )
    if problem == "unmatched_taint":
        assert any(row.selection == "excluded" for row in result.comparisons)
    else:
        assert result.daemonsets[0].modeled_desired_node_uids is None
    assert result.desired_membership_admission == "unverified"
    assert result.fit_status == "blocked"


@pytest.mark.parametrize("kind", ["storage", "daemonsets"])
def test_native_infrastructure_commands_are_bounded_exclusive_and_redacted(
    tmp_path: Path, kind: str
) -> None:
    from typer.testing import CliRunner

    from aks_fleet_efficiency.assessment import AssessmentFragments
    from aks_fleet_efficiency.cli import app

    if kind == "storage":
        metadata, objects, receipts = storage_projection_inputs()
        native = {
            "objects": objects,
            "receipts": {key: value.model_dump(mode="json") for key, value in receipts.items()},
        }
        command, input_flag = "review-storage", "--native-storage"
    else:
        metadata, controllers, nodes = daemonset_membership_inputs()
        native = {"daemonsets": controllers, "nodes": nodes}
        command, input_flag = "review-daemonsets", "--native-objects"
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/daemonset-overhead-assessment.json").read_bytes()
    )
    fragments.kubernetes = [metadata]
    source = tmp_path / "fragments.json"
    source.write_text(fragments.model_dump_json(), encoding="utf-8")
    native_path = tmp_path / "native.json"
    native_path.write_text(json.dumps(native), encoding="utf-8")
    output = tmp_path / "review.json"
    args = [
        command,
        "--fragments",
        str(source),
        input_flag,
        str(native_path),
        "--tenant",
        metadata.tenant_id,
        "--cluster",
        metadata.cluster_resource_id,
        "--as-of",
        AS_OF.isoformat(),
        "--max-source-age-seconds",
        "7200",
        "--output",
        str(output),
    ]
    runner = CliRunner()
    response = runner.invoke(app, args)
    assert response.exit_code == 0, response.output
    assert json.loads(output.read_text())["fit_status"] == "blocked"
    assert "SENSITIVE" not in output.read_text()
    original = output.read_bytes()
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_bytes() == original
    output.unlink()
    native["SENSITIVE-UNAPPROVED-FIELD"] = "SENSITIVE-TOKEN"
    native_path.write_text(json.dumps(native), encoding="utf-8")
    denied = runner.invoke(app, args)
    assert denied.exit_code == 2 and not output.exists()
    assert "SENSITIVE" not in denied.output


@pytest.mark.parametrize("budget", ["objects", "pairs", "work", "bytes"])
def test_storage_projection_refuses_budget_excess(
    monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    from aks_fleet_efficiency import storage

    metadata, objects, receipts = storage_projection_inputs()
    monkeypatch.setattr(
        storage,
        {
            "objects": "MAXIMUM_STORAGE_OBJECTS",
            "pairs": "MAXIMUM_STORAGE_PAIRS",
            "work": "MAXIMUM_STORAGE_WORK",
            "bytes": "MAXIMUM_STORAGE_BYTES",
        }[budget],
        1,
    )
    with pytest.raises(ValueError, match="budget"):
        storage.project_storage_context(
            metadata,
            objects=objects,
            receipts=receipts,
            as_of=AS_OF,
            maximum_source_age_seconds=7200,
        )


@pytest.mark.parametrize("budget", ["objects", "pairs", "work", "bytes"])
def test_daemonset_membership_refuses_budget_excess(
    monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    from aks_fleet_efficiency import daemonsets

    metadata, controllers, nodes = daemonset_membership_inputs()
    monkeypatch.setattr(
        daemonsets,
        {
            "objects": "MAXIMUM_DAEMONSET_MEMBERSHIP_OBJECTS",
            "pairs": "MAXIMUM_DAEMONSET_MEMBERSHIP_PAIRS",
            "work": "MAXIMUM_DAEMONSET_MEMBERSHIP_WORK",
            "bytes": "MAXIMUM_DAEMONSET_MEMBERSHIP_BYTES",
        }[budget],
        1,
    )
    with pytest.raises(ValueError, match="budget"):
        daemonsets.review_daemonset_membership(
            metadata,
            daemonsets=controllers,
            nodes=nodes,
            as_of=AS_OF,
            maximum_source_age_seconds=7200,
        )


@pytest.mark.parametrize("problem", ["duplicate", "foreign_kind", "foreign_namespace"])
def test_storage_projection_refuses_foreign_or_ambiguous_identities(problem: str) -> None:
    from aks_fleet_efficiency.storage import project_storage_context

    metadata, objects, receipts = storage_projection_inputs()
    if problem == "duplicate":
        objects.append(objects[0])
    elif problem == "foreign_kind":
        objects[0]["kind"] = "Secret"
    else:
        objects[0]["metadata"]["namespace"] = "synthetic-foreign-namespace"
    with pytest.raises(ValueError):
        project_storage_context(
            metadata,
            objects=objects,
            receipts=receipts,
            as_of=AS_OF,
            maximum_source_age_seconds=7200,
        )


def daemonset_status_inputs(
    change: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[KubernetesMetadataSnapshot, list[dict[str, Any]]]:
    reader = FakeKubernetesReader()
    controller = {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {
            **metadata("synthetic-agent", "synthetic-daemonset-uid", "orders"),
            "resourceVersion": "synthetic-daemonset-version",
            "generation": 3,
            "annotations": {"synthetic-private": "SENSITIVE-ANNOTATION"},
        },
        "spec": {},
        "status": {
            "observedGeneration": 3,
            "desiredNumberScheduled": 2,
            "numberReady": 1,
            "conditions": [{"message": "SENSITIVE-STATUS"}],
        },
    }
    if change is not None:
        change(controller)
    reader.rows["apps/v1/daemonsets"] = [controller]
    return collect(reader), [controller]


def test_daemonset_status_projection_is_explicit_and_never_establishes_membership() -> None:
    snapshot, controllers = daemonset_status_inputs()
    original = json.dumps([snapshot.model_dump(mode="json"), controllers], sort_keys=True)
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert result.mapping_reference == "kubernetes-apps-v1@v1.36.0"
    assert result.source_binding == "unverified_supplied_native_objects"
    assert result.tenant_id == snapshot.tenant_id
    assert result.cluster_resource_id == CLUSTER
    assert result.cluster_uid == CLUSTER_UID
    assert result.collection == snapshot.collection
    assert result.metadata_generated_at == snapshot.generated_at
    assert result.evaluated_at == AS_OF
    assert not result.source_issues
    assert len(result.daemonsets) == 1
    observation = result.daemonsets[0]
    assert observation.daemonset_uid == "synthetic-daemonset-uid"
    assert observation.namespace_uid == "namespace-uid"
    assert observation.resource_version == "synthetic-daemonset-version"
    assert observation.metadata_generation == 3
    assert observation.observed_generation == 3
    assert observation.generation_relation == "equal"
    assert observation.desired_number_scheduled == 2
    assert observation.number_ready == 1
    assert observation.desired_node_membership == "unknown"
    assert observation.disruption_feasibility == "unknown"
    assert not observation.issues
    assert "SENSITIVE-" not in result.model_dump_json()
    assert "observedGeneration" not in snapshot.model_dump_json()
    assert json.dumps([snapshot.model_dump(mode="json"), controllers], sort_keys=True) == original


@pytest.mark.parametrize(
    ("observed", "relation", "issues"),
    [
        (0, "lagging", ["controller_generation_lagging"]),
        (2, "lagging", ["controller_generation_lagging"]),
        (3, "equal", []),
        (4, "contradictory", ["observed_generation_ahead"]),
    ],
)
def test_daemonset_status_generation_relation_is_not_reconciliation(
    observed: int, relation: str, issues: list[str]
) -> None:
    snapshot, controllers = daemonset_status_inputs(
        lambda controller: controller["status"].update(observedGeneration=observed)
    )
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    observation = result.daemonsets[0]
    assert observation.generation_relation == relation
    assert observation.issues == issues
    assert observation.desired_node_membership == "unknown"
    assert observation.disruption_feasibility == "unknown"


@pytest.mark.parametrize(
    ("section", "field", "attribute", "issue", "invalid"),
    [
        ("metadata", "generation", "metadata_generation", "metadata_generation_unknown", 0),
        ("metadata", "generation", "metadata_generation", "metadata_generation_unknown", 2**63),
        ("status", "observedGeneration", "observed_generation", "observed_generation_unknown", -1),
        (
            "status",
            "observedGeneration",
            "observed_generation",
            "observed_generation_unknown",
            2**63,
        ),
        (
            "status",
            "desiredNumberScheduled",
            "desired_number_scheduled",
            "desired_count_unknown",
            -1,
        ),
        (
            "status",
            "desiredNumberScheduled",
            "desired_number_scheduled",
            "desired_count_unknown",
            2**31,
        ),
        ("status", "numberReady", "number_ready", "ready_count_unknown", -1),
        ("status", "numberReady", "number_ready", "ready_count_unknown", 2**31),
    ],
)
@pytest.mark.parametrize("value_kind", ["boundary", "missing", "bool", "string", "fraction"])
def test_daemonset_status_fields_fail_closed_independently(
    section: str, field: str, attribute: str, issue: str, invalid: int, value_kind: str
) -> None:
    def change(controller: dict[str, Any]) -> None:
        values = {"boundary": invalid, "bool": True, "string": "SENSITIVE-VALUE", "fraction": 1.5}
        if value_kind == "missing":
            controller[section].pop(field)
        else:
            controller[section][field] = values[value_kind]

    snapshot, controllers = daemonset_status_inputs(change)
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    observation = result.daemonsets[0]
    assert getattr(observation, attribute) is None
    assert issue in observation.issues
    if section == "metadata" or field == "observedGeneration":
        assert observation.generation_relation == "unknown"
        assert observation.desired_number_scheduled == 2
        assert observation.number_ready == 1
    else:
        assert observation.generation_relation == "equal"
    assert "SENSITIVE-" not in result.model_dump_json()


@pytest.mark.parametrize("version", [None, "", " ", True, 3])
def test_daemonset_status_missing_object_version_cannot_bind_generations(version: Any) -> None:
    snapshot, controllers = daemonset_status_inputs(
        lambda controller: controller["metadata"].update(resourceVersion=version)
    )
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert result.daemonsets[0].resource_version is None
    assert result.daemonsets[0].generation_relation == "unknown"
    assert result.daemonsets[0].issues == ["resource_version_unknown"]


def test_daemonset_status_accepts_native_integer_boundaries_without_inventing_coverage() -> None:
    def change(controller: dict[str, Any]) -> None:
        controller["metadata"]["generation"] = 2**63 - 1
        controller["status"].update(
            observedGeneration=2**63 - 1, desiredNumberScheduled=0, numberReady=2**31 - 1
        )

    snapshot, controllers = daemonset_status_inputs(change)
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    observation = result.daemonsets[0]
    assert observation.metadata_generation == observation.observed_generation == 2**63 - 1
    assert observation.generation_relation == "equal"
    assert observation.desired_number_scheduled == 0
    assert observation.number_ready == 2**31 - 1
    assert observation.desired_node_membership == "unknown"


@pytest.mark.parametrize(
    "problem",
    ["missing", "duplicate", "foreign", "changed", "namespace", "fingerprint", "kind", "api"],
)
def test_daemonset_status_refuses_substituted_or_incomplete_rosters(problem: str) -> None:
    snapshot, controllers = daemonset_status_inputs()
    if problem == "missing":
        controllers.clear()
    elif problem == "duplicate":
        controllers.append(controllers[0])
    elif problem == "foreign":
        controllers[0]["metadata"]["uid"] = "SENSITIVE-FOREIGN-UID"
    elif problem == "changed":
        controllers[0]["status"]["desiredNumberScheduled"] = 9
    elif problem == "namespace":
        snapshot.resources = [item for item in snapshot.resources if item.name != "orders"]
    elif problem == "fingerprint":
        snapshot.cluster_uid = "SENSITIVE-FOREIGN-FINGERPRINT"
    elif problem == "kind":
        controllers[0]["kind"] = "Deployment"
    else:
        controllers[0]["apiVersion"] = "apps/v1beta2"
    with pytest.raises(ValueError) as error:
        project_daemonset_status(
            snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
        )
    assert "SENSITIVE-" not in str(error.value)


@pytest.mark.parametrize(
    ("problem", "issue"),
    [
        ("partial", "incomplete_metadata"),
        ("missing-list", "incomplete_daemonset_lists"),
        ("missing-version", "incomplete_daemonset_lists"),
        ("unknown-clock", "metadata_source_clock_unknown"),
        ("future-clock", "future_metadata_source"),
        ("stale", "stale_metadata_source"),
        ("future-generation-clock", "invalid_metadata_clock"),
    ],
)
def test_daemonset_status_source_gaps_do_not_erase_independent_observations(
    problem: str, issue: str
) -> None:
    snapshot, controllers = daemonset_status_inputs()
    if problem == "partial":
        snapshot.collection.status = CollectionStatus.PARTIAL
        snapshot.collection.missing_fields = ["synthetic-source-gap"]
    elif problem == "missing-list":
        snapshot.api_availability.pop("apps/v1/daemonsets")
    elif problem == "missing-version":
        snapshot.resource_versions.pop("apps/v1/daemonsets")
    elif problem == "unknown-clock":
        snapshot.collection.source_observed_at = None
    elif problem == "future-clock":
        snapshot.collection.source_observed_at = AS_OF + timedelta(seconds=1)
        snapshot.collection.completed_at = AS_OF + timedelta(seconds=1)
        snapshot.generated_at = AS_OF + timedelta(seconds=1)
    elif problem == "stale":
        snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3601)
    else:
        snapshot.generated_at = AS_OF + timedelta(seconds=1)
    original = snapshot.model_dump_json()
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert issue in result.source_issues
    assert result.daemonsets[0].generation_relation == "equal"
    assert result.daemonsets[0].number_ready == 1
    assert result.daemonsets[0].desired_node_membership == "unknown"
    assert result.collection == snapshot.collection
    assert snapshot.model_dump_json() == original


def test_daemonset_status_old_fields_empty_rosters_and_freshness_boundary() -> None:
    snapshot, controllers = daemonset_status_inputs()
    controllers[0]["metadata"].pop("generation")
    controllers[0]["metadata"].pop("resourceVersion")
    controllers[0]["status"].pop("observedGeneration")
    snapshot.collection.source_observed_at = AS_OF - timedelta(seconds=3600)
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert not result.source_issues
    assert result.daemonsets[0].generation_relation == "unknown"
    assert result.daemonsets[0].desired_number_scheduled == 2
    assert result.daemonsets[0].issues == [
        "metadata_generation_unknown",
        "observed_generation_unknown",
        "resource_version_unknown",
    ]
    snapshot.resources = [item for item in snapshot.resources if item.kind != "DaemonSet"]
    empty = project_daemonset_status(
        snapshot, daemonsets=[], as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert empty.daemonsets == [] and not empty.source_issues


def test_daemonset_status_order_budget_and_closed_claim_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import scheduling

    snapshot, controllers = daemonset_status_inputs()
    other = json.loads(json.dumps(controllers[0]))
    other["metadata"].update(name="synthetic-other-agent", uid="synthetic-other-daemonset")
    controllers.append(other)
    snapshot.resources.append(project_metadata("apps/v1/daemonsets", other))
    original = json.dumps([snapshot.model_dump(mode="json"), controllers], sort_keys=True)
    result = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert json.dumps([snapshot.model_dump(mode="json"), controllers], sort_keys=True) == original
    controllers.reverse()
    snapshot.resources.reverse()
    reordered = project_daemonset_status(
        snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
    )
    assert result.daemonsets == reordered.daemonsets
    monkeypatch.setattr(scheduling, "MAXIMUM_DAEMONSET_STATUS_OBJECTS", len(snapshot.resources))
    monkeypatch.setattr(
        scheduling, "MAXIMUM_DAEMONSET_STATUS_BYTES", len(reordered.model_dump_json().encode())
    )
    assert (
        project_daemonset_status(
            snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
        )
        == reordered
    )
    monkeypatch.setattr(scheduling, "MAXIMUM_DAEMONSET_STATUS_BYTES", 1)
    with pytest.raises(ValueError, match="output byte budget"):
        project_daemonset_status(
            snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
        )
    monkeypatch.setattr(scheduling, "MAXIMUM_DAEMONSET_STATUS_OBJECTS", len(snapshot.resources) - 1)
    with pytest.raises(ValueError, match="object budget"):
        project_daemonset_status(
            snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=3600
        )
    changed = result.model_dump(mode="json")
    changed["daemonsets"][0]["desired_node_membership"] = "complete"
    with pytest.raises(ValueError):
        scheduling.DaemonSetStatusProjection.model_validate(changed)


@pytest.mark.parametrize("age", [0, -1, True, 1.5, "3600"])
def test_daemonset_status_refuses_invalid_age_policy(age: Any) -> None:
    snapshot, controllers = daemonset_status_inputs()
    with pytest.raises(ValueError, match="source age budget"):
        project_daemonset_status(
            snapshot, daemonsets=controllers, as_of=AS_OF, maximum_source_age_seconds=age
        )


def test_daemonset_status_refuses_naive_evaluation_clock() -> None:
    snapshot, controllers = daemonset_status_inputs()
    with pytest.raises(ValueError, match="aware evaluation clock"):
        project_daemonset_status(
            snapshot,
            daemonsets=controllers,
            as_of=AS_OF.replace(tzinfo=None),
            maximum_source_age_seconds=3600,
        )


def startup_history_frames(
    count: int = 3,
) -> list[tuple[KubernetesMetadataSnapshot, dict[str, Any]]]:
    frames = []
    for index in range(count):
        state = "False" if index == 0 else "True"
        snapshot, pod = current_attempt_inputs()
        observed = AS_OF - timedelta(seconds=(count - 1 - index) * 60)
        snapshot.generated_at = observed
        snapshot.collection.started_at = observed
        snapshot.collection.completed_at = observed
        snapshot.collection.source_observed_at = observed
        pod["metadata"]["resourceVersion"] = f"synthetic-pod-version-{index}"
        pod["status"]["containerStatuses"][0]["state"]["running"]["startedAt"] = (
            AS_OF - timedelta(minutes=15)
        ).isoformat()
        pod["status"]["conditions"] = [{"type": "Ready", "status": state}]
        pod["status"]["phase"] = "Running"
        pod["spec"].update(initContainers=[], overhead={}, resources={})
        pod["spec"]["containers"][0]["resources"] = {"requests": {"cpu": "250m", "memory": "128Mi"}}
        for item in snapshot.resources:
            if item.kind == "Deployment":
                item.spec["replicas"] = 1
        projected = project_metadata("v1/pods", pod)
        snapshot.resources = [
            projected if item.uid == projected.uid else item for item in snapshot.resources
        ]
        frames.append((snapshot, pod))
    return frames


def test_startup_history_bounds_observed_readiness_without_inventing_application_startup() -> None:
    frames = startup_history_frames()
    original = json.dumps(
        [[item.model_dump(mode="json"), pod] for item, pod in frames], sort_keys=True
    )
    result = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=120),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    assert result.status == "observed_transition"
    assert result.pod_to_observed_ready_lower_seconds == 3480
    assert result.pod_to_observed_ready_upper_seconds == 3540
    assert result.first_startup == "unknown"
    assert result.application_startup_duration_seconds is None
    assert result.post_readiness_cpu_p95_mcpu is None
    assert result.post_readiness_memory_p99_mib is None
    assert not result.issues
    assert "SENSITIVE-" not in result.model_dump_json()
    assert (
        json.dumps([[item.model_dump(mode="json"), pod] for item, pod in frames], sort_keys=True)
        == original
    )


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "duplicate",
        "partial",
        "unknown-ready",
        "attempt",
        "restart",
        "stale",
        "left-censored",
        "readiness-loss",
        "clock",
    ],
)
def test_startup_history_fails_closed_for_incomplete_or_changed_episodes(problem: str) -> None:
    frames = startup_history_frames()
    if problem == "missing":
        frames.pop(1)
    elif problem == "duplicate":
        frames.append(frames[-1])
    elif problem == "partial":
        frames[1][0].collection.status = CollectionStatus.PARTIAL
        frames[1][0].collection.missing_fields = ["synthetic-gap"]
    elif problem == "unknown-ready":
        frames[1][1]["status"].pop("conditions")
    elif problem == "attempt":
        frames[1][1]["status"]["containerStatuses"][0]["containerID"] = (
            "containerd://SENSITIVE-OTHER"
        )
    elif problem == "restart":
        frames[1][1]["status"]["containerStatuses"][0]["restartCount"] = 1
    elif problem == "left-censored":
        frames[0][1]["status"]["conditions"][0]["status"] = "True"
    elif problem == "readiness-loss":
        frames[-1][1]["status"]["conditions"][0]["status"] = "False"
    elif problem == "clock":
        frames[1][0].collection.source_observed_at = None
    result = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=120),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF + timedelta(seconds=3601) if problem == "stale" else AS_OF,
        maximum_source_age_seconds=3600,
    )
    assert result.status == "blocked"
    assert result.issues
    assert result.pod_to_observed_ready_upper_seconds is None
    assert result.application_startup_duration_seconds is None


def test_startup_history_requires_exact_native_identity_and_distinguishes_no_transition() -> None:
    frames = startup_history_frames()
    frames[1][1]["metadata"]["uid"] = "synthetic-foreign"
    with pytest.raises(ValueError):
        project_startup_history(
            frames,
            container="api",
            window_start=AS_OF - timedelta(seconds=120),
            window_end=AS_OF,
            step_seconds=60,
            as_of=AS_OF,
            maximum_source_age_seconds=3600,
        )
    frames = startup_history_frames()
    for _, pod in frames:
        pod["status"]["conditions"][0]["status"] = "False"
    result = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=120),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    assert result.status == "not_observed"
    assert not result.issues


def test_startup_history_qualifies_independent_post_readiness_measurements() -> None:
    from aks_fleet_efficiency.catalog import load_catalog
    from aks_fleet_efficiency.collectors.metric_queries import render_query
    from aks_fleet_efficiency.models import (
        MetricEntity,
        MetricObservation,
        MetricQuality,
        MetricWindow,
        PrometheusMetricsSnapshot,
    )

    frames = startup_history_frames(12)
    catalog = load_catalog()
    source = catalog.source("identity-enriched")
    entity = MetricEntity(
        cluster_resource_id=CLUSTER,
        namespace="orders",
        workload_kind="Deployment",
        workload="orders",
        workload_uid="deployment-uid",
        pod_uid="pod-uid",
        container="api",
    )
    labels = {
        source.labels[field]: str(getattr(entity, field))
        for field in ("cluster_resource_id", "namespace", "workload_kind", "workload", "container")
    }
    labels.update(workload_uid="deployment-uid", pod_uid="pod-uid")
    usage = PrometheusMetricsSnapshot(
        tenant_id=SUBSCRIPTION,
        source_name="synthetic-prometheus",
        generated_at=AS_OF,
        query_start=AS_OF - timedelta(seconds=300),
        query_end=AS_OF,
        step_seconds=60,
        collection=frames[-1][0].collection.model_copy(update={"collector": "prometheus"}),
        source_profile=source,
        observations=[
            MetricObservation(
                entity=entity,
                metric=metric,
                p95=100,
                p99=256,
                minimum=0,
                maximum=256,
                latest_sample_at=AS_OF,
                quality=MetricQuality(
                    source="synthetic-prometheus",
                    query_version="1.0",
                    query_asset_version=catalog.queries[metric].version,
                    step_seconds=60,
                    observed_at=AS_OF,
                    unit=unit,
                    minimum=0,
                    maximum=256,
                    query_expression=render_query(catalog.queries[metric].expression, labels, 60),
                    window=MetricWindow(
                        start=AS_OF - timedelta(seconds=300),
                        end=AS_OF,
                        sample_count=6,
                        coverage_ratio=1,
                    ),
                ),
            )
            for metric, unit in [("cpu_usage", "mCPU"), ("memory_usage", "MiB")]
        ],
    )
    result = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=660),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
        usage=usage,
    )
    assert result.post_readiness_cpu_p95_mcpu == 100
    assert result.post_readiness_memory_p99_mib == 256
    assert not result.usage_issues
    usage.observations[0].quality.query_expression = "vector(1)"
    withheld = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=660),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
        usage=usage,
    )
    assert withheld.post_readiness_cpu_p95_mcpu is None
    assert withheld.post_readiness_memory_p99_mib == 256
    usage.observations[0].quality.query_expression = render_query(
        catalog.queries["cpu_usage"].expression, labels, 60
    )
    for metric in usage.observations:
        metric.latest_sample_at = AS_OF - timedelta(seconds=60)
        metric.quality.window.end = AS_OF - timedelta(seconds=60)
        metric.quality.window.sample_count = 5
    usage.query_end = AS_OF - timedelta(seconds=60)
    stale_tail = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=660),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=59,
        usage=usage,
    )
    assert stale_tail.post_readiness_cpu_p95_mcpu is None
    assert stale_tail.post_readiness_memory_p99_mib is None


def test_startup_history_integrates_with_original_assessment_and_opt_in_pack(
    tmp_path: Path,
) -> None:
    from aks_fleet_efficiency.artifacts import write_assessment_artifacts
    from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
    from aks_fleet_efficiency.config import AdvisorConfig
    from aks_fleet_efficiency.history import _read_verified_archive

    frames = startup_history_frames()
    history = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=120),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    value = json.loads(
        Path("examples/fixtures/history-assessment.json").read_text(encoding="utf-8")
    )
    value["kubernetes"] = [frames[-1][0].model_dump(mode="json")]
    value["metrics"] = []
    value["workload_assessments"] = []
    value["startup_history"] = [history.model_dump(mode="json")]
    fragments = AssessmentFragments.model_validate(value)
    config = profile()
    config.analysis = AdvisorConfig(packs=["AKS-START-001"])
    result = assess_fragments(fragments, config, as_of=AS_OF)
    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    assert finding.rule_id == "AKS-START-001"
    assert finding.rule_version == "1.0.0"
    assert finding.proposed_requests is None and finding.estimated_monthly_savings is None
    assert result.report.summary.pack_subject_counts["AKS-START-001"] == 1
    assert finding.metadata["first_startup"] == "unknown"
    directory = tmp_path / "artifacts"
    write_assessment_artifacts(directory, fragments, result, config.analysis)
    _, replayed, _ = _read_verified_archive(directory, tenant_id=config.scope.tenant_id)
    assert replayed.report == result.report
    stale = assess_fragments(fragments, config, as_of=AS_OF + timedelta(seconds=3601))
    assert not stale.report.recommendations
    assert "stale_lifecycle_window" in stale.report.blocked_recommendations[0].reason_codes


def test_startup_and_scheduler_commands_are_offline_scoped_and_exclusive(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from aks_fleet_efficiency.cli import app

    runner = CliRunner()
    frames = startup_history_frames()
    history = project_startup_history(
        frames,
        container="api",
        window_start=AS_OF - timedelta(seconds=120),
        window_end=AS_OF,
        step_seconds=60,
        as_of=AS_OF,
        maximum_source_age_seconds=3600,
    )
    source = tmp_path / "startup.json"
    source.write_text(history.model_dump_json(), encoding="utf-8")
    output = tmp_path / "startup-review.json"
    args = [
        "review-startup",
        "--history",
        str(source),
        "--tenant",
        SUBSCRIPTION,
        "--cluster",
        CLUSTER,
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["status"] == "observed_transition"
    assert runner.invoke(app, args).exit_code != 0
    snapshot, pods, nodes = simple_native_scheduling_inputs()
    value = json.loads(
        Path("examples/fixtures/history-assessment.json").read_text(encoding="utf-8")
    )
    value.update(kubernetes=[snapshot.model_dump(mode="json")], metrics=[], workload_assessments=[])
    fragments = tmp_path / "fragments.json"
    fragments.write_text(json.dumps(value), encoding="utf-8")
    native = tmp_path / "native.json"
    native.write_text(json.dumps({"pods": pods, "nodes": nodes}), encoding="utf-8")
    target = tmp_path / "calculation.json"
    args = [
        "calculate-scheduling",
        "--fragments",
        str(fragments),
        "--native-objects",
        str(native),
        "--tenant",
        SUBSCRIPTION,
        "--cluster",
        CLUSTER,
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(target),
    ]
    calculated = runner.invoke(app, args)
    assert calculated.exit_code == 0, calculated.output
    payload = json.loads(target.read_text())
    assert payload["pairs"] and payload["fit_status"] == "blocked"
    assert "SENSITIVE-" not in target.read_text()
    assert runner.invoke(app, args).exit_code != 0


def test_startup_canonical_example_replays_the_documented_opt_in_pack() -> None:
    from aks_fleet_efficiency.config import AdvisorConfig
    from aks_fleet_efficiency.models import FleetSnapshot
    from aks_fleet_efficiency.reporting.markdown import render_markdown
    from aks_fleet_efficiency.rules.engine import analyze

    snapshot = FleetSnapshot.model_validate_json(
        Path("examples/fixtures/startup-snapshot.json").read_bytes()
    )
    report = analyze(snapshot, AdvisorConfig(packs=["AKS-START-001"]), as_of=AS_OF)
    assert len(report.recommendations) == 1 and not report.blocked_recommendations
    assert render_markdown(report) + "\n" == Path("examples/expected-startup.md").read_text(
        encoding="utf-8"
    )


def test_current_attempt_projection_is_explicit_and_never_proves_first_startup() -> None:
    metadata_snapshot, pod = current_attempt_inputs()
    supplied = json.loads(json.dumps(pod))
    default_json = metadata_snapshot.model_dump_json()
    assert "SENSITIVE-CURRENT-ID" not in default_json
    assert "creationTimestamp" not in default_json
    context = project_current_container_attempts(metadata_snapshot, pod)
    assert context.mapping_reference == "kubernetes-core-v1@v1.36.0"
    assert context.cluster_resource_id == CLUSTER
    assert context.cluster_uid == CLUSTER_UID
    assert context.namespace_uid == "namespace-uid"
    assert context.pod_uid == "pod-uid"
    assert context.pod_resource_version == "synthetic-pod-version"
    assert context.first_startup == "unknown"
    assert context.application_startup_duration_seconds is None
    assert context.post_startup_demand is None
    attempt = context.containers[0]
    assert attempt.name == "api" and attempt.state == "running"
    assert attempt.restart_count == 0
    assert attempt.pod_to_attempt_start_seconds == 3300
    assert attempt.container_id_digest is not None and len(attempt.container_id_digest) == 64
    serialized = context.model_dump_json()
    assert all(
        value not in serialized
        for value in (
            "SENSITIVE-CURRENT-ID",
            "SENSITIVE-STATUS-TEXT",
            "SENSITIVE-IMAGE",
            '"ready"',
            '"started"',
            '"containerID"',
        )
    )
    assert pod == supplied
    assert metadata_snapshot.model_dump_json() == default_json


@pytest.mark.parametrize("value", [True, -1, 0.5, "SENSITIVE-COUNTER"])
def test_current_attempt_rejects_malformed_restart_counts(value: Any) -> None:
    def change(pod: dict[str, Any]) -> None:
        pod["status"]["containerStatuses"][0]["restartCount"] = value

    snapshot, pod = current_attempt_inputs(change)
    with pytest.raises(ValueError) as error:
        project_current_container_attempts(snapshot, pod)
    assert "SENSITIVE-COUNTER" not in str(error.value)


@pytest.mark.parametrize(
    "defect",
    [
        "naive-start",
        "invalid-start",
        "future-start",
        "start-before-pod",
        "future-creation",
        "invalid-identity",
        "duplicate-status",
        "foreign-status",
        "ambiguous-state",
        "unsupported-state",
        "foreign-pod",
        "fingerprint",
        "owner-binding",
    ],
)
def test_current_attempt_rejects_invalid_clocks_states_and_identity(defect: str) -> None:
    def change(pod: dict[str, Any]) -> None:
        status = pod["status"]["containerStatuses"][0]
        if defect == "naive-start":
            status["state"]["running"]["startedAt"] = "2026-10-29T11:55:00"
        elif defect == "invalid-start":
            status["state"]["running"]["startedAt"] = "SENSITIVE-CLOCK"
        elif defect == "future-start":
            status["state"]["running"]["startedAt"] = (AS_OF + timedelta(seconds=1)).isoformat()
        elif defect == "start-before-pod":
            status["state"]["running"]["startedAt"] = (AS_OF - timedelta(hours=2)).isoformat()
        elif defect == "future-creation":
            pod["metadata"]["creationTimestamp"] = (AS_OF + timedelta(seconds=1)).isoformat()
        elif defect == "invalid-identity":
            status["containerID"] = ["SENSITIVE-ID"]
        elif defect == "duplicate-status":
            pod["status"]["containerStatuses"].append(dict(status))
        elif defect == "foreign-status":
            status["name"] = "foreign-container"
        elif defect == "ambiguous-state":
            status["state"]["waiting"] = {"message": "SENSITIVE-BODY"}
        elif defect == "unsupported-state":
            status["state"] = {"unknown-native-state": {}}

    snapshot, pod = current_attempt_inputs(change)
    if defect == "foreign-pod":
        pod["metadata"]["uid"] = "foreign-pod-uid"
    elif defect == "fingerprint":
        snapshot.cluster_uid = "foreign-fingerprint"
    elif defect == "owner-binding":
        snapshot.workload_bindings["pod-uid"] = "foreign-controller-uid"
    with pytest.raises(ValueError) as error:
        project_current_container_attempts(snapshot, pod)
    assert all(
        value not in str(error.value)
        for value in (
            "SENSITIVE-CLOCK",
            "SENSITIVE-ID",
            "SENSITIVE-BODY",
        )
    )


@pytest.mark.parametrize("state", ["waiting", "terminated", "missing", "no-status"])
def test_current_attempt_preserves_unknown_running_episode(state: str) -> None:
    def change(pod: dict[str, Any]) -> None:
        if state == "no-status":
            pod["status"] = {}
            return
        status = pod["status"]["containerStatuses"][0]
        status["state"] = {} if state == "missing" else {state: {"message": "SENSITIVE-TEXT"}}
        status.pop("restartCount")
        status.pop("containerID")

    snapshot, pod = current_attempt_inputs(change)
    context = project_current_container_attempts(snapshot, pod)
    attempt = context.containers[0]
    assert attempt.state == (state if state in {"waiting", "terminated"} else "unknown")
    assert attempt.started_at is None and attempt.pod_to_attempt_start_seconds is None
    assert attempt.restart_count is None and attempt.container_id_digest is None
    assert "current_running_start_unknown" in attempt.issues
    assert "supplied_payload_observation_unverified" in context.issues
    assert context.first_startup == "unknown" and context.post_startup_demand is None
    assert "SENSITIVE-TEXT" not in context.model_dump_json()


def test_current_attempt_missing_lifecycle_fields_and_elapsed_boundary() -> None:
    snapshot, pod = current_attempt_inputs()
    pod["metadata"].pop("creationTimestamp")
    pod["metadata"].pop("resourceVersion")
    context = project_current_container_attempts(snapshot, pod)
    assert context.pod_created_at is None and context.pod_resource_version is None
    assert context.containers[0].pod_to_attempt_start_seconds is None
    assert {"pod_creation_unknown", "pod_resource_version_unknown"} <= set(context.issues)
    pod["metadata"]["creationTimestamp"] = "2026-10-29T13:55:00+02:00"
    pod["status"]["containerStatuses"][0]["restartCount"] = 3
    context = project_current_container_attempts(snapshot, pod)
    assert context.pod_created_at == AS_OF - timedelta(minutes=5)
    assert context.containers[0].pod_to_attempt_start_seconds == 0
    assert context.first_startup == "unknown"
    assert PodContainerAttempts.model_validate_json(context.model_dump_json()) == context


@pytest.mark.parametrize("quality", ["partial", "missing-clock", "old-source"])
def test_current_attempt_does_not_refresh_or_qualify_metadata(quality: str) -> None:
    snapshot, pod = current_attempt_inputs()
    if quality == "partial":
        snapshot.collection.status = CollectionStatus.PARTIAL
        snapshot.collection.missing_fields.append("synthetic-missing-field")
    elif quality == "missing-clock":
        snapshot.collection.source_observed_at = None
    else:
        snapshot.collection.source_observed_at = AS_OF - timedelta(days=30)
    context = project_current_container_attempts(snapshot, pod)
    assert context.collection == snapshot.collection
    assert context.metadata_generated_at == AS_OF
    assert "metadata_freshness_unassessed" in context.issues
    assert "supplied_payload_observation_unverified" in context.issues
    if quality == "partial":
        assert "incomplete_metadata" in context.issues
    elif quality == "missing-clock":
        assert "metadata_source_clock_unknown" in context.issues
    assert context.first_startup == "unknown" and context.post_startup_demand is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_startup", "confirmed"),
        ("application_startup_duration_seconds", 5),
        ("post_startup_demand", {"cpu_mcores": 100}),
        ("ready", True),
    ],
)
def test_current_attempt_contract_rejects_promoted_claims(field: str, value: Any) -> None:
    snapshot, pod = current_attempt_inputs()
    payload = project_current_container_attempts(snapshot, pod).model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValueError):
        PodContainerAttempts.model_validate(payload)


@pytest.mark.parametrize("value", ["private-probe-text", ["private-probe-text"], True, 1.5, -1])
def test_sanitized_exports_reject_noninteger_or_negative_probe_timing(value: Any) -> None:
    from test_assessment import payload

    from aks_fleet_efficiency.assessment import AssessmentFragments

    exported = payload()
    pod = next(item for item in exported["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["spec"]["containers"][0]["livenessProbe"] = {"periodSeconds": value}

    with pytest.raises((ValueError, KubernetesReadError)) as error:
        AssessmentFragments.model_validate(exported)

    assert "private-probe-text" not in str(error.value)


def test_live_projection_rejects_unapproved_probe_timing_without_persisting_it() -> None:
    reader = FakeKubernetesReader()
    reader.rows["v1/pods"] = [
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": metadata("orders", "pod-uid", "orders"),
            "spec": {
                "containers": [
                    {"name": "api", "livenessProbe": {"periodSeconds": "private-probe-text"}}
                ]
            },
        }
    ]

    result = collect(reader)

    assert result.collection.status != "complete"
    assert "private-probe-text" not in result.model_dump_json()


def test_absent_optional_apis_are_explicit_not_permission_success() -> None:
    result = collect(FakeKubernetesReader())
    assert result.collection.status == "complete"
    assert result.api_availability["autoscaling.k8s.io/v1/verticalpodautoscalers"] == "absent"
    assert result.api_availability["keda.sh/v1alpha1/scaledobjects"] == "absent"


def test_vpa_projection_retains_container_mode_without_unapproved_fields() -> None:
    reader = FakeKubernetesReader()
    reader.rows["autoscaling.k8s.io/v1/verticalpodautoscalers"] = [
        {
            "apiVersion": "autoscaling.k8s.io/v1",
            "kind": "VerticalPodAutoscaler",
            "metadata": metadata("synthetic-vpa", "synthetic-vpa-uid", "orders"),
            "spec": {
                "targetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": "orders"},
                "updatePolicy": {"updateMode": "Recreate"},
                "resourcePolicy": {
                    "containerPolicies": [
                        {
                            "containerName": "api",
                            "mode": "Off",
                            "controlledResources": ["cpu"],
                            "controlledValues": "RequestsOnly",
                            "unapproved": "synthetic-private-marker",
                        }
                    ]
                },
            },
        }
    ]
    result = collect(reader)
    vpa = next(item for item in result.resources if item.kind == "VerticalPodAutoscaler")
    assert vpa.spec["resourcePolicy"]["containerPolicies"][0]["mode"] == "Off"
    assert vpa.spec["resourcePolicy"]["containerPolicies"][0]["controlledValues"] == "RequestsOnly"
    assert "synthetic-private-marker" not in result.model_dump_json()


def test_forbidden_required_resource_makes_the_cluster_partial() -> None:
    reader = FakeKubernetesReader()
    reader.errors["v1/pods"] = "forbidden"
    result = collect(reader)
    assert result.collection.status == "partial"
    assert result.collection.completed_scope == []
    assert result.collection.errors[0].code == "forbidden"


def test_wrong_cluster_fingerprint_stops_before_workloads_are_read() -> None:
    reader = FakeKubernetesReader()
    reader.rows["v1/namespaces"][0]["metadata"]["uid"] = "wrong-cluster-uid"
    result = collect(reader)
    assert result.collection.status == "failed"
    assert not result.resources
    assert [resource for resource, _ in reader.calls] == ["v1/namespaces"]


def test_reader_never_lists_secrets_configmaps_or_logs() -> None:
    reader = FakeKubernetesReader()
    collect(reader)
    requested = [resource for resource, _ in reader.calls]
    assert requested
    assert not any(
        "secrets" in resource or "configmaps" in resource or "/log" in resource
        for resource in requested
    )


def add_workload_chain(reader: FakeKubernetesReader) -> None:
    reader.rows["apps/v1/deployments"] = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": metadata("orders", "deployment-uid", "orders"),
            "spec": {"replicas": 2},
        }
    ]
    replica_metadata = metadata("orders-replicaset", "replicaset-uid", "orders")
    replica_metadata["ownerReferences"] = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "orders",
            "uid": "deployment-uid",
            "controller": True,
        }
    ]
    reader.rows["apps/v1/replicasets"] = [
        {
            "apiVersion": "apps/v1",
            "kind": "ReplicaSet",
            "metadata": replica_metadata,
        }
    ]
    pod_metadata = metadata("orders-pod", "pod-uid", "orders")
    pod_metadata["ownerReferences"] = [
        {
            "apiVersion": "apps/v1",
            "kind": "ReplicaSet",
            "name": "orders-replicaset",
            "uid": "replicaset-uid",
            "controller": True,
        }
    ]
    reader.rows["v1/pods"] = [
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": pod_metadata,
            "spec": {"containers": [{"name": "api"}]},
        }
    ]


def test_pod_owner_chain_is_reconciled_by_uid() -> None:
    reader = FakeKubernetesReader()
    add_workload_chain(reader)
    result = collect(reader)
    assert result.collection.status == "complete"
    assert result.workload_bindings["pod-uid"] == "deployment-uid"


def test_recreated_controller_name_does_not_override_an_old_owner_uid() -> None:
    reader = FakeKubernetesReader()
    add_workload_chain(reader)
    reader.rows["apps/v1/deployments"][0]["metadata"]["uid"] = "recreated-deployment-uid"
    result = collect(reader)
    assert result.workload_bindings["pod-uid"] is None
    assert result.collection.status == "partial"


def azure_cluster() -> AzureClusterInventory:
    return AzureClusterInventory(
        resource_id=CLUSTER,
        name="aks-synthetic",
        subscription_id=SUBSCRIPTION,
        resource_group="rg-synthetic",
        location="eastus2",
        node_pools=[
            {
                "resource_id": f"{CLUSTER}/agentPools/apps",
                "name": "apps",
                "vm_size": "Standard_D4s_v5",
            }
        ],
    )


def add_node(reader: FakeKubernetesReader, subscription: str = SUBSCRIPTION) -> str:
    azure_id = (
        f"/subscriptions/{subscription}/resourceGroups/rg-node-synthetic/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/synthetic-vmss/virtualMachines/0"
    )
    node_metadata = metadata("synthetic-node", "node-uid")
    node_metadata["labels"] = {
        "kubernetes.azure.com/agentpool": "apps",
        "topology.kubernetes.io/zone": "eastus2-1",
    }
    reader.rows["v1/nodes"] = [
        {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": node_metadata,
            "spec": {"providerID": f"azure://{azure_id}"},
            "status": {"allocatable": {"cpu": "3900m", "memory": "7Gi"}},
        }
    ]
    return azure_id


def test_node_provider_identity_is_bound_to_explicit_azure_inventory() -> None:
    reader = FakeKubernetesReader()
    azure_id = add_node(reader)
    result = collect(
        reader, azure_cluster=azure_cluster(), expected_node_resource_group="rg-node-synthetic"
    )
    assert result.nodes[0].state == "matched"
    assert result.nodes[0].azure_resource_id == azure_id
    assert result.nodes[0].node_pool_resource_id == f"{CLUSTER}/agentPools/apps"


def test_foreign_node_provider_identity_cannot_join_by_pool_name() -> None:
    reader = FakeKubernetesReader()
    add_node(reader, "00000000-0000-0000-0000-000000000001")
    result = collect(
        reader, azure_cluster=azure_cluster(), expected_node_resource_group="rg-node-synthetic"
    )
    assert result.nodes[0].state == "mismatch"
    assert result.nodes[0].node_pool_resource_id is None
    assert result.collection.status == "partial"


def test_missing_azure_binding_remains_unknown() -> None:
    reader = FakeKubernetesReader()
    add_node(reader)
    result = collect(reader)
    assert result.nodes[0].state == "unknown"
    assert result.nodes[0].node_pool_resource_id is None


def test_optional_autoscaler_projection_excludes_authentication_metadata() -> None:
    reader = FakeKubernetesReader()
    reader.rows["keda.sh/v1alpha1/scaledobjects"] = [
        {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "metadata": metadata("orders-scaler", "scaler-uid", "orders"),
            "spec": {
                "scaleTargetRef": {"name": "orders"},
                "triggers": [
                    {
                        "type": "azure-servicebus",
                        "metricType": "AverageValue",
                        "metadata": {"connection": "synthetic-private-connection"},
                        "authenticationRef": {"name": "synthetic-private-reference"},
                    }
                ],
            },
        }
    ]
    result = collect(reader)
    serialized = result.model_dump_json()
    assert "azure-servicebus" in serialized
    assert "synthetic-private" not in serialized


class FakeApiError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__("synthetic-private-error-body")
        self.status = status
        self.headers = {"Retry-After": "2"}


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status = 200
        self.headers = {"Date": "Thu, 29 Oct 2026 12:00:00 GMT"}
        self.payload = json.dumps(payload).encode()
        self.closed = False
        self.response = self

    def read(self, amount: int) -> bytes:
        return self.payload[:amount]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.closed = True


class FakeApiClient:
    def __init__(self) -> None:
        self.configuration = SimpleNamespace(
            host="https://api.example.invalid",
            verify_ssl=True,
            assert_hostname=None,
            debug=False,
            retries=0,
        )
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.responses: dict[str, dict[str, Any]] = {}
        self.failures: dict[str, int] = {}
        self.last_response: FakeResponse | None = None
        self.serializations: list[dict[str, Any]] = []

    def param_serialize(self, *, method: str, resource_path: str, **kwargs: Any) -> tuple[Any, ...]:
        self.serializations.append(kwargs)
        query = urlencode(kwargs.get("query_params", []))
        return (
            method,
            f"{self.configuration.host}{resource_path}?{query}",
            kwargs.get("header_params"),
            None,
            [],
        )

    def call_api(
        self,
        method: str,
        url: str,
        headers: Any = None,
        body: Any = None,
        post_params: Any = None,
        **kwargs: Any,
    ) -> FakeResponse:
        path = urlsplit(url).path
        self.calls.append((path, method, kwargs))
        if path in self.failures:
            raise FakeApiError(self.failures[path])
        response = FakeResponse(self.responses[path])
        self.last_response = response
        return response


def sdk_reader(monkeypatch: pytest.MonkeyPatch, client: FakeApiClient, **options: Any) -> Any:
    modules = {
        "kubernetes.client.exceptions": SimpleNamespace(ApiException=FakeApiError),
        "urllib3.exceptions": SimpleNamespace(
            HTTPError=type("SyntheticHttpError", (Exception,), {})
        ),
    }
    monkeypatch.setattr(kubernetes_module, "import_module", lambda name: modules[name])
    return KubernetesSdkReader(profile(), cluster_resource_id=CLUSTER, api_client=client, **options)


def test_sdk_reader_uses_only_get_and_projects_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient()
    client.responses["/api/v1/pods"] = {
        "apiVersion": "v1",
        "kind": "PodList",
        "metadata": {"resourceVersion": "123", "continue": ""},
        "items": [
            {
                "metadata": metadata("pod", "pod-uid", "orders"),
                "spec": {
                    "containers": [
                        {
                            "name": "api",
                            "env": [{"name": "PASSWORD", "value": "synthetic-private-value"}],
                        }
                    ]
                },
            }
        ],
    }
    reader = sdk_reader(monkeypatch, client)
    page = reader.list_page("v1/pods", continue_token="opaque-cursor", page_size=100)
    path, method, options = client.calls[0]
    assert path == "/api/v1/pods"
    assert method == "GET"
    assert ("limit", 100) in client.serializations[0]["query_params"]
    assert ("continue", "opaque-cursor") in client.serializations[0]["query_params"]
    assert client.serializations[0]["auth_settings"] == ["BearerToken"]
    assert options["_request_timeout"] == (30, 30)
    assert page.continue_token is None
    assert page.resource_version == "123"
    assert page.observed_at == AS_OF
    assert "synthetic-private" not in json.dumps(page.items)
    assert client.last_response is not None and client.last_response.closed


@pytest.mark.parametrize(
    "resource", ["v1/secrets", "v1/configmaps", "v1/pods/log", "../nodes", "v1/pods/exec"]
)
def test_sdk_resource_allowlist_rejects_prohibited_paths(
    monkeypatch: pytest.MonkeyPatch, resource: str
) -> None:
    client = FakeApiClient()
    reader = sdk_reader(monkeypatch, client)
    with pytest.raises(KubernetesReadError):
        reader.list_page(resource, continue_token=None, page_size=100)
    assert not client.calls


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verify_ssl", False),
        ("assert_hostname", False),
        ("debug", True),
        ("host", "http://api.example.invalid"),
    ],
)
def test_sdk_rejects_unsafe_tls_or_debug_settings(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    client = FakeApiClient()
    setattr(client.configuration, field, value)
    with pytest.raises(ValueError):
        sdk_reader(monkeypatch, client)
    assert not client.calls


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (410, "invalid-response"),
        (429, "throttled"),
        (503, "unavailable"),
    ],
)
def test_sdk_errors_do_not_echo_response_bodies(
    monkeypatch: pytest.MonkeyPatch, status: int, code: str
) -> None:
    client = FakeApiClient()
    client.failures["/api/v1/nodes"] = status
    reader = sdk_reader(monkeypatch, client)
    with pytest.raises(KubernetesReadError) as error:
        reader.list_page("v1/nodes", continue_token=None, page_size=100)
    assert error.value.code == code
    assert "synthetic-private" not in str(error.value)
    assert error.value.retry_after_seconds == 2


def test_sdk_rejects_oversized_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient()
    client.responses["/api/v1/nodes"] = {"oversized": "x" * 2048}
    reader = sdk_reader(monkeypatch, client, max_response_bytes=1024)
    with pytest.raises(KubernetesReadError):
        reader.list_page("v1/nodes", continue_token=None, page_size=100)
    assert client.last_response is not None and client.last_response.closed


def test_sdk_discovers_only_allowlisted_resource_families(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient()
    client.responses["/api/v1"] = {
        "resources": [
            {"name": "pods", "kind": "Pod", "namespaced": True, "verbs": ["get", "list"]},
            {"name": "secrets", "kind": "Secret", "namespaced": True, "verbs": ["get", "list"]},
        ]
    }
    client.responses["/apis"] = {
        "groups": [{"name": "keda.sh", "versions": [{"version": "v1alpha1"}]}]
    }
    client.responses["/apis/keda.sh/v1alpha1"] = {
        "resources": [
            {
                "name": "scaledobjects",
                "kind": "ScaledObject",
                "namespaced": True,
                "verbs": ["get", "list"],
            }
        ]
    }
    discovered = sdk_reader(monkeypatch, client).discover()
    assert discovered == {"v1/pods", "keda.sh/v1alpha1/scaledobjects"}
    assert all(method == "GET" for _, method, _ in client.calls)


def test_optional_sdk_dependency_is_declared() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert any(
        value.startswith("kubernetes>=")
        for value in project["project"]["optional-dependencies"]["kubernetes"]
    )


def test_priority_and_runtime_overhead_are_preserved_without_arbitrary_root_fields() -> None:
    reader = FakeKubernetesReader()
    reader.rows["scheduling.k8s.io/v1/priorityclasses"] = [
        {
            "apiVersion": "scheduling.k8s.io/v1",
            "kind": "PriorityClass",
            "metadata": metadata("critical", "priority-uid"),
            "value": 1000,
            "globalDefault": False,
            "preemptionPolicy": "Never",
            "privateField": "synthetic-private-value",
        }
    ]
    reader.rows["node.k8s.io/v1/runtimeclasses"] = [
        {
            "apiVersion": "node.k8s.io/v1",
            "kind": "RuntimeClass",
            "metadata": metadata("sandbox", "runtime-uid"),
            "handler": "sandbox",
            "overhead": {"podFixed": {"cpu": "100m", "memory": "64Mi"}},
        }
    ]
    result = collect(reader)
    priority = next(item for item in result.resources if item.kind == "PriorityClass")
    runtime = next(item for item in result.resources if item.kind == "RuntimeClass")
    assert priority.attributes["value"] == 1000
    assert runtime.attributes["overhead"]["podFixed"]["memory"] == "64Mi"
    assert "synthetic-private" not in result.model_dump_json()


def test_unsupported_optional_api_is_not_reported_absent() -> None:
    reader = FakeKubernetesReader()
    reader.rows["karpenter.sh/v1beta1/nodepools"] = []
    result = collect(reader)
    assert result.api_availability["karpenter.sh/v1/nodepools"] == "unsupported"


@pytest.mark.parametrize("second_version", ["first", "changed"])
def test_paging_preserves_a_consistent_resource_version(second_version: str) -> None:
    reader = FakeKubernetesReader()
    original = reader.list_page

    def pages(resource: str, *, continue_token: str | None, page_size: int) -> KubernetesPage:
        if resource != "v1/namespaces":
            return original(resource, continue_token=continue_token, page_size=page_size)
        reader.calls.append((resource, continue_token))
        if continue_token is None:
            return KubernetesPage(
                items=reader.rows[resource][:1],
                resource_version="first",
                continue_token="next",
                observed_at=AS_OF,
            )
        return KubernetesPage(
            items=reader.rows[resource][1:], resource_version=second_version, observed_at=AS_OF
        )

    reader.list_page = pages
    result = collect(reader)
    assert result.collection.status == ("complete" if second_version == "first" else "failed")
    if second_version == "first":
        assert result.resource_versions["v1/namespaces"] == "first"


def test_cursor_loop_stops_at_the_resource_boundary() -> None:
    reader = FakeKubernetesReader()
    original = reader.list_page

    def pages(resource: str, *, continue_token: str | None, page_size: int) -> KubernetesPage:
        if resource != "v1/pods":
            return original(resource, continue_token=continue_token, page_size=page_size)
        reader.calls.append((resource, continue_token))
        return KubernetesPage(
            items=[], resource_version="rv", continue_token="repeated", observed_at=AS_OF
        )

    reader.list_page = pages
    result = collect(reader)
    assert result.collection.status == "partial"
    assert len([name for name, _ in reader.calls if name == "v1/pods"]) == 2


def test_throttling_is_retried_with_a_bounded_delay() -> None:
    reader = FakeKubernetesReader()
    original = reader.list_page
    attempts = 0

    def flaky(resource: str, *, continue_token: str | None, page_size: int) -> KubernetesPage:
        nonlocal attempts
        if resource == "v1/pods":
            attempts += 1
            if attempts == 1:
                raise KubernetesReadError("throttled", retry_after_seconds=99999)
        return original(resource, continue_token=continue_token, page_size=page_size)

    reader.list_page = flaky
    waits: list[float] = []
    result = KubernetesMetadataCollector(
        profile(),
        cluster_resource_id=CLUSTER,
        expected_cluster_uid=CLUSTER_UID,
        reader=reader,
        clock=lambda: AS_OF,
        sleep=waits.append,
    ).collect()
    assert result.collection.status == "complete"
    assert result.collection.retry_count == 1
    assert waits == [30]


def test_sdk_does_not_ignore_remaining_items_without_a_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient()
    client.responses["/api/v1/pods"] = {
        "apiVersion": "v1",
        "kind": "PodList",
        "metadata": {"resourceVersion": "rv", "remainingItemCount": 2},
        "items": [],
    }
    with pytest.raises(KubernetesReadError):
        sdk_reader(monkeypatch, client).list_page("v1/pods", continue_token=None, page_size=100)


def test_sdk_refuses_credential_refresh_hooks_and_impersonation_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient()
    client.configuration.refresh_api_key_hook = lambda _: None
    with pytest.raises(ValueError):
        sdk_reader(monkeypatch, client)
    client.configuration.refresh_api_key_hook = None
    client.default_headers = {"Impersonate-User": "synthetic-user"}
    with pytest.raises(ValueError):
        sdk_reader(monkeypatch, client)
    assert not client.calls


def test_installed_sdk_serialization_and_raw_response_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = pytest.importorskip("kubernetes.client")
    rest = pytest.importorskip("kubernetes.client.rest")
    urllib3 = pytest.importorskip("urllib3")
    configuration = client.Configuration()
    configuration.host = "https://api.example.invalid"
    configuration.retries = 0
    calls: list[tuple[str, str]] = []

    def no_network(method: str, url: str, **kwargs: Any) -> Any:
        calls.append((method, url))
        body = json.dumps(
            {
                "apiVersion": "v1",
                "kind": "PodList",
                "metadata": {"resourceVersion": "123"},
                "items": [],
            }
        ).encode()
        return rest.RESTResponse(
            urllib3.HTTPResponse(
                body=io.BytesIO(body),
                status=200,
                headers={"Date": "Thu, 29 Oct 2026 12:00:00 GMT"},
                preload_content=False,
            )
        )

    with client.ApiClient(configuration) as api_client:
        monkeypatch.setattr(
            api_client,
            "call_api",
            lambda method, url, *args, **kwargs: no_network(method, url, **kwargs),
        )
        reader = KubernetesSdkReader(profile(), cluster_resource_id=CLUSTER, api_client=api_client)
        page = reader.list_page("v1/pods", continue_token="opaque token", page_size=20)
    assert page.resource_version == "123"
    assert calls[0][0] == "GET"
    parsed = urlsplit(calls[0][1])
    assert parsed.path == "/api/v1/pods"
    assert dict(parse_qsl(parsed.query)) == {"limit": "20", "continue": "opaque token"}


def test_hpa_pod_and_object_targets_are_not_lost() -> None:
    reader = FakeKubernetesReader()
    reader.rows["autoscaling/v2/horizontalpodautoscalers"] = [
        {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": metadata("orders-hpa", "hpa-uid", "orders"),
            "spec": {
                "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": "orders"},
                "metrics": [
                    {
                        "type": "Pods",
                        "pods": {
                            "metric": {"name": "requests"},
                            "target": {"type": "AverageValue", "averageValue": "10"},
                        },
                    },
                    {
                        "type": "Object",
                        "object": {
                            "describedObject": {
                                "apiVersion": "networking.k8s.io/v1",
                                "kind": "Ingress",
                                "name": "orders",
                            },
                            "metric": {"name": "requests"},
                            "target": {"type": "Value", "value": "100"},
                        },
                    },
                ],
            },
        }
    ]
    result = collect(reader)
    hpa = next(item for item in result.resources if item.kind == "HorizontalPodAutoscaler")
    assert hpa.spec["metrics"][0]["pods"]["target"]["averageValue"] == "10"
    assert hpa.spec["metrics"][1]["object"]["target"]["value"] == "100"


def test_forbidden_optional_api_is_not_reported_absent() -> None:
    reader = FakeKubernetesReader()
    resource = "autoscaling.k8s.io/v1/verticalpodautoscalers"
    reader.rows[resource] = []
    reader.errors[resource] = "forbidden"
    result = collect(reader)
    assert result.api_availability[resource] == "available"
    assert result.collection.status == "partial"
    assert resource in result.collection.missing_fields


@pytest.mark.parametrize("observed_at", [None, AS_OF - timedelta(days=2)])
def test_source_timestamp_is_not_replaced_with_collection_time(
    observed_at: datetime | None,
) -> None:
    reader = FakeKubernetesReader()
    original = reader.list_page

    def pages(resource: str, *, continue_token: str | None, page_size: int) -> KubernetesPage:
        return replace(
            original(resource, continue_token=continue_token, page_size=page_size),
            observed_at=observed_at,
        )

    reader.list_page = pages
    result = collect(reader)
    assert result.collection.source_observed_at == observed_at


def test_discovery_denial_is_structured_without_listing_workloads() -> None:
    reader = FakeKubernetesReader()

    def deny() -> set[str]:
        raise KubernetesReadError("forbidden")

    reader.discover = deny
    result = collect(reader)
    assert result.collection.status == "failed"
    assert result.collection.errors[0].code == "forbidden"
    assert not reader.calls
    assert not result.resources


def test_kubernetes_metadata_contract_round_trip() -> None:
    result = collect(FakeKubernetesReader())
    assert KubernetesMetadataSnapshot.model_validate_json(result.model_dump_json()) == result
