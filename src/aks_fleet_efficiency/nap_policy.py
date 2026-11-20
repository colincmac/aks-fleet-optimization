from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from croniter import CroniterBadCronError, CroniterBadDateError, croniter
from pydantic import BaseModel, ConfigDict, Field

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.models import CollectorResult, KubernetesMetadataSnapshot, UtcDatetime
from aks_fleet_efficiency.node_history import Digest, Reference, _receipt_gaps, _utc

DisruptionReason = Literal["Empty", "Underutilized", "Drifted", "Unhealthy"]
REASONS: tuple[DisruptionReason, ...] = ("Empty", "Underutilized", "Drifted", "Unhealthy")
MAXIMUM_NAP_POLICY_BYTES = 32 * 1024 * 1024


class _PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SuppliedNapBudget(_PolicyModel):
    nodes: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
    reasons: tuple[DisruptionReason, ...] | None = Field(default=None, max_length=4)
    schedule: Annotated[str, Field(strict=True, min_length=1, max_length=128)] | None = None
    duration: Annotated[str, Field(strict=True, min_length=1, max_length=64)] | None = None


class NapPolicyInput(_PolicyModel):
    schema_version: Literal["1.0"] = "1.0"
    reference: Literal["azure-v1.15.2/karpenter-v1.15.1"] = "azure-v1.15.2/karpenter-v1.15.1"
    tenant_id: UUID
    cluster_resource_id: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    cluster_uid: Reference
    nodepool_uid: Reference
    object_version: Reference | None = None
    generation: Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)] | None = None
    observed_at: UtcDatetime | None = None
    collection: CollectorResult | None = None
    supply_mode: Literal["static", "dynamic", "unknown"]
    replicas: Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)] | None = None
    node_count: Annotated[int, Field(strict=True, ge=0, le=100_000)] | None = None
    consolidation_policy: Literal["WhenEmpty", "WhenEmptyOrUnderutilized", "Balanced"] | None = None
    consolidate_after: Annotated[str, Field(strict=True, min_length=1, max_length=64)] | None = None
    budgets: tuple[SuppliedNapBudget, ...] | None = Field(default=None, max_length=50)


class NapBudgetCalculation(_PolicyModel):
    index: int
    active: bool | None
    applies_to: tuple[DisruptionReason, ...]
    configured_limit: int | None
    reason_codes: list[str]


class NapReasonCalculation(_PolicyModel):
    status: Literal["configured_ceiling", "no_applicable_active_budget", "unknown"]
    configured_limit: int | None
    reason_codes: list[str]


class NapPolicyReview(_PolicyModel):
    schema_version: Literal["1.0"] = "1.0"
    reference: Literal["azure-v1.15.2/karpenter-v1.15.1"] = "azure-v1.15.2/karpenter-v1.15.1"
    input_digest: Digest
    tenant_id: UUID
    cluster_resource_id: str
    cluster_uid: Reference
    nodepool_uid: Reference
    evaluated_at: UtcDatetime
    source_issues: list[str]
    budgets: list[NapBudgetCalculation]
    reasons: dict[DisruptionReason, NapReasonCalculation]
    consolidation_interpretation: Literal[
        "configured_dynamic_policy", "disabled_by_never", "ignored_for_static_pool", "unknown"
    ]
    basis: Literal["supplied_policy_reference_calculation"] = (
        "supplied_policy_reference_calculation"
    )
    controller_admission: Literal["unverified"] = "unverified"
    actual_disruption_headroom: Literal["not_calculated"] = "not_calculated"
    disruption_feasibility: Literal["unknown"] = "unknown"


def _duration(value: str) -> timedelta | None:
    if not re.fullmatch(r"(?:[0-9]+h(?:[0-9]+m)?|[0-9]+m)(?:0s)?", value):
        return None
    seconds = sum(
        int(number) * (3600 if unit == "h" else 60)
        for number, unit in re.findall(r"([0-9]+)([hm])", value)
    )
    if seconds > (2**63 - 1) // 1_000_000_000:
        return None
    return timedelta(seconds=seconds)


