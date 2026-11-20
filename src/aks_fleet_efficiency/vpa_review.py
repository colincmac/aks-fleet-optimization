"""Current-only VPA context and a narrowly scoped, non-predictive CPU comparison."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from math import isfinite
from typing import Annotated, Literal

from pydantic import Field

from aks_fleet_efficiency.controller_evidence import (
    ControllerEvidence,
    ControllerScope,
    ControllerWindow,
    ControllerWorkloadScope,
    _Clock,
    _SavedModel,
    _Token,
    qualify_controller_timeline,
)
from aks_fleet_efficiency.models import (
    VpaConfiguration,
    VpaContainerPolicy,
    VpaContainerRecommendation,
    VpaResourceValues,
)

type _Resource = Literal["cpu", "memory"]
_ObservedRequest = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class VpaScope(ControllerWorkloadScope):
    vpa_uid: _Token


class SingleContainerCpuBasis(_SavedModel):
    hpa_uid: _Token
    configuration_revision: _Token
    request_revision: _Token
    sole_container: _Token


class CurrentVpaEvidence(_SavedModel):
    schema_version: Literal["1.0"]
    scope: VpaScope
    source_status: Literal["complete", "partial", "denied"]
    observed_at: _Clock
    container: _Token
    request_cpu_mcpu: _ObservedRequest | None = None
    request_memory_mib: _ObservedRequest | None = None
    cpu_basis: SingleContainerCpuBasis | None = None
    vpa: VpaConfiguration


class VpaGenerationEvidence(_SavedModel):
    recommendation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: _Clock


@dataclass(frozen=True)
class VpaResourceContext:
    unit: Literal["mCPU", "MiB"]
    current_request: float | None
    lower: float
    target: float
    upper: float
    uncapped: float | None
    policy_minimum: float
    policy_maximum: float


@dataclass(frozen=True)
class VpaContext:
    scope: VpaScope
    container: str
    observed_at: datetime
    recommendation_age: timedelta | None
    cpu: VpaResourceContext | None
    memory: VpaResourceContext | None
    update_mode: Literal["Off"] = "Off"


@dataclass(frozen=True)
class CpuSensitivity:
    observed_at: datetime
    observed_utilization_percent: int
    unchanged_usage_utilization_percent: float


type _SensitivityBlocker = Literal[
    "missing_cpu_context",
    "unsupported_cpu_request_basis",
    "unverified_recommendation_generation",
    "missing_hpa_timeline",
    "hpa_scope_mismatch",
    "unqualified_hpa_timeline",
    "request_basis_mismatch",
    "non_finite_sensitivity",
]
type _ContextBlocker = Literal[
    "scope_mismatch",
    "incomplete_source",
    "invalid_observation_time",
    "unsupported_vpa",
    "missing_container_context",
]


@dataclass(frozen=True)
class VpaReview:
    context: VpaContext | None = None
    sensitivity: CpuSensitivity | None = None
    context_blocker: _ContextBlocker | None = None
    sensitivity_blocker: _SensitivityBlocker | None = None


def vpa_recommendation_digest(evidence: CurrentVpaEvidence) -> str:
    """Bind the normalized status and policy to the reviewed scope and request basis."""
    data = evidence.model_dump(
        mode="json", include={"scope", "container", "cpu_basis", "vpa", "schema_version"}
    )
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _resource_context(
    resource: _Resource,
    request: float | None,
    recommendation: VpaContainerRecommendation,
    policy: VpaContainerPolicy,
) -> VpaResourceContext | None:
    if resource not in (policy.controlled_resources or ()):
        return None

    def amount(value: VpaResourceValues | None) -> float | None:
        if value is None:
            return None
        return value.cpu_mcores if resource == "cpu" else value.memory_mib

    values = tuple(
        amount(item)
        for item in (
            recommendation.lower_bound,
            recommendation.target,
            recommendation.upper_bound,
            recommendation.uncapped_target,
            policy.min_allowed,
            policy.max_allowed,
        )
    )
    lower, target, upper, uncapped, minimum, maximum = values
    if (
        lower is None
        or target is None
        or upper is None
        or minimum is None
        or maximum is None
        or not (0 < lower <= target <= upper and 0 <= minimum <= target <= maximum)
    ):
        return None
    return VpaResourceContext(
        "mCPU" if resource == "cpu" else "MiB",
        request,
        lower,
        target,
        upper,
        uncapped,
        minimum,
        maximum,
    )


def review_current_vpa(
    evidence: CurrentVpaEvidence,
    *,
    expected_scope: VpaScope,
    as_of: datetime,
    max_age: timedelta,
    generation: VpaGenerationEvidence | None = None,
    hpa_evidence: ControllerEvidence | None = None,
    expected_hpa_scope: ControllerScope | None = None,
    reviewed_window: ControllerWindow | None = None,
) -> VpaReview:
    if as_of.utcoffset() is None or max_age < timedelta(0):
        raise ValueError("use a timezone-aware evaluation clock and nonnegative maximum age")
    if evidence.scope != expected_scope or evidence.vpa.uid != expected_scope.vpa_uid:
        return VpaReview(context_blocker="scope_mismatch")
    if evidence.source_status != "complete":
        return VpaReview(context_blocker="incomplete_source")
    if not timedelta(0) <= as_of - evidence.observed_at <= max_age:
        return VpaReview(context_blocker="invalid_observation_time")
    vpa = evidence.vpa
    if vpa.update_mode != "Off" or vpa.evidence_issues:
        return VpaReview(context_blocker="unsupported_vpa")
    policies = {policy.container_name: policy for policy in vpa.container_policies}
    policy = policies.get(evidence.container, policies.get("*"))
    recommendation = next(
        (item for item in vpa.recommendations if item.container_name == evidence.container), None
    )
    if policy is None or policy.mode != "Auto" or recommendation is None:
        return VpaReview(context_blocker="missing_container_context")
    cpu = _resource_context("cpu", evidence.request_cpu_mcpu, recommendation, policy)
    memory = _resource_context("memory", evidence.request_memory_mib, recommendation, policy)
    if cpu is None and memory is None:
        return VpaReview(context_blocker="missing_container_context")

    age = None
    if (
        generation is not None
        and generation.generated_at <= evidence.observed_at
        and generation.recommendation_digest == vpa_recommendation_digest(evidence)
    ):
        age = as_of - generation.generated_at
    context = VpaContext(evidence.scope, evidence.container, evidence.observed_at, age, cpu, memory)
    if cpu is None:
        return VpaReview(context, sensitivity_blocker="missing_cpu_context")
    basis = evidence.cpu_basis
    if basis is None or basis.sole_container != evidence.container:
        return VpaReview(context, sensitivity_blocker="unsupported_cpu_request_basis")
    if age is None or age > max_age:
        return VpaReview(context, sensitivity_blocker="unverified_recommendation_generation")
    if hpa_evidence is None or expected_hpa_scope is None or reviewed_window is None:
        return VpaReview(context, sensitivity_blocker="missing_hpa_timeline")
    if (
        expected_hpa_scope.workload_key != expected_scope.workload_key
        or expected_hpa_scope.hpa_uid != basis.hpa_uid
    ):
        return VpaReview(context, sensitivity_blocker="hpa_scope_mismatch")

    timeline = qualify_controller_timeline(
        hpa_evidence,
        expected_scope=expected_hpa_scope,
        reviewed_window=reviewed_window,
        as_of=as_of,
        max_age=max_age,
    )
    if timeline.status != "qualified":
        return VpaReview(context, sensitivity_blocker="unqualified_hpa_timeline")
    point = timeline.points[-1]
    signal, request = point.signal, point.request_mcpu_per_pod
    if (
        signal is None
        or request is None
        or signal.revision != (basis.configuration_revision, basis.request_revision)
        or request.value != cpu.current_request
        or point.observed_at > evidence.observed_at
    ):
        return VpaReview(context, sensitivity_blocker="request_basis_mismatch")
    result = signal.value * request.value / cpu.target
    if not isfinite(result):
        return VpaReview(context, sensitivity_blocker="non_finite_sensitivity")
    return VpaReview(context, CpuSensitivity(point.observed_at, signal.value, result))
