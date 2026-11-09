from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256

from pydantic import JsonValue

from aks_fleet_efficiency.models import (
    AutoscalerOwnerReference,
    HpaConfiguration,
    HpaMetricSignal,
    KedaConfiguration,
    KedaTrigger,
    KubernetesMetadataSnapshot,
    KubernetesObjectMetadata,
    VpaConfiguration,
    VpaContainerPolicy,
    VpaContainerRecommendation,
    VpaResourceValues,
    WorkloadAutoscalerConfiguration,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.workload_normalization import _quantity


def _api_observed(metadata: KubernetesMetadataSnapshot, key: str, kind: str) -> bool:
    state = metadata.api_availability.get(key)
    if state == "absent":
        return not any(item.kind == kind for item in metadata.resources)
    return state == "available" and bool(metadata.resource_versions.get(key))


def _hpa(resource: KubernetesObjectMetadata) -> HpaConfiguration:
    raw_metrics = resource.spec.get("metrics")
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise ValueError("explicit HPA metrics are required")
    signals = []
    for metric in raw_metrics:
        if not isinstance(metric, dict):
            raise ValueError("invalid HPA metric")
        metric_type = metric.get("type")
        if not isinstance(metric_type, str) or metric_type not in {
            "Resource",
            "ContainerResource",
            "External",
            "Pods",
            "Object",
        }:
            raise ValueError("unsupported HPA metric type")
        body = metric.get(metric_type[0].lower() + metric_type[1:])
        if not isinstance(body, dict):
            raise ValueError("explicit HPA target is required")
        target = body.get("target")
        if not isinstance(target, dict):
            raise ValueError("explicit HPA target is required")
        target_type = target.get("type")
        field = (
            {
                "Utilization": "averageUtilization",
                "AverageValue": "averageValue",
                "Value": "value",
            }.get(target_type)
            if isinstance(target_type, str)
            else None
        )
        if field is None or set(target) != {"type", field}:
            raise ValueError("ambiguous HPA metric target")
        if target_type != "Utilization":
            quantity = _quantity(target[field], Decimal(1), "HPA target")
            if quantity is None or quantity <= 0:
                raise ValueError("absolute HPA targets require a positive quantity")
        signals.append(
            HpaMetricSignal.model_validate(
                {
                    "metric_type": metric_type,
                    "resource": body.get("name")
                    if metric_type in {"Resource", "ContainerResource"}
                    else None,
                    "container": body.get("container")
                    if metric_type == "ContainerResource"
                    else None,
                    "target_type": target_type,
                    "average_utilization": target[field] if target_type == "Utilization" else None,
                    "target_value": target[field] if target_type != "Utilization" else None,
                }
            )
        )
    return HpaConfiguration.model_validate(
        {
            "uid": resource.uid,
            "name": resource.name,
            "metrics": sorted(signals, key=lambda item: item.model_dump_json()),
            "min_replicas": resource.spec.get("minReplicas"),
            "max_replicas": resource.spec.get("maxReplicas"),
            "current_replicas": resource.status.get("currentReplicas"),
            "desired_replicas": resource.status.get("desiredReplicas"),
            "owner_references": [
                AutoscalerOwnerReference.model_validate(
                    {
                        "api_version": owner.get("apiVersion"),
                        "kind": owner.get("kind"),
                        "name": owner.get("name"),
                        "uid": owner.get("uid"),
                        "controller": owner.get("controller"),
                    }
                )
                for owner in resource.owner_references
            ],
        }
    )


def _vpa_values(value: JsonValue) -> VpaResourceValues:
    if not isinstance(value, dict) or set(value) - {"cpu", "memory"}:
        raise ValueError("explicit allowlisted VPA resource quantities are required")
    return VpaResourceValues(
        cpu_mcores=_quantity(value.get("cpu"), Decimal(1000), "VPA CPU"),
        memory_mib=_quantity(value.get("memory"), Decimal(1) / Decimal(1048576), "VPA memory"),
    )


def _vpa(resource: KubernetesObjectMetadata) -> VpaConfiguration:
    update = resource.spec.get("updatePolicy")
    mode = update.get("updateMode") if isinstance(update, dict) else None
    resource_policy = resource.spec.get("resourcePolicy")
    policies = (
        resource_policy.get("containerPolicies") if isinstance(resource_policy, dict) else None
    )
    parsed = []
    evidence_issues: list[str] = []
    if mode != "Off" and (not isinstance(policies, list) or not policies):
        raise ValueError("explicit VPA policies are required")
    if policies is not None:
        if not isinstance(policies, list):
            raise ValueError("invalid VPA container policies")
        for policy in policies:
            if not isinstance(policy, dict):
                raise ValueError("invalid VPA container policy")
            parsed.append(
                VpaContainerPolicy.model_validate(
                    {
                        "container_name": policy.get("containerName"),
                        "mode": policy.get("mode"),
                        "controlled_resources": policy.get("controlledResources"),
                        "controlled_values": policy.get("controlledValues"),
                    }
                )
            )
            try:
                if "minAllowed" in policy:
                    parsed[-1].min_allowed = _vpa_values(policy["minAllowed"])
                if "maxAllowed" in policy:
                    parsed[-1].max_allowed = _vpa_values(policy["maxAllowed"])
            except ValueError:
                evidence_issues.append("unsupported_vpa_bounds")
    recommendations = []
    raw = resource.status.get("recommendation")
    if raw is not None:
        try:
            if not isinstance(raw, dict):
                raise ValueError("invalid VPA recommendation")
            containers = raw.get("containerRecommendations")
            if not isinstance(containers, list) or not containers:
                raise ValueError("explicit VPA container recommendations are required")
            for item in containers:
                if not isinstance(item, dict):
                    raise ValueError("invalid VPA container recommendation")
                recommendations.append(
                    VpaContainerRecommendation.model_validate(
                        {
                            "container_name": item.get("containerName"),
                            "target": _vpa_values(item.get("target")),
                            "lower_bound": _vpa_values(item.get("lowerBound")),
                            "upper_bound": _vpa_values(item.get("upperBound")),
                            "uncapped_target": _vpa_values(item["uncappedTarget"])
                            if "uncappedTarget" in item
                            else None,
                        }
                    )
                )
            if len({item.container_name for item in recommendations}) != len(recommendations):
                raise ValueError("duplicate VPA recommendation containers")
        except ValueError:
            recommendations = []
            evidence_issues.append("unsupported_vpa_recommendation")
    return VpaConfiguration.model_validate(
        {
            "uid": resource.uid,
            "name": resource.name,
            "update_mode": mode,
            "container_policies": sorted(parsed, key=lambda item: item.container_name),
            "recommendations": sorted(recommendations, key=lambda item: item.container_name),
            "evidence_issues": sorted(set(evidence_issues)),
        }
    )


def _keda(resource: KubernetesObjectMetadata) -> KedaConfiguration:
    raw = resource.spec.get("triggers")
    if not isinstance(raw, list) or not raw:
        raise ValueError("explicit KEDA trigger types are required")
    triggers = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid KEDA trigger")
        triggers.append(
            KedaTrigger.model_validate(
                {"type": item.get("type"), "metric_type": item.get("metricType")}
            )
        )
    return KedaConfiguration.model_validate(
        {
            "uid": resource.uid,
            "name": resource.name,
            "triggers": sorted(triggers, key=lambda item: item.model_dump_json()),
            "min_replicas": resource.spec.get("minReplicaCount"),
            "max_replicas": resource.spec.get("maxReplicaCount"),
            "polling_interval_seconds": resource.spec.get("pollingInterval"),
            "cooldown_period_seconds": resource.spec.get("cooldownPeriod"),
            "generated_hpa_name": resource.status.get("hpaName"),
        }
    )


def _available_replicas(
    metadata: KubernetesMetadataSnapshot, workload: WorkloadSnapshot
) -> int | None:
    for item in metadata.resources:
        if item.uid == workload.uid and item.kind == "Deployment":
            count = item.status.get("availableReplicas")
            if count is None:
                return None
            if type(count) is not int or count < 0:
                raise ValueError("current available replica count must be a nonnegative integer")
            return count
    return None


def _replica_constraints(
    metadata: KubernetesMetadataSnapshot, workload: WorkloadSnapshot
) -> list[str] | None:
    pods = [
        item
        for item in metadata.resources
        if item.kind == "Pod" and metadata.workload_bindings.get(item.uid) == workload.uid
    ]
    if len(pods) != workload.replicas or any(
        not isinstance(pod.spec.get("initContainers"), list)
        or not isinstance(pod.spec.get("overhead"), dict)
        for pod in pods
    ):
        return None
    issues = {
        f"unsupported_replica_{field}"
        for pod in pods
        for field in (
            "nodeSelector",
            "affinity",
            "topologySpreadConstraints",
            "tolerations",
            "volumes",
            "runtimeClassName",
            "priorityClassName",
            "initContainers",
            "overhead",
        )
        if pod.spec.get(field)
    }
    if any(pod.spec.get("schedulerName") not in {None, "default-scheduler"} for pod in pods):
        issues.add("unsupported_replica_scheduler")
    return sorted(issues)


def normalize_autoscaler_configuration(
    metadata: KubernetesMetadataSnapshot, workload: WorkloadSnapshot
) -> WorkloadAutoscalerConfiguration:
    namespaces = [
        item.uid
        for item in metadata.resources
        if item.kind == "Namespace" and item.name == workload.namespace
    ]
    configuration = WorkloadAutoscalerConfiguration.model_validate(
        {
            "cluster_resource_id": metadata.cluster_resource_id,
            "cluster_uid": metadata.cluster_uid,
            "namespace": workload.namespace,
            "namespace_uid": namespaces[0] if len(namespaces) == 1 else None,
            "workload_uid": workload.uid,
            "target_api_version": "apps/v1",
            "target_kind": workload.kind,
            "target_name": workload.name,
            "observed_at": metadata.generated_at,
            "hpa_observed": _api_observed(
                metadata, "autoscaling/v2/horizontalpodautoscalers", "HorizontalPodAutoscaler"
            ),
            "vpa_observed": _api_observed(
                metadata, "autoscaling.k8s.io/v1/verticalpodautoscalers", "VerticalPodAutoscaler"
            ),
            "keda_observed": _api_observed(
                metadata, "keda.sh/v1alpha1/scaledobjects", "ScaledObject"
            )
            and _api_observed(metadata, "keda.sh/v1alpha1/scaledjobs", "ScaledJob"),
            "workload_available_replicas": _available_replicas(metadata, workload),
            "replica_constraint_issues": _replica_constraints(metadata, workload),
            "replica_pod_configuration_digest": sha256(
                json.dumps(
                    [
                        {"pod_uid": item.uid, "spec": item.spec}
                        for item in sorted(metadata.resources, key=lambda item: item.uid)
                        if item.kind == "Pod"
                        and metadata.workload_bindings.get(item.uid) == workload.uid
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        }
    )
    for resource in sorted(metadata.resources, key=lambda item: item.uid):
        if resource.namespace != workload.namespace or resource.kind not in {
            "HorizontalPodAutoscaler",
            "VerticalPodAutoscaler",
            "ScaledObject",
        }:
            continue
        hpa = resource.kind == "HorizontalPodAutoscaler"
        keda = resource.kind == "ScaledObject"
        target: JsonValue = resource.spec.get("scaleTargetRef" if hpa or keda else "targetRef")
        if not isinstance(target, dict):
            configuration.issues.append("ambiguous_autoscaler_target")
            continue
        name, kind = target.get("name"), target.get("kind")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(kind, str)
            or not kind.strip()
        ):
            configuration.issues.append("ambiguous_autoscaler_target")
            continue
        if name != workload.name or kind != workload.kind:
            continue
        if target != {"apiVersion": "apps/v1", "kind": workload.kind, "name": workload.name}:
            configuration.issues.append("ambiguous_autoscaler_target")
            continue
        try:
            if hpa:
                if resource.api_version != "autoscaling/v2":
                    raise ValueError("unsupported HPA API version")
                configuration.hpas.append(_hpa(resource))
            elif keda:
                if resource.api_version != "keda.sh/v1alpha1":
                    raise ValueError("unsupported KEDA API version")
                configuration.kedas.append(_keda(resource))
            else:
                if resource.api_version != "autoscaling.k8s.io/v1":
                    raise ValueError("unsupported VPA API version")
                configuration.vpas.append(_vpa(resource))
        except ValueError:
            configuration.issues.append(
                "unsupported_hpa_configuration"
                if hpa
                else "unsupported_keda_configuration"
                if keda
                else "unsupported_vpa_configuration"
            )
    configuration.issues = sorted(set(configuration.issues))
    return WorkloadAutoscalerConfiguration.model_validate(configuration.model_dump())