def _schedule_active(budget: SuppliedNapBudget, clock: datetime) -> tuple[bool | None, list[str]]:
    if budget.schedule is None and budget.duration is None:
        return True, []
    if budget.schedule is None or budget.duration is None:
        return None, ["schedule_duration_pair_required"]
    duration = _duration(budget.duration)
    if duration is None:
        return None, ["unsupported_budget_duration"]
    schedule = budget.schedule
    aliases = {"@annually", "@yearly", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"}
    fields = schedule.split()
    if schedule not in aliases:
        if (
            len(fields) != 5
            or any(
                word.upper()
                not in {
                    "JAN",
                    "FEB",
                    "MAR",
                    "APR",
                    "MAY",
                    "JUN",
                    "JUL",
                    "AUG",
                    "SEP",
                    "OCT",
                    "NOV",
                    "DEC",
                    "SUN",
                    "MON",
                    "TUE",
                    "WED",
                    "THU",
                    "FRI",
                    "SAT",
                }
                for word in re.findall(r"[A-Za-z_]+", schedule)
            )
            or re.search(r"[^A-Za-z0-9*/?,\-\s]", schedule)
        ):
            return None, ["unsupported_budget_schedule"]
        if "7" in re.findall(r"[0-9]+", fields[4]):
            return None, ["unsupported_budget_schedule"]
        if fields[2] != "*" and fields[4] != "*" and ("*" in fields[2] or "*" in fields[4]):
            return None, ["uncharacterized_day_wildcard_combination"]
    try:
        checkpoint = clock - duration
        next_hit = croniter(
            schedule, checkpoint, day_or=True, max_years_between_matches=5
        ).get_next(datetime)
    except CroniterBadCronError, CroniterBadDateError, ValueError, OverflowError:
        return None, ["unsupported_budget_schedule"]
    return next_hit <= clock, []


def review_nap_policy(
    evidence: NapPolicyInput, *, as_of: datetime, maximum_source_age_seconds: int
) -> NapPolicyReview:
    clock = _utc(as_of)
    if type(maximum_source_age_seconds) is not int or maximum_source_age_seconds < 1:
        raise ValueError("NAP policy review requires a positive integer age budget")
    evidence = NapPolicyInput.model_validate(evidence.model_dump())
    if len(evidence.model_dump_json().encode("utf-8")) > MAXIMUM_NAP_POLICY_BYTES:
        raise ValueError("NAP policy input exceeds its byte budget")
    issues = []
    if evidence.observed_at is None:
        issues.append("missing_policy_source_clock")
    elif evidence.observed_at > clock:
        issues.append("future_policy_source_clock")
    elif (clock - evidence.observed_at).total_seconds() > maximum_source_age_seconds:
        issues.append("stale_policy_source_clock")
    if evidence.object_version is None or evidence.generation is None:
        issues.append("missing_policy_object_binding")
    source_issues = list(issues)
    if evidence.collection is None:
        source_issues.append("missing_source_receipt")
    else:
        receipt_gaps = _receipt_gaps(
            evidence.collection,
            scope=evidence.cluster_resource_id,
            clock=clock,
            maximum_age=maximum_source_age_seconds,
        )
        issues.extend(receipt_gaps)
        source_issues.extend(receipt_gaps)
    rows = []
    for index, budget in enumerate(evidence.budgets or ()):
        active, schedule_gaps = _schedule_active(budget, clock)
        schedule_gaps.extend(issues)
        gaps = list(schedule_gaps)
        if budget.reasons is not None and len(set(budget.reasons)) != len(budget.reasons):
            gaps.append("duplicate_budget_reasons")
        applies = REASONS if budget.reasons is None else budget.reasons
        limit = None
        if not re.fullmatch(r"(?:100|[0-9]{1,2})%|[0-9]+", budget.nodes):
            gaps.append("invalid_budget_nodes")
        elif budget.nodes.endswith("%"):
            if evidence.node_count is None:
                gaps.append("missing_supplied_node_count")
            else:
                limit = (evidence.node_count * int(budget.nodes[:-1]) + 99) // 100
        else:
            limit = int(budget.nodes)
            if limit > 2**31 - 1:
                gaps.append("budget_nodes_out_of_reference_bounds")
        rows.append(
            NapBudgetCalculation(
                index=index,
                active=None if schedule_gaps else active,
                applies_to=applies,
                configured_limit=limit if active and not gaps else None,
                reason_codes=sorted(set(gaps)),
            )
        )
    reasons: dict[DisruptionReason, NapReasonCalculation] = {}
    for reason in REASONS:
        applicable = [row for row in rows if reason in row.applies_to and row.active is not False]
        gaps = sorted({gap for row in applicable for gap in row.reason_codes})
        if evidence.budgets is None:
            gaps.append("missing_explicit_budget_list")
        active_rows = [row for row in applicable if row.active is True]
        limits = [row.configured_limit for row in active_rows if row.configured_limit is not None]
        reasons[reason] = NapReasonCalculation(
            status="unknown"
            if gaps
            else "configured_ceiling"
            if active_rows
            else "no_applicable_active_budget",
            configured_limit=min(limits) if limits and not gaps else None,
            reason_codes=sorted(set(gaps)),
        )
    interpretation: Literal[
        "configured_dynamic_policy", "disabled_by_never", "ignored_for_static_pool", "unknown"
    ] = "unknown"
    if not issues:
        if evidence.supply_mode == "static" and evidence.replicas is not None:
            interpretation = "ignored_for_static_pool"
        elif evidence.supply_mode == "dynamic" and evidence.replicas is None:
            if evidence.consolidate_after == "Never":
                interpretation = "disabled_by_never"
            elif (
                evidence.consolidation_policy is not None
                and evidence.consolidate_after is not None
                and re.fullmatch(r"(?:[0-9]+[smh])+", evidence.consolidate_after)
            ):
                interpretation = "configured_dynamic_policy"
    result = NapPolicyReview(
        input_digest=digest_json(evidence.model_dump(mode="json")),
        tenant_id=evidence.tenant_id,
        cluster_resource_id=evidence.cluster_resource_id,
        cluster_uid=evidence.cluster_uid,
        nodepool_uid=evidence.nodepool_uid,
        evaluated_at=clock,
        source_issues=sorted(set(source_issues)),
        budgets=rows,
        reasons=reasons,
        consolidation_interpretation=interpretation,
    )
    if len(result.model_dump_json().encode("utf-8")) > MAXIMUM_NAP_POLICY_BYTES:
        raise ValueError("NAP policy review exceeds its byte budget")
    return result


def project_nap_policy_inputs(
    metadata: KubernetesMetadataSnapshot, *, nodepools: list[dict[str, Any]]
) -> list[NapPolicyInput]:
    from aks_fleet_efficiency.collectors.kubernetes_metadata import project_metadata
    from aks_fleet_efficiency.scheduling import audit_scheduling_completeness

    if len(nodepools) > 1000:
        raise ValueError("NAP policy projection exceeds its pool budget")
    audit_scheduling_completeness(
        metadata,
        as_of=metadata.generated_at,
        maximum_source_age_seconds=86400,
    )
    resource_key = "karpenter.sh/v1/nodepools"
    if metadata.api_availability.get(
        resource_key
    ) != "available" or not metadata.resource_versions.get(resource_key):
        raise ValueError("NAP policy projection requires the original versioned pool list")
    expected = {row.uid: row for row in metadata.resources if row.kind == "NodePool"}
    if metadata.cluster_uid is None:
        raise ValueError("NAP policy projection requires an exact original fingerprint")
    result = []
    seen = set()
    for row in nodepools:
        if row.get("kind") != "NodePool" or row.get("apiVersion") != "karpenter.sh/v1":
            raise ValueError("NAP policy projection requires native versioned NodePools")
        projected = project_metadata("karpenter.sh/v1/nodepools", row)
        if projected.uid in seen or expected.get(projected.uid) != projected:
            raise ValueError("NAP policy projection requires exact original approved pools")
        seen.add(projected.uid)
        identity = row.get("metadata", {})
        spec = row.get("spec", {})
        if not isinstance(spec, dict):
            raise ValueError("NAP policy projection requires an observed spec")
        disruption = spec.get("disruption", {})
        if not isinstance(disruption, dict):
            raise ValueError("NAP policy projection requires an observed disruption shape")
        replicas = spec.get("replicas")
        mode: Literal["static", "dynamic", "unknown"] = (
            "dynamic"
            if "replicas" not in spec
            else "static"
            if type(replicas) is int and 0 <= replicas < 2**63
            else "unknown"
        )
        budgets = disruption.get("budgets")
        if budgets is not None and (
            not isinstance(budgets, list) or any(not isinstance(item, dict) for item in budgets)
        ):
            raise ValueError("NAP policy projection requires a bounded budget list")
        result.append(
            NapPolicyInput(
                tenant_id=UUID(metadata.tenant_id),
                cluster_resource_id=metadata.cluster_resource_id,
                cluster_uid=metadata.cluster_uid,
                nodepool_uid=projected.uid,
                object_version=identity.get("resourceVersion"),
                generation=identity.get("generation"),
                observed_at=metadata.collection.source_observed_at,
                collection=metadata.collection,
                supply_mode=mode,
                replicas=replicas if mode == "static" else None,
                consolidation_policy=disruption.get("consolidationPolicy"),
                consolidate_after=disruption.get("consolidateAfter"),
                budgets=None
                if budgets is None
                else tuple(
                    SuppliedNapBudget.model_validate(
                        {
                            key: item[key]
                            for key in ["nodes", "reasons", "schedule", "duration"]
                            if key in item
                        }
                    )
                    for item in budgets
                ),
            )
        )
    if seen != expected.keys():
        raise ValueError("NAP policy projection requires the complete original pool roster")
    if (
        len("".join(row.model_dump_json() for row in result).encode("utf-8"))
        > MAXIMUM_NAP_POLICY_BYTES
    ):
        raise ValueError("NAP policy projection exceeds its output byte budget")
    return sorted(result, key=lambda row: row.nodepool_uid)
