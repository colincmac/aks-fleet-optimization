from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib import import_module
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import JsonValue, ValidationError

from aks_fleet_efficiency.config import ClusterTarget, OnboardingConfig
from aks_fleet_efficiency.models import (
    AzureClusterInventory,
    CollectionError,
    CollectionErrorCode,
    CollectionStatus,
    CollectorResult,
    KubernetesMetadataSnapshot,
    KubernetesNodeIdentity,
    KubernetesObjectMetadata,
)

type Projection = dict[str, Projection | None]
QUANTITY_FIELDS: Projection = {"cpu": None, "memory": None, "ephemeral-storage": None, "pods": None}
SELECTOR_FIELDS: Projection = {
    "matchLabels": {"*": None},
    "matchExpressions": {"key": None, "operator": None, "values": None},
}
CONTAINER_FIELDS: Projection = {
    "name": None,
    "restartPolicy": None,
    "resources": {"requests": QUANTITY_FIELDS, "limits": QUANTITY_FIELDS},
}
TAINT_FIELDS: Projection = {
    "key": None,
    "value": None,
    "effect": None,
    "operator": None,
    "tolerationSeconds": None,
}
AFFINITY_TERM: Projection = {
    "labelSelector": SELECTOR_FIELDS,
    "namespaceSelector": SELECTOR_FIELDS,
    "namespaces": None,
    "topologyKey": None,
}
POD_AFFINITY: Projection = {
    "requiredDuringSchedulingIgnoredDuringExecution": AFFINITY_TERM,
    "preferredDuringSchedulingIgnoredDuringExecution": {
        "weight": None,
        "podAffinityTerm": AFFINITY_TERM,
    },
}
NODE_TERMS: Projection = {
    "matchExpressions": {"key": None, "operator": None, "values": None},
    "matchFields": {"key": None, "operator": None, "values": None},
}
POD_FIELDS: Projection = {
    "containers": CONTAINER_FIELDS,
    "initContainers": CONTAINER_FIELDS,
    "overhead": QUANTITY_FIELDS,
    "resources": {"requests": QUANTITY_FIELDS, "limits": QUANTITY_FIELDS},
    "nodeName": None,
    "nodeSelector": {"*": None},
    "tolerations": TAINT_FIELDS,
    "topologySpreadConstraints": {
        "maxSkew": None,
        "topologyKey": None,
        "whenUnsatisfiable": None,
        "minDomains": None,
        "labelSelector": SELECTOR_FIELDS,
    },
    "priorityClassName": None,
    "priority": None,
    "runtimeClassName": None,
    "schedulerName": None,
    "affinity": {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": NODE_TERMS},
            "preferredDuringSchedulingIgnoredDuringExecution": {
                "weight": None,
                "preference": NODE_TERMS,
            },
        },
        "podAffinity": POD_AFFINITY,
        "podAntiAffinity": POD_AFFINITY,
    },
    "volumes": {
        "name": None,
        "persistentVolumeClaim": {"claimName": None, "readOnly": None},
        "emptyDir": {"medium": None, "sizeLimit": None},
    },
}
TARGET_FIELDS: Projection = {"apiVersion": None, "kind": None, "name": None}
METRIC_TARGET: Projection = {
    "type": None,
    "value": None,
    "averageValue": None,
    "averageUtilization": None,
}
METRIC_REFERENCE: Projection = {"name": None, "selector": SELECTOR_FIELDS}
HPA_METRICS: Projection = {
    "type": None,
    "resource": {"name": None, "target": METRIC_TARGET},
    "containerResource": {"name": None, "container": None, "target": METRIC_TARGET},
    "external": {"metric": METRIC_REFERENCE, "target": METRIC_TARGET},
    "pods": {"metric": METRIC_REFERENCE, "target": METRIC_TARGET},
    "object": {
        "describedObject": TARGET_FIELDS,
        "metric": METRIC_REFERENCE,
        "target": METRIC_TARGET,
    },
}
WORKLOAD_FIELDS: Projection = {
    "replicas": None,
    "selector": SELECTOR_FIELDS,
    "template": {"spec": POD_FIELDS},
    "jobTemplate": {"spec": {"template": {"spec": POD_FIELDS}}},
    "parallelism": None,
    "completions": None,
    "suspend": None,
}
VPA_BOUND: Projection = {"cpu": None, "memory": None}


