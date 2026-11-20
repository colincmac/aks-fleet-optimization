from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, model_validator

from aks_fleet_efficiency.advisory import ExperimentDimension
from aks_fleet_efficiency.artifacts import write_exclusive
from aks_fleet_efficiency.assessment import AssessmentFragments
from aks_fleet_efficiency.autoscaler_normalization import normalize_autoscaler_configuration
from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.catalog.models import CatalogModel, Digest, Text
from aks_fleet_efficiency.cost import Currency, Money
from aks_fleet_efficiency.experiments import (
    _markdown,
    _write_outcome_payloads,
    read_experiment_handoff_bundle,
    read_experiment_outcome_bundle,
)
from aks_fleet_efficiency.history import _read_verified_archive, _summary
from aks_fleet_efficiency.models import CollectionStatus, UtcDatetime
from aks_fleet_efficiency.workload_normalization import normalize_workload_inventory


def _decimal_quantity(value: object) -> object:
    if isinstance(value, (bool, float)):
        raise ValueError("quantities require decimal strings or Decimal values")
    return value


Quantity = Annotated[
    Decimal,
    BeforeValidator(_decimal_quantity),
    Field(ge=0, max_digits=30, decimal_places=12),
]
Ratio = Annotated[Quantity, Field(le=1)]
RequestCount = Annotated[int, Field(ge=0, le=10**12, strict=True)]


class EngineeringWindowObservation(CatalogModel):
    run_id: Digest
    window_start: UtcDatetime
    window_end: UtcDatetime
    source: Text
    observation_ref: Text
    coverage_complete: bool = Field(strict=True)
    request_count: RequestCount | None = None
    success_count: RequestCount | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> EngineeringWindowObservation:
        if self.window_end <= self.window_start:
            raise ValueError("engineering evidence requires an ordered window")
        if self.success_count is not None and (
            self.request_count is None or self.success_count > self.request_count
        ):
            raise ValueError("successful requests must be a subset of observed requests")
        return self


class EngineeringChangeRecord(CatalogModel):
    schema_version: Literal["1.0"]
    dimension: Literal["cpu_request"] = "cpu_request"
    tenant_id: UUID
    cluster_resource_id: Text
    cluster_uid: Text
    namespace_uid: Text
    workload_uid: Text
    hpa_uid: Text
    container: Text
    approval_ref: Text
    changed_at: UtcDatetime
    before: EngineeringWindowObservation
    after: EngineeringWindowObservation
    minimum_success_ratio: Ratio
    maximum_demand_change_ratio: Ratio
    owner_disposition: Literal["review", "retain_current_configuration", "rolled_back"]


class EngineeringCpuObservation(CatalogModel):
    run_id: Digest
    cpu_request_mcpu: float | None = None
    configuration_revision: Digest | None = None
    configuration_without_cpu_request: Digest | None = None
    ready_replicas: int | None = None
    available_replicas: int | None = None
    pending_pods: int | None = None


