from __future__ import annotations

import json
import re
from typing import Literal

from aks_fleet_efficiency.catalog.models import QueryId
from aks_fleet_efficiency.config import MetricSourceProfile
from aks_fleet_efficiency.models import MetricEntity

type MetricLabelEntityKind = Literal[
    "container",
    "workload_container",
    "unresolved_container",
    "node",
    "node_pool",
    "workload",
    "hpa",
]


def effective_label_mapping(
    source: MetricSourceProfile, query_id: QueryId | None = None
) -> dict[str, str]:
    override = source.query_label_mappings.get(query_id, {}) if query_id is not None else {}
    return {str(name): value for name, value in (source.label_mapping | override).items()}


def required_metric_labels(kind: MetricLabelEntityKind) -> set[str]:
    required = {"cluster_resource_id"}
    if kind == "unresolved_container":
        required.update({"namespace", "pod", "container"})
    if kind in {"container", "workload", "workload_container", "hpa"}:
        required.update({"namespace", "workload_kind", "workload"})
        if kind in {"container", "workload_container"}:
            required.add("container")
    return required


def validate_metric_label_mapping(mapping: dict[str, str], kind: MetricLabelEntityKind) -> None:
    required = required_metric_labels(kind)
    if not required <= set(mapping):
        raise ValueError("Metric source is missing required label mappings")
    if any(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name) is None for name in mapping.values()):
        raise ValueError("Metric source label names must be valid Prometheus identifiers")
    reserved = {
        "container": {"workload_uid", "pod_uid"},
        "workload_container": {"workload_uid", "membership_digest"},
        "workload": {"workload_uid"},
        "hpa": {"workload_uid", "hpa_uid"},
        "node": {"node_resource_id", "node_uid"},
        "node_pool": {"node_resource_id", "node_uid"},
        "unresolved_container": set(),
    }[kind]
    selected = [mapping[name] for name in required]
    if len(set(selected)) != len(selected) or set(selected) & reserved:
        raise ValueError("Metric label mapping collides with required identity labels")


def metric_labels(
    entity: MetricEntity, source: MetricSourceProfile, query_id: QueryId | None = None
) -> dict[str, str]:
    mapping = effective_label_mapping(source, query_id)
    validate_metric_label_mapping(mapping, entity.kind)
    values = {mapping["cluster_resource_id"]: entity.cluster_resource_id}
    if entity.kind == "unresolved_container":
        for field in ["namespace", "pod", "container"]:
            values[mapping[field]] = str(getattr(entity, field))
    elif entity.kind in {"container", "workload", "workload_container", "hpa"}:
        for field in ["namespace", "workload_kind", "workload"]:
            values[mapping[field]] = str(getattr(entity, field))
        values["workload_uid"] = str(entity.workload_uid)
        if entity.kind == "hpa":
            values["hpa_uid"] = str(entity.hpa_uid)
        if entity.kind in {"container", "workload_container"}:
            values[mapping["container"]] = str(entity.container)
            if entity.kind == "container":
                values["pod_uid"] = str(entity.pod_uid)
            else:
                values["membership_digest"] = str(entity.membership_digest)
    else:
        values["node_resource_id"] = str(entity.node_resource_id)
        values["node_uid"] = str(entity.node_uid)
    expected = (
        4
        if entity.kind == "unresolved_container"
        else 7
        if entity.kind in {"container", "workload_container"}
        else 6
        if entity.kind == "hpa"
        else 5
        if entity.kind == "workload"
        else 3
    )
    if len(values) != expected:
        raise ValueError("Metric label mapping collides with required identity labels")
    return values


def render_query(expression: str, labels: dict[str, str], step_seconds: int) -> str:
    selector = ",".join(f"{name}={json.dumps(value)}" for name, value in sorted(labels.items()))
    return expression.replace("__scope__", selector).replace("__step__", str(step_seconds))