@dataclass(frozen=True)
class ResourceDefinition:
    kind: str
    namespaced: bool
    spec: Projection
    status: Projection
    required: bool = True
    attributes: Projection | None = None


RESOURCE_CATALOG = {
    "v1/namespaces": ResourceDefinition("Namespace", False, {}, {}),
    "v1/nodes": ResourceDefinition(
        "Node",
        False,
        {"providerID": None, "taints": TAINT_FIELDS, "unschedulable": None},
        {"allocatable": QUANTITY_FIELDS, "capacity": QUANTITY_FIELDS},
    ),
    "v1/pods": ResourceDefinition(
        "Pod",
        True,
        POD_FIELDS,
        {
            "phase": None,
            "qosClass": None,
            "containerStatuses": {
                "name": None,
                "lastState": {"terminated": {"reason": None, "exitCode": None, "finishedAt": None}},
            },
        },
    ),
    "v1/resourcequotas": ResourceDefinition(
        "ResourceQuota",
        True,
        {"hard": {"*": None}, "scopes": None},
        {"hard": {"*": None}, "used": {"*": None}},
    ),
    "v1/limitranges": ResourceDefinition(
        "LimitRange",
        True,
        {
            "limits": {
                "type": None,
                "min": QUANTITY_FIELDS,
                "max": QUANTITY_FIELDS,
                "default": QUANTITY_FIELDS,
                "defaultRequest": QUANTITY_FIELDS,
                "maxLimitRequestRatio": QUANTITY_FIELDS,
            }
        },
        {},
    ),
    "apps/v1/deployments": ResourceDefinition(
        "Deployment", True, WORKLOAD_FIELDS, {"replicas": None, "availableReplicas": None}
    ),
    "apps/v1/replicasets": ResourceDefinition(
        "ReplicaSet", True, WORKLOAD_FIELDS, {"replicas": None}
    ),
    "apps/v1/statefulsets": ResourceDefinition(
        "StatefulSet", True, WORKLOAD_FIELDS, {"replicas": None, "readyReplicas": None}
    ),
    "apps/v1/daemonsets": ResourceDefinition(
        "DaemonSet", True, WORKLOAD_FIELDS, {"desiredNumberScheduled": None, "numberReady": None}
    ),
    "batch/v1/jobs": ResourceDefinition(
        "Job", True, WORKLOAD_FIELDS, {"active": None, "succeeded": None, "failed": None}
    ),
    "batch/v1/cronjobs": ResourceDefinition("CronJob", True, WORKLOAD_FIELDS, {}),
    "autoscaling/v2/horizontalpodautoscalers": ResourceDefinition(
        "HorizontalPodAutoscaler",
        True,
        {
            "scaleTargetRef": TARGET_FIELDS,
            "minReplicas": None,
            "maxReplicas": None,
            "metrics": HPA_METRICS,
        },
        {"currentReplicas": None, "desiredReplicas": None},
    ),
    "policy/v1/poddisruptionbudgets": ResourceDefinition(
        "PodDisruptionBudget",
        True,
        {
            "minAvailable": None,
            "maxUnavailable": None,
            "selector": SELECTOR_FIELDS,
            "unhealthyPodEvictionPolicy": None,
        },
        {
            "disruptionsAllowed": None,
            "currentHealthy": None,
            "desiredHealthy": None,
            "expectedPods": None,
        },
    ),
    "scheduling.k8s.io/v1/priorityclasses": ResourceDefinition(
        "PriorityClass",
        False,
        {},
        {},
        attributes={"value": None, "globalDefault": None, "preemptionPolicy": None},
    ),
    "node.k8s.io/v1/runtimeclasses": ResourceDefinition(
        "RuntimeClass",
        False,
        {},
        {},
        attributes={
            "handler": None,
            "overhead": {"podFixed": QUANTITY_FIELDS},
            "scheduling": {"nodeSelector": {"*": None}, "tolerations": TAINT_FIELDS},
        },
    ),
    "autoscaling.k8s.io/v1/verticalpodautoscalers": ResourceDefinition(
        "VerticalPodAutoscaler",
        True,
        {
            "targetRef": TARGET_FIELDS,
            "updatePolicy": {"updateMode": None},
            "resourcePolicy": {
                "containerPolicies": {
                    "containerName": None,
                    "mode": None,
                    "controlledResources": None,
                    "controlledValues": None,
                    "minAllowed": VPA_BOUND,
                    "maxAllowed": VPA_BOUND,
                }
            },
        },
        {
            "recommendation": {
                "containerRecommendations": {
                    "containerName": None,
                    "target": VPA_BOUND,
                    "lowerBound": VPA_BOUND,
                    "upperBound": VPA_BOUND,
                    "uncappedTarget": VPA_BOUND,
                }
            }
        },
        False,
    ),
    "keda.sh/v1alpha1/scaledobjects": ResourceDefinition(
        "ScaledObject",
        True,
        {
            "scaleTargetRef": TARGET_FIELDS,
            "minReplicaCount": None,
            "maxReplicaCount": None,
            "pollingInterval": None,
            "cooldownPeriod": None,
            "triggers": {"type": None, "metricType": None},
        },
        {"hpaName": None},
        False,
    ),
    "keda.sh/v1alpha1/scaledjobs": ResourceDefinition(
        "ScaledJob",
        True,
        {
            "minReplicaCount": None,
            "maxReplicaCount": None,
            "triggers": {"type": None, "metricType": None},
        },
        {},
        False,
    ),
    "karpenter.sh/v1/nodepools": ResourceDefinition(
        "NodePool",
        False,
        {
            "template": {
                "spec": {
                    "nodeClassRef": {"group": None, "kind": None, "name": None},
                    "requirements": {
                        "key": None,
                        "operator": None,
                        "values": None,
                        "minValues": None,
                    },
                    "taints": TAINT_FIELDS,
                    "startupTaints": TAINT_FIELDS,
                }
            },
            "limits": QUANTITY_FIELDS,
            "disruption": {
                "consolidationPolicy": None,
                "consolidateAfter": None,
                "budgets": {"nodes": None, "duration": None, "schedule": None, "reasons": None},
            },
        },
        {},
        False,
    ),
    "karpenter.sh/v1/nodeclaims": ResourceDefinition(
        "NodeClaim",
        False,
        {},
        {
            "nodeName": None,
            "providerID": None,
            "capacity": QUANTITY_FIELDS,
            "allocatable": QUANTITY_FIELDS,
        },
        False,
    ),
    "karpenter.azure.com/v1beta1/aksnodeclasses": ResourceDefinition(
        "AKSNodeClass", False, {"imageFamily": None, "osDiskSizeGB": None}, {}, False
    ),
}
REQUIRED_RESOURCES = tuple(
    name for name, definition in RESOURCE_CATALOG.items() if definition.required
)
LABEL_KEYS = {
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/name",
    "kubernetes.azure.com/agentpool",
    "agentpool",
    "topology.kubernetes.io/zone",
    "kubernetes.io/os",
    "node.kubernetes.io/instance-type",
}


