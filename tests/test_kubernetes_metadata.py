from __future__ import annotations

import io
import json
import tomllib
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
)
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import AzureClusterInventory, KubernetesMetadataSnapshot

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
    serialized = result.model_dump_json()
    assert '"250m"' in serialized
    assert "synthetic-secret" not in serialized
    assert "synthetic-private-argument" not in serialized
    assert "envFrom" not in serialized


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


def test_kubernetes_metadata_contract_round_trip_and_schema_parity() -> None:
    result = collect(FakeKubernetesReader())
    assert KubernetesMetadataSnapshot.model_validate_json(result.model_dump_json()) == result
    committed = json.loads(
        Path("schemas/kubernetes-metadata.schema.json").read_text(encoding="utf-8")
    )
    assert committed == KubernetesMetadataSnapshot.model_json_schema()
