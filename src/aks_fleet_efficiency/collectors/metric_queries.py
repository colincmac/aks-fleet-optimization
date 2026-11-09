from __future__ import annotations

import json
import re

from aks_fleet_efficiency.config import MetricSourceProfile
from aks_fleet_efficiency.models import MetricEntity


def metric_labels(entity: MetricEntity, source: MetricSourceProfile) -> dict[str, str]:
    mapping = {str(name): value for name, value in source.label_mapping.items()}
    required = {"cluster_resource_id"}
    if entity.kind == "unresolved_container":
        required.update({"namespace", "pod", "container"})
    if entity.kind in {"container", "workload", "workload_container", "hpa"}:
        required.update({"namespace", "workload_kind", "workload"})
        if entity.kind in {"container", "workload_container"}:
            required.add("container")
    if not required <= set(mapping):
        raise ValueError("Metric source is missing required label mappings")
    if any(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name) is None for name in mapping.values()):
        raise ValueError("Metric source label names must be valid Prometheus identifiers")
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