@dataclass(frozen=True)
class KubernetesPage:
    items: list[dict[str, Any]]
    resource_version: str
    continue_token: str | None = None
    observed_at: datetime | None = None


class KubernetesReadError(Exception):
    def __init__(
        self, code: CollectionErrorCode, *, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(code)
        self.code: CollectionErrorCode = code
        self.retry_after_seconds = retry_after_seconds


class KubernetesReader(Protocol):
    cluster_resource_id: str

    def discover(self) -> set[str]: ...

    def list_page(
        self, resource: str, *, continue_token: str | None, page_size: int
    ) -> KubernetesPage: ...


def _validate_cluster_scope(profile: OnboardingConfig, resource_id: str) -> None:
    target = ClusterTarget(resource_id=resource_id)
    if target.subscription_id not in profile.scope.subscription_ids or (
        profile.clusters
        and resource_id not in {cluster.resource_id for cluster in profile.clusters}
    ):
        raise ValueError("Kubernetes cluster is outside the approved scope")


class KubernetesSdkReader:
    def __init__(
        self,
        profile: OnboardingConfig,
        *,
        cluster_resource_id: str,
        api_client: Any,
        request_timeout_seconds: float = 30,
        max_response_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        _validate_cluster_scope(profile, cluster_resource_id)
        if not math.isfinite(request_timeout_seconds) or not 0 < request_timeout_seconds <= 120:
            raise ValueError("Kubernetes request timeout must be at most 120 seconds")
        if not 1024 <= max_response_bytes <= 64 * 1024 * 1024:
            raise ValueError("invalid Kubernetes response byte bound")
        self.cluster_resource_id = cluster_resource_id
        self.api_client = api_client
        self.timeout = request_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._validate_client()
        try:
            self.errors = import_module("kubernetes.client.exceptions")
            self.http_errors = import_module("urllib3.exceptions")
        except ImportError:
            raise RuntimeError("Install the project's kubernetes optional dependencies.") from None

    def _validate_client(self) -> None:
        configuration = self.api_client.configuration
        endpoint = urlsplit(configuration.host)
        headers = getattr(self.api_client, "default_headers", {})
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
            or configuration.verify_ssl is not True
            or configuration.assert_hostname is False
            or configuration.debug
            or getattr(configuration, "retries", None) != 0
            or getattr(configuration, "refresh_api_key_hook", None) is not None
            or not isinstance(headers, dict)
            or any(str(header).casefold().startswith("impersonate-") for header in headers)
        ):
            raise ValueError(
                "Kubernetes client requires verified HTTPS, no debug logging, and zero SDK retries"
            )

    def _get(
        self, path: str, query: list[tuple[str, str | int]] | None = None
    ) -> tuple[dict[str, Any], datetime | None]:
        self._validate_client()
        try:
            parameters = self.api_client.param_serialize(
                method="GET",
                resource_path=path,
                query_params=query or [],
                header_params={"Accept": "application/json"},
                auth_settings=["BearerToken"],
            )
            if parameters[0] != "GET":
                raise KubernetesReadError("invalid-response")
            response = self.api_client.call_api(
                *parameters,
                _request_timeout=(self.timeout, self.timeout),
            )
        except self.errors.ApiException as error:
            codes: dict[int, CollectionErrorCode] = {
                401: "unauthorized",
                403: "forbidden",
                408: "timeout",
                429: "throttled",
                500: "unavailable",
                502: "unavailable",
                503: "unavailable",
                504: "timeout",
            }
            delay = None
            try:
                parsed_delay = float((error.headers or {}).get("Retry-After", ""))
                delay = parsed_delay if math.isfinite(parsed_delay) else None
            except (TypeError, ValueError):
                pass
            raise KubernetesReadError(
                codes.get(error.status, "invalid-response"), retry_after_seconds=delay
            ) from None
        except (self.http_errors.HTTPError, TimeoutError, OSError):
            raise KubernetesReadError("unavailable") from None
        try:
            if not 200 <= response.status < 300:
                raise KubernetesReadError("invalid-response")
            body = response.response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise KubernetesReadError("invalid-response")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise KubernetesReadError("invalid-response")
            observed_at = None
            date = response.headers.get("Date")
            if date:
                try:
                    parsed = parsedate_to_datetime(date)
                    if parsed.tzinfo is not None:
                        observed_at = parsed.astimezone(UTC)
                except (TypeError, ValueError, OverflowError):
                    pass
            return data, observed_at
        except (ValueError, self.http_errors.HTTPError, OSError):
            raise KubernetesReadError("invalid-response") from None
        finally:
            response.response.close()
            response.response.release_conn()

    def discover(self) -> set[str]:
        discovered: set[str] = set()

        def resources_at(api_version: str) -> None:
            path = f"/api/{api_version}" if api_version == "v1" else f"/apis/{api_version}"
            data, _ = self._get(path)
            entries = data.get("resources")
            if not isinstance(entries, list):
                raise KubernetesReadError("invalid-response")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise KubernetesReadError("invalid-response")
                name = entry.get("name")
                if not isinstance(name, str) or "/" in name or "list" not in entry.get("verbs", []):
                    continue
                key = f"{api_version}/{name}"
                family = (key.split("/")[0], name)
                definition = next(
                    (
                        value
                        for resource, value in RESOURCE_CATALOG.items()
                        if (resource.split("/")[0], resource.rsplit("/", 1)[-1]) == family
                    ),
                    None,
                )
                if definition is not None:
                    if (
                        entry.get("kind") != definition.kind
                        or entry.get("namespaced") is not definition.namespaced
                    ):
                        raise KubernetesReadError("invalid-response")
                    discovered.add(key)

        resources_at("v1")
        groups, _ = self._get("/apis")
        approved_groups = {
            resource.split("/")[0] for resource in RESOURCE_CATALOG if resource.count("/") == 2
        }
        entries = groups.get("groups")
        if not isinstance(entries, list):
            raise KubernetesReadError("invalid-response")
        for group in entries:
            if not isinstance(group, dict) or group.get("name") not in approved_groups:
                continue
            versions = group.get("versions", [])
            if not isinstance(versions, list) or len(versions) > 8:
                raise KubernetesReadError("invalid-response")
            for item in versions:
                version = item.get("version") if isinstance(item, dict) else None
                if (
                    not isinstance(version, str)
                    or re.fullmatch(r"v[0-9]+(?:(?:alpha|beta)[0-9]+)?", version) is None
                ):
                    raise KubernetesReadError("invalid-response")
                resources_at(f"{group['name']}/{version}")
        return discovered

    def list_page(
        self, resource: str, *, continue_token: str | None, page_size: int
    ) -> KubernetesPage:
        if resource not in RESOURCE_CATALOG or not 1 <= page_size <= 1000:
            raise KubernetesReadError("invalid-response")
        query: list[tuple[str, str | int]] = [("limit", page_size)]
        if continue_token is not None:
            query.append(("continue", continue_token))
        path = f"/api/{resource}" if resource.startswith("v1/") else f"/apis/{resource}"
        data, observed_at = self._get(path, query)
        definition = RESOURCE_CATALOG[resource]
        api_version = resource.rsplit("/", 1)[0]
        if data.get("kind") != f"{definition.kind}List" or data.get("apiVersion") != api_version:
            raise KubernetesReadError("invalid-response")
        entries = data.get("items")
        metadata = data.get("metadata", {})
        if (
            not isinstance(entries, list)
            or len(entries) > page_size
            or not isinstance(metadata, dict)
            or metadata.get("shardInfo")
        ):
            raise KubernetesReadError("invalid-response")
        version = metadata.get("resourceVersion")
        token = metadata.get("continue")
        if (
            not isinstance(version, str)
            or not version
            or (token is not None and not isinstance(token, str))
        ):
            raise KubernetesReadError("invalid-response")
        remaining = metadata.get("remainingItemCount")
        if remaining is not None and (
            not isinstance(remaining, int) or remaining < 0 or (remaining > 0 and not token)
        ):
            raise KubernetesReadError("invalid-response")
        safe_items = []
        try:
            for item in entries:
                if not isinstance(item, dict):
                    raise KubernetesReadError("invalid-response")
                projected = project_metadata(
                    resource, {"apiVersion": api_version, "kind": definition.kind, **item}
                )
                safe_items.append(
                    {
                        "apiVersion": projected.api_version,
                        "kind": projected.kind,
                        "metadata": {
                            "name": projected.name,
                            "namespace": projected.namespace,
                            "uid": projected.uid,
                            "labels": projected.labels,
                            "ownerReferences": projected.owner_references,
                        },
                        "spec": projected.spec,
                        "status": projected.status,
                        **projected.attributes,
                    }
                )
        except (ValidationError, TypeError, AttributeError):
            raise KubernetesReadError("invalid-response") from None
        return KubernetesPage(
            items=safe_items,
            resource_version=version,
            continue_token=token or None,
            observed_at=observed_at,
        )


def _scalar(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list):
        return [_scalar(item) for item in value]
    raise KubernetesReadError("invalid-response")


def _project(value: Any, fields: Projection) -> Any:
    if isinstance(value, list):
        return [_project(item, fields) for item in value]
    if value is None:
        return None
    if not isinstance(value, dict):
        raise KubernetesReadError("invalid-response")
    projected: dict[str, JsonValue] = {}
    for key, child in fields.items():
        if key == "*":
            return {str(name): _scalar(item) for name, item in value.items()}
        if key in value:
            projected[key] = _scalar(value[key]) if child is None else _project(value[key], child)
    return projected


def project_metadata(resource: str, item: dict[str, Any]) -> KubernetesObjectMetadata:
    definition = RESOURCE_CATALOG[resource]
    api_version = resource.rsplit("/", 1)[0]
    if item.get("kind") != definition.kind or item.get("apiVersion") != api_version:
        raise KubernetesReadError("identity-mismatch")
    metadata = item.get("metadata", {})
    namespace = metadata.get("namespace")
    if definition.namespaced and not namespace:
        raise KubernetesReadError("invalid-response")
    labels = metadata.get("labels") or {}
    owners = _project(
        metadata.get("ownerReferences", []),
        {"apiVersion": None, "kind": None, "name": None, "uid": None, "controller": None},
    )
    return KubernetesObjectMetadata(
        api_version=api_version,
        kind=definition.kind,
        name=metadata.get("name"),
        namespace=namespace,
        uid=metadata.get("uid"),
        labels={key: value for key, value in labels.items() if key in LABEL_KEYS},
        owner_references=owners,
        spec=_project(item.get("spec", {}), definition.spec),
        status=_project(item.get("status", {}), definition.status),
        attributes=_project(item, definition.attributes or {}),
    )


def validate_metadata_projection(snapshot: KubernetesMetadataSnapshot) -> None:
    for item in snapshot.resources:
        resource = next(
            (
                name
                for name, definition in RESOURCE_CATALOG.items()
                if definition.kind == item.kind and name.rsplit("/", 1)[0] == item.api_version
            ),
            None,
        )
        if resource is None:
            raise ValueError("unsupported metadata resource in sanitized export")
        raw = {
            **item.attributes,
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
        if project_metadata(resource, raw) != item:
            raise ValueError("metadata export includes fields outside the approved projection")


def _now() -> datetime:
    return datetime.now(UTC)


def _owner_bindings(
    resources: list[KubernetesObjectMetadata],
) -> tuple[dict[str, str | None], list[str]]:
    objects = {resource.uid: resource for resource in resources}
    pods = [resource for resource in resources if resource.kind == "Pod"]
    if len(objects) != len(resources):
        return {pod.uid: None for pod in pods}, ["duplicate-object-uid"]
    bindings: dict[str, str | None] = {}
    missing: list[str] = []
    workloads = {"Pod", "Deployment", "ReplicaSet", "StatefulSet", "DaemonSet", "Job", "CronJob"}
    for pod in pods:
        current = pod
        seen: set[str] = set()
        while current.uid not in seen:
            seen.add(current.uid)
            owners = [
                owner for owner in current.owner_references if owner.get("controller") is True
            ]
            if not owners:
                if current.kind in workloads:
                    bindings[pod.uid] = current.uid
                break
            if len(owners) != 1:
                break
            owner = owners[0]
            owner_uid = owner.get("uid")
            parent = objects.get(owner_uid) if isinstance(owner_uid, str) else None
            if (
                parent is None
                or parent.kind != owner.get("kind")
                or parent.name != owner.get("name")
                or parent.namespace != current.namespace
                or parent.api_version != owner.get("apiVersion")
            ):
                break
            current = parent
        if pod.uid not in bindings:
            bindings[pod.uid] = None
            missing.append(f"pod-owner:{pod.uid}")
    return bindings, missing


def _node_identity(
    node: KubernetesObjectMetadata,
    azure_cluster: AzureClusterInventory | None,
    node_resource_group: str | None,
) -> KubernetesNodeIdentity:
    raw = node.spec.get("providerID")
    provider_id = raw if isinstance(raw, str) else None
    result = KubernetesNodeIdentity(node_uid=node.uid, provider_id=provider_id, state="unknown")
    if not provider_id or azure_cluster is None or node_resource_group is None:
        return result
    parsed = urlsplit(provider_id)
    match = re.fullmatch(
        r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft.Compute/"
        r"(?:virtualMachineScaleSets/[^/]+/virtualMachines/[^/]+|virtualMachines/[^/]+)",
        parsed.path,
        flags=re.IGNORECASE,
    )
    if (
        parsed.scheme != "azure"
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or match is None
    ):
        result.state = "mismatch"
        return result
    try:
        matched_scope = (
            UUID(match.group(1)) == UUID(azure_cluster.subscription_id)
            and match.group(2).casefold() == node_resource_group.casefold()
        )
    except ValueError:
        matched_scope = False
    if not matched_scope:
        result.state = "mismatch"
        return result
    result.azure_resource_id = parsed.path
    pool_names = {
        node.labels[key]
        for key in ["kubernetes.azure.com/agentpool", "agentpool"]
        if key in node.labels
    }
    if len(pool_names) > 1:
        result.state = "mismatch"
        return result
    if not pool_names:
        return result
    pool_name = pool_names.pop()
    pool = next((pool for pool in azure_cluster.node_pools if pool.name == pool_name), None)
    if pool is None or pool.resource_id != f"{azure_cluster.resource_id}/agentPools/{pool.name}":
        return result
    result.node_pool_resource_id = pool.resource_id
    result.state = "matched"
    return result


class KubernetesMetadataCollector:
    def __init__(
        self,
        profile: OnboardingConfig,
        *,
        cluster_resource_id: str,
        expected_cluster_uid: str,
        reader: KubernetesReader,
        azure_cluster: AzureClusterInventory | None = None,
        expected_node_resource_group: str | None = None,
        clock: Callable[[], datetime] = _now,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        max_pages: int = 100,
        page_size: int = 500,
    ) -> None:
        _validate_cluster_scope(profile, cluster_resource_id)
        if reader.cluster_resource_id != cluster_resource_id or not expected_cluster_uid:
            raise ValueError("explicit cluster binding and expected namespace UID are required")
        if azure_cluster is not None and azure_cluster.resource_id != cluster_resource_id:
            raise ValueError("Azure inventory binding must match the exact cluster resource ID")
        if expected_node_resource_group is not None and (
            not expected_node_resource_group or "/" in expected_node_resource_group
        ):
            raise ValueError("expected node resource group must be an explicit resource-group name")
        if not 0 <= max_retries <= 10 or not 1 <= max_pages <= 10000 or not 1 <= page_size <= 1000:
            raise ValueError("invalid Kubernetes collection bounds")
        self.profile = profile
        self.cluster_resource_id = cluster_resource_id
        self.expected_cluster_uid = expected_cluster_uid
        self.reader = reader
        self.azure_cluster = azure_cluster
        self.expected_node_resource_group = expected_node_resource_group
        self.clock = clock
        self.sleep = sleep
        self.max_retries = max_retries
        self.max_pages = max_pages
        self.page_size = page_size

    def collect(self) -> KubernetesMetadataSnapshot:
        started = self.clock()
        if started.tzinfo is None or started.utcoffset() is None:
            raise ValueError("Kubernetes clock must be timezone-aware")
        resources: list[KubernetesObjectMetadata] = []
        errors: list[CollectionError] = []
        missing: list[str] = []
        observations: list[datetime | None] = []
        retries = 0
        verified_uid = None
        availability: dict[str, Literal["available", "absent", "unsupported"]] = {}
        resource_versions: dict[str, str] = {}
        try:
            discovered = self.reader.discover()
            for name in RESOURCE_CATALOG:
                family = (name.split("/")[0], name.rsplit("/", 1)[-1])
                other_version = any(
                    (other.split("/")[0], other.rsplit("/", 1)[-1]) == family
                    for other in discovered
                )
                availability[name] = (
                    "available"
                    if name in discovered
                    else "unsupported"
                    if other_version
                    else "absent"
                )
            ordered = [
                "v1/namespaces",
                *sorted(name for name in RESOURCE_CATALOG if name != "v1/namespaces"),
            ]
            for name in ordered:
                definition = RESOURCE_CATALOG[name]
                if availability[name] != "available":
                    if definition.required:
                        errors.append(
                            CollectionError(scope=self.cluster_resource_id, code="invalid-response")
                        )
                        missing.append(name)
                        if name == "v1/namespaces":
                            break
                    continue
                try:
                    items: list[KubernetesObjectMetadata] = []
                    token = None
                    tokens: set[str] = set()
                    version = None
                    identities: set[tuple[str | None, str]] = set()
                    for page_index in range(self.max_pages):
                        for attempt in range(self.max_retries + 1):
                            try:
                                page = self.reader.list_page(
                                    name, continue_token=token, page_size=self.page_size
                                )
                                break
                            except KubernetesReadError as error:
                                if (
                                    error.code not in {"throttled", "timeout", "unavailable"}
                                    or attempt == self.max_retries
                                ):
                                    raise
                                delay = (
                                    error.retry_after_seconds
                                    if error.retry_after_seconds is not None
                                    else 2**attempt
                                )
                                self.sleep(min(30, max(0, delay)))
                                retries += 1
                        if (
                            len(page.items) > self.page_size
                            or not page.resource_version
                            or (version is not None and version != page.resource_version)
                        ):
                            raise KubernetesReadError("invalid-response")
                        version = page.resource_version
                        if page.observed_at is not None and (
                            page.observed_at.tzinfo is None
                            or page.observed_at.utcoffset() is None
                            or page.observed_at > self.clock()
                        ):
                            raise KubernetesReadError("invalid-response")
                        observations.append(page.observed_at)
                        for raw in page.items:
                            item = project_metadata(name, raw)
                            key = (item.namespace, item.name)
                            if key in identities:
                                raise KubernetesReadError("identity-mismatch")
                            identities.add(key)
                            items.append(item)
                        if page.continue_token is None:
                            break
                        if (
                            not page.continue_token
                            or page.continue_token in tokens
                            or page_index == self.max_pages - 1
                        ):
                            raise KubernetesReadError("invalid-response")
                        tokens.add(page.continue_token)
                        token = page.continue_token
                    if name == "v1/namespaces":
                        namespace = next(
                            (item for item in items if item.name == "kube-system"), None
                        )
                        if namespace is None or namespace.uid != self.expected_cluster_uid:
                            raise KubernetesReadError("identity-mismatch")
                        verified_uid = namespace.uid
                    if version is not None:
                        resource_versions[name] = version
                    resources.extend(items)
                except (KubernetesReadError, ValidationError, TypeError, AttributeError) as error:
                    code = (
                        error.code if isinstance(error, KubernetesReadError) else "invalid-response"
                    )
                    errors.append(CollectionError(scope=self.cluster_resource_id, code=code))
                    missing.append(name)
                    if name == "v1/namespaces":
                        break
        except KubernetesReadError as error:
            errors.append(CollectionError(scope=self.cluster_resource_id, code=error.code))
        bindings, unresolved = _owner_bindings(resources)
        missing.extend(unresolved)
        nodes = [
            _node_identity(resource, self.azure_cluster, self.expected_node_resource_group)
            for resource in resources
            if resource.kind == "Node"
        ]
        if unresolved or any(node.state == "mismatch" for node in nodes):
            errors.append(CollectionError(scope=self.cluster_resource_id, code="identity-mismatch"))
        if any(node.state == "mismatch" for node in nodes):
            missing.append("node-provider-identity")
        ended = self.clock()
        if ended.tzinfo is None or ended.utcoffset() is None or ended < started:
            raise ValueError("invalid Kubernetes completion clock")
        state = (
            CollectionStatus.COMPLETE
            if not errors
            else CollectionStatus.PARTIAL
            if resources
            else CollectionStatus.FAILED
        )
        observed_at = (
            min(value for value in observations if value is not None)
            if observations and all(value is not None for value in observations)
            else None
        )
        receipt = CollectorResult(
            collector="kubernetes-metadata",
            status=state,
            requested_scope=[self.cluster_resource_id],
            completed_scope=[self.cluster_resource_id] if not errors else [],
            started_at=started,
            completed_at=ended,
            source_observed_at=observed_at,
            pagination_complete=not errors,
            retry_count=retries,
            errors=errors,
            missing_fields=sorted(set(missing)),
        )
        return KubernetesMetadataSnapshot(
            tenant_id=str(self.profile.scope.tenant_id),
            cluster_resource_id=self.cluster_resource_id,
            cluster_uid=verified_uid,
            generated_at=ended,
            collection=receipt,
            api_availability=availability,
            resources=sorted(
                resources,
                key=lambda item: (item.api_version, item.kind, item.namespace or "", item.name),
            ),
            nodes=sorted(nodes, key=lambda node: node.node_uid),
            workload_bindings=bindings,
            resource_versions=resource_versions,
        )