class EngineeringCpuOutcome(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    cluster_resource_id: Text
    cluster_uid: Text
    workload_uid: Text
    container: Text
    status: Literal["observed_change", "regression", "inconclusive"]
    before: EngineeringCpuObservation
    after: EngineeringCpuObservation
    before_service: EngineeringWindowObservation
    after_service: EngineeringWindowObservation
    minimum_success_ratio: Ratio
    maximum_demand_change_ratio: Ratio
    owner_disposition: Literal["review", "retain_current_configuration", "rolled_back"]
    reason_codes: list[Text]


def _read_cpu_window(
    directory: Path, record: EngineeringChangeRecord, window: EngineeringWindowObservation
) -> EngineeringCpuObservation:
    archive, assessment, config = _read_verified_archive(directory, tenant_id=record.tenant_id)
    run = _summary(archive, assessment, config)
    if run.run_id != window.run_id:
        raise ValueError("engineering observation must identify the original verified run")
    result = EngineeringCpuObservation(run_id=run.run_id)
    if (run.window_start, run.window_end) != (window.window_start, window.window_end):
        return result
    if len(assessment.snapshot.clusters) != 1:
        return result
    cluster = assessment.snapshot.clusters[0]
    if (cluster.resource_id, cluster.uid) != (record.cluster_resource_id, record.cluster_uid):
        return result
    fragments = AssessmentFragments.model_validate_json(archive.payloads["fragments.json"])
    if len(fragments.kubernetes) != 1:
        return result
    metadata = fragments.kubernetes[0]
    at = metadata.collection.source_observed_at
    fingerprints = [
        item.uid
        for item in metadata.resources
        if item.api_version == "v1" and item.kind == "Namespace" and item.name == "kube-system"
    ]
    if (
        (metadata.cluster_resource_id, metadata.cluster_uid) != (cluster.resource_id, cluster.uid)
        or fingerprints != [record.cluster_uid]
        or metadata.collection.collector != "kubernetes-metadata"
        or metadata.collection.requested_scope != [cluster.resource_id]
        or metadata.collection.status != CollectionStatus.COMPLETE
        or metadata.collection.completed_scope != [cluster.resource_id]
        or at is None
        or not window.window_start <= at <= metadata.generated_at <= window.window_end
        or run.generated_at < window.window_end
        or (run.generated_at - at).total_seconds()
        > config.thresholds.maximum_evidence_age_hours * 3600
    ):
        return result
    workloads, membership, _ = normalize_workload_inventory(metadata)
    members = [item for item in membership if item.workload_uid == record.workload_uid]
    if len(members) != 1 or members[0].namespace_uid != record.namespace_uid:
        return result
    workload = next((item for item in workloads if item.uid == record.workload_uid), None)
    if workload is None or len(workload.containers) != 1:
        return result
    container = workload.containers[0]
    controllers = normalize_autoscaler_configuration(metadata, workload)
    if (
        container.name != record.container
        or not container.resources.cpu_request_observed
        or container.resources.request_cpu_mcores is None
        or controllers.issues
        or not (controllers.hpa_observed and controllers.vpa_observed and controllers.keda_observed)
        or len(controllers.hpas) != 1
        or controllers.hpas[0].uid != record.hpa_uid
        or any(vpa.update_mode != "Off" for vpa in controllers.vpas)
        or controllers.kedas
    ):
        return result
    originals = {item.uid: item for item in metadata.resources}
    pod = originals[members[0].pod_uid]
    target = originals[record.workload_uid]
    if pod.status.get("phase") != "Running":
        return result
    pod_spec = deepcopy(pod.spec)
    pod_spec.pop("nodeName", None)
    containers = pod_spec.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        return result
    admitted = containers[0]
    resources = admitted.get("resources") if isinstance(admitted, dict) else None
    requests = resources.get("requests") if isinstance(resources, dict) else None
    if not isinstance(requests, dict) or "cpu" not in requests:
        return result
    spec = {
        "pod": pod_spec,
        "workload": target.spec,
        "controllers": {
            uid: originals[uid].spec
            for uid in [record.hpa_uid, *(vpa.uid for vpa in controllers.vpas)]
        },
    }
    result.cpu_request_mcpu = container.resources.request_cpu_mcores
    result.configuration_revision = digest_json(spec)
    requests.pop("cpu")
    result.configuration_without_cpu_request = digest_json(spec)
    for field, attr in (
        ("readyReplicas", "ready_replicas"),
        ("availableReplicas", "available_replicas"),
    ):
        value = target.status.get(field)
        if type(value) is int and value >= 0:
            setattr(result, attr, value)
    if set(members_item.pod_uid for members_item in members) == {
        uid for uid, owner in metadata.workload_bindings.items() if owner == record.workload_uid
    } and all(
        item.kind != "Pod"
        or item.namespace != target.namespace
        or metadata.workload_bindings.get(item.uid) is not None
        for item in metadata.resources
    ):
        result.pending_pods = 0
    return result


def review_cpu_request_outcome(
    before: Path, after: Path, *, record: EngineeringChangeRecord
) -> EngineeringCpuOutcome:
    """Compare approved saved engineering evidence without invoking the financial adapter."""
    record = EngineeringChangeRecord.model_validate(record.model_dump())
    old, new = record.before, record.after
    prior = _read_cpu_window(before, record, old)
    followup = _read_cpu_window(after, record, new)
    reasons = []
    if not (
        old.window_end <= record.changed_at <= new.window_start
        and old.window_end - old.window_start == new.window_end - new.window_start
        and old.source == new.source
        and old.observation_ref != new.observation_ref
    ):
        reasons.append("incompatible_observation_windows")
    if prior.cpu_request_mcpu is None or followup.cpu_request_mcpu is None:
        reasons.append("unqualified_request_observations")
    elif prior.configuration_without_cpu_request != followup.configuration_without_cpu_request:
        reasons.append("other_configuration_changed")
    if (
        not old.request_count
        or not new.request_count
        or Decimal(abs(new.request_count - old.request_count))
        > record.maximum_demand_change_ratio * old.request_count
    ):
        reasons.append("incompatible_demand")
    if old.success_count is None or new.success_count is None:
        reasons.append("missing_slo_observation")
    if not (old.coverage_complete and new.coverage_complete):
        reasons.append("incomplete_service_observation")
    if record.owner_disposition != "review":
        reasons.append("owner_disposition_preserved")

    status: Literal["observed_change", "regression", "inconclusive"] = "inconclusive"
    if (
        not reasons
        and old.request_count
        and new.request_count
        and old.success_count is not None
        and new.success_count is not None
    ):
        if old.success_count < record.minimum_success_ratio * old.request_count:
            reasons.append("baseline_below_owner_slo")
        elif new.success_count < record.minimum_success_ratio * new.request_count:
            status = "regression"
            reasons.append("followup_below_owner_slo")
        elif prior.cpu_request_mcpu == followup.cpu_request_mcpu:
            reasons.append("no_cpu_request_change")
        else:
            status = "observed_change"
    return EngineeringCpuOutcome(
        tenant_id=record.tenant_id,
        cluster_resource_id=record.cluster_resource_id,
        cluster_uid=record.cluster_uid,
        workload_uid=record.workload_uid,
        container=record.container,
        status=status,
        before=prior,
        after=followup,
        before_service=old,
        after_service=new,
        minimum_success_ratio=record.minimum_success_ratio,
        maximum_demand_change_ratio=record.maximum_demand_change_ratio,
        owner_disposition=record.owner_disposition,
        reason_codes=reasons,
    )


class ResourceChange(CatalogModel):
    status: Literal["observed", "declared", "blocked", "inconclusive"]
    dimension: ExperimentDimension
    unit: Text
    before: Quantity | None = None
    after: Quantity | None = None
    before_assessment_digest: Digest | None = None
    after_assessment_digest: Digest | None = None
    demand_comparable: bool = Field(strict=True)
    reason_codes: list[Text] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_change(self) -> ResourceChange:
        evidence = (
            self.before,
            self.after,
            self.before_assessment_digest,
            self.after_assessment_digest,
        )
        if self.status == "observed":
            if any(value is None for value in evidence) or not self.demand_comparable:
                raise ValueError("Observed resource change requires comparable complete evidence")
            if self.reason_codes:
                raise ValueError("Observed resource change cannot retain reason codes")
        elif self.status == "declared":
            if any(value is None for value in evidence):
                raise ValueError("Declared resource change requires both values and references")
        elif not self.reason_codes:
            raise ValueError("Unobserved resource change requires explicit reasons")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Resource change reasons must be distinct")
        return self


class CapacityEffect(CatalogModel):
    status: Literal["observed", "declared", "blocked", "not_supplied"]
    before_node_hours: Quantity | None = None
    after_node_hours: Quantity | None = None
    evidence_digest: Digest | None = None
    reason_codes: list[Text] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_capacity(self) -> CapacityEffect:
        evidence = (self.before_node_hours, self.after_node_hours, self.evidence_digest)
        if self.status in {"observed", "declared"}:
            if any(value is None for value in evidence):
                raise ValueError(
                    f"{self.status.capitalize()} capacity requires before/after node-hours "
                    "and evidence"
                )
            if self.reason_codes:
                raise ValueError("Reported capacity cannot retain reason codes")
        elif self.status == "blocked":
            if not self.reason_codes:
                raise ValueError("Blocked capacity requires explicit reasons")
        elif any(value is not None for value in evidence) or self.reason_codes:
            raise ValueError("Unsupplied capacity cannot retain evidence or reasons")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Capacity reasons must be distinct")
        return self


class FinancialEffect(CatalogModel):
    status: Literal["modeled", "observed", "blocked", "not_supplied"]
    amount: Money | None = None
    currency: Currency | None = None
    evidence_digest: Digest | None = None
    method_reference: Text | None = None
    reason_codes: list[Text] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_effect(self) -> FinancialEffect:
        evidence = (self.amount, self.currency, self.evidence_digest, self.method_reference)
        if self.status in {"modeled", "observed"}:
            if any(value is None for value in evidence):
                raise ValueError("Financial effects require amount, currency, evidence and method")
            if self.reason_codes:
                raise ValueError("Observed financial effects cannot retain reason codes")
        elif self.status == "blocked":
            if not self.reason_codes:
                raise ValueError("Blocked financial effects require explicit reasons")
        elif any(value is not None for value in evidence) or self.reason_codes:
            raise ValueError("Unsupplied financial effects cannot retain evidence or reasons")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Financial effect reasons must be distinct")
        return self


class ExperimentValueOutcome(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["post-experiment-value-outcome"] = "post-experiment-value-outcome"
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    experiment_digest: Digest
    evaluated_at: UtcDatetime
    execution_outcome: Literal[
        "completed", "aborted", "rolled_back", "inconclusive", "not_executed"
    ]
    execution_reference: Text
    engineering: ResourceChange
    capacity: CapacityEffect
    modeled_cost_avoidance: FinancialEffect
    reconciled_bill_effect: FinancialEffect
    reviewer_reference: Text
    estimated_monthly_savings: None = None
    engineering_order_changed: Literal[False] = False
    notice: Literal[
        "Post-experiment evidence layers remain separate; request changes are not capacity "
        "release, modeled avoidance is not bill savings, and bill changes do not prove causality."
    ] = (
        "Post-experiment evidence layers remain separate; request changes are not capacity "
        "release, modeled avoidance is not bill savings, and bill changes do not prove causality."
    )

    @model_validator(mode="after")
    def validate_outcome(self) -> ExperimentValueOutcome:
        if self.modeled_cost_avoidance.status == "observed":
            raise ValueError("Modeled cost avoidance cannot be labeled observed")
        if self.reconciled_bill_effect.status == "modeled":
            raise ValueError("Reconciled bill effects cannot be labeled modeled")
        if self.execution_outcome != "completed" and (
            self.modeled_cost_avoidance.status == "modeled"
            or self.reconciled_bill_effect.status == "observed"
        ):
            raise ValueError("Financial effects require completed execution")
        return self


class ExperimentValueOutcomeRequest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    engineering: ResourceChange
    capacity: CapacityEffect
    modeled_cost_avoidance: FinancialEffect
    reconciled_bill_effect: FinancialEffect
    reviewer_reference: Text


def validate_experiment_value_outcome(
    experiment_directory: Path,
    outcome_directory: Path,
    *,
    request: ExperimentValueOutcomeRequest,
    evaluated_at: UtcDatetime,
) -> ExperimentValueOutcome:
    request = ExperimentValueOutcomeRequest.model_validate(request.model_dump())
    experiment_manifest, handoff = read_experiment_handoff_bundle(experiment_directory)
    _, execution = read_experiment_outcome_bundle(outcome_directory)
    if (
        execution.experiment_digest != experiment_manifest.experiment_digest
        or execution.tenant_id != handoff.tenant_id
        or execution.cluster_resource_id != handoff.cluster_resource_id
        or execution.cluster_uid != handoff.cluster_uid
        or execution.finding_id != handoff.finding_id
        or execution.dimension != handoff.dimension
    ):
        raise ValueError("Value outcome requires exact experiment and execution bindings")
    if evaluated_at < execution.recorded_at:
        raise ValueError("Value outcome evaluation cannot precede the execution record")
    if request.engineering.dimension != handoff.dimension:
        raise ValueError("Engineering outcome must preserve the selected experiment dimension")
    if request.engineering.status == "observed" or request.capacity.status == "observed":
        raise ValueError("Observed engineering and capacity results require original evidence")
    if request.engineering.status == "declared" and (
        request.engineering.before_assessment_digest != execution.before_assessment_digest
        or request.engineering.after_assessment_digest != execution.after_assessment_digest
    ):
        raise ValueError("Engineering outcome must bind the declared before/after assessments")
    if request.capacity.status == "declared" and execution.outcome != "completed":
        raise ValueError("Declared capacity effects require completed execution")
    if (
        request.modeled_cost_avoidance.status == "modeled"
        or request.reconciled_bill_effect.status == "observed"
    ):
        raise ValueError("Positive financial effects require a qualified financial adapter")
    return ExperimentValueOutcome(
        tenant_id=handoff.tenant_id,
        cluster_resource_id=handoff.cluster_resource_id,
        cluster_uid=handoff.cluster_uid,
        experiment_digest=experiment_manifest.experiment_digest,
        evaluated_at=evaluated_at,
        execution_outcome=execution.outcome,
        execution_reference=execution.execution_reference,
        engineering=request.engineering,
        capacity=request.capacity,
        modeled_cost_avoidance=request.modeled_cost_avoidance,
        reconciled_bill_effect=request.reconciled_bill_effect,
        reviewer_reference=request.reviewer_reference,
    )


def render_experiment_value_outcome_markdown(outcome: ExperimentValueOutcome) -> str:
    engineering = outcome.engineering
    capacity = outcome.capacity
    modeled = outcome.modeled_cost_avoidance
    reconciled = outcome.reconciled_bill_effect
    lines = [
        "# Experiment Value Outcome",
        "",
        f"Execution outcome: **{outcome.execution_outcome}**.",
        "",
        f"Experiment digest: `{outcome.experiment_digest}`.",
        "",
        "## Engineering",
        "",
        f"- Status: **{engineering.status}**",
        f"- Dimension: **{engineering.dimension}**",
        f"- Before: {engineering.before if engineering.before is not None else 'unknown'} "
        f"{_markdown(engineering.unit)}",
        f"- After: {engineering.after if engineering.after is not None else 'unknown'} "
        f"{_markdown(engineering.unit)}",
        "",
        "## Capacity",
        "",
        f"- Status: **{capacity.status}**",
        f"- Before node-hours: "
        f"{capacity.before_node_hours if capacity.before_node_hours is not None else 'unknown'}",
        f"- After node-hours: "
        f"{capacity.after_node_hours if capacity.after_node_hours is not None else 'unknown'}",
        "",
        "## Modeled Cost Avoidance",
        "",
        f"- Status: **{modeled.status}**",
        f"- Amount: {modeled.amount if modeled.amount is not None else 'unknown'} "
        f"{modeled.currency or ''}",
        "",
        "## Reconciled Bill Effect",
        "",
        f"- Status: **{reconciled.status}**",
        f"- Amount: {reconciled.amount if reconciled.amount is not None else 'unknown'} "
        f"{reconciled.currency or ''}",
        "",
        "## Review Boundary",
        "",
        f"- Reviewer reference: `{_markdown(outcome.reviewer_reference)}`",
        f"- {outcome.notice}",
        "- Declared values and comparability have not been verified against source records.",
        "- Estimated monthly savings remains null.",
    ]
    return "\n".join(lines) + "\n"


def write_experiment_value_outcome_bundle(directory: Path, outcome: ExperimentValueOutcome) -> None:
    outcome = ExperimentValueOutcome.model_validate(outcome.model_dump())
    digests = _write_outcome_payloads(
        directory,
        "value",
        outcome.model_dump_json(indent=2),
        render_experiment_value_outcome_markdown(outcome),
    )
    write_exclusive(
        directory / "manifest.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "execution_outcome": outcome.execution_outcome,
                "experiment_digest": outcome.experiment_digest,
                "files": digests,
                "estimated_monthly_savings": None,
            },
            indent=2,
            sort_keys=True,
        ),
    )
