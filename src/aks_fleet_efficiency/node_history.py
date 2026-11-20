from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import fsum, isfinite
from statistics import quantiles
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.models import CollectionStatus, CollectorResult, UtcDatetime

MAXIMUM_NODE_HISTORY_BYTES = 32 * 1024 * 1024
MAXIMUM_NODE_HISTORY_POINTS = 100_000
MAXIMUM_NODE_HISTORY_CONTRIBUTIONS = 100_000
Amount = Annotated[float, Field(strict=True, ge=0)]
Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Reference = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")]


def _utc(clock: datetime) -> datetime:
    if clock.utcoffset() is None:
        raise ValueError("historical review requires an aware evaluation clock")
    return clock.astimezone(UTC)


class _HistoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class HistoricalNodeIdentity(_HistoryModel):
    node_uid: Reference
    node_resource_id: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]


class HistoricalNodeContribution(HistoricalNodeIdentity):
    cpu_mcpu: Amount | None = None
    memory_working_set_mib: Amount | None = None
    cpu_sampled_at: UtcDatetime | None = None
    memory_sampled_at: UtcDatetime | None = None


class HistoricalNodePoint(_HistoryModel):
    timestamp: UtcDatetime
    membership_receipt: CollectorResult
    members: tuple[HistoricalNodeIdentity, ...] | None = Field(default=None, max_length=100_000)
    contributions: tuple[HistoricalNodeContribution, ...] = Field(max_length=100_000)


class HistoricalNodeEvidence(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    cluster_resource_id: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    cluster_uid: Reference
    source: Reference
    source_version: Reference
    profile: Reference
    profile_version: Reference
    mapping_reference: Reference
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: Annotated[int, Field(strict=True, ge=1, le=300)]
    cpu_measure: Literal["rate(node_cpu_usage_seconds_total)"] = (
        "rate(node_cpu_usage_seconds_total)"
    )
    cpu_rate_window_seconds: Annotated[int, Field(strict=True, ge=1, le=3600)]
    memory_measure: Literal["node_memory_working_set_bytes"] = "node_memory_working_set_bytes"
    cpu_receipt: CollectorResult
    memory_receipt: CollectorResult
    points: tuple[HistoricalNodePoint, ...] = Field(max_length=100_000)


class HistoricalClusterPoint(_HistoryModel):
    timestamp: UtcDatetime
    members: Annotated[int, Field(ge=0)] | None
    cpu_mcpu: Amount | None
    memory_working_set_mib: Amount | None
    cpu_gaps: list[str]
    memory_gaps: list[str]


class HistoricalNodeReview(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    cluster_resource_id: str
    cluster_uid: Reference
    source: Reference
    source_version: Reference
    profile: Reference
    profile_version: Reference
    mapping_reference: Reference
    evidence_digest: Digest
    evaluated_at: UtcDatetime
    maximum_source_age_seconds: Annotated[int, Field(strict=True, ge=1)]
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: Annotated[int, Field(strict=True, ge=1, le=300)]
    cpu_rate_window_seconds: Annotated[int, Field(strict=True, ge=1, le=3600)]
    cpu_measure: Literal["rate(node_cpu_usage_seconds_total)"] = (
        "rate(node_cpu_usage_seconds_total)"
    )
    memory_measure: Literal["node_memory_working_set_bytes"] = "node_memory_working_set_bytes"
    cpu_p95_mcpu: Amount | None
    memory_p99_working_set_mib: Amount | None
    cpu_gaps: list[str]
    memory_gaps: list[str]
    points: list[HistoricalClusterPoint]
    source_admission: Literal["unverified_saved_contributions"] = "unverified_saved_contributions"
    capacity_interpretation: Literal["not_free_movable_or_billed_capacity"] = (
        "not_free_movable_or_billed_capacity"
    )


def _receipt_gaps(
    receipt: CollectorResult,
    *,
    scope: str,
    clock: datetime,
    maximum_age: int,
    completed_by: datetime | None = None,
) -> list[str]:
    gaps = []
    if (
        receipt.status != CollectionStatus.COMPLETE
        or receipt.requested_scope != [scope]
        or receipt.completed_scope != [scope]
        or not receipt.pagination_complete
        or receipt.errors
        or receipt.missing_fields
    ):
        gaps.append("incomplete_or_foreign_receipt")
    observed = receipt.source_observed_at
    if observed is None:
        gaps.append("missing_source_clock")
    elif observed > clock or receipt.completed_at > (completed_by or clock):
        gaps.append("future_source_clock")
    elif (clock - observed).total_seconds() > maximum_age:
        gaps.append("stale_source_clock")
    return gaps


def _point_total(
    point: HistoricalNodePoint,
    *,
    resource: Literal["cpu", "memory"],
    membership_gaps: list[str],
    step_seconds: int,
) -> tuple[float | None, list[str]]:
    gaps = list(membership_gaps)
    rows = {(row.node_uid, row.node_resource_id): row for row in point.contributions}
    members = {(row.node_uid, row.node_resource_id) for row in point.members or ()}
    if not members <= rows.keys():
        gaps.append("missing_node_contribution")
    values = []
    for identity in sorted(members & rows.keys()):
        row = rows[identity]
        value = row.cpu_mcpu if resource == "cpu" else row.memory_working_set_mib
        clock = row.cpu_sampled_at if resource == "cpu" else row.memory_sampled_at
        if value is None:
            gaps.append("missing_value")
        elif clock is None:
            gaps.append("missing_sample_clock")
        elif not 0 <= (point.timestamp - clock).total_seconds() <= step_seconds:
            gaps.append("misaligned_sample_clock")
        else:
            values.append(value)
    total = None if gaps else _finite_sum(values)
    if not gaps and total is None:
        gaps.append("nonfinite_resource_total")
    return total, sorted(set(gaps))


def _finite_sum(values: list[float]) -> float | None:
    try:
        result = fsum(values)
    except OverflowError:
        return None
    return result if isfinite(result) else None


def _percentile(values: list[float], percentile: int) -> float:
    return (
        values[0]
        if len(values) == 1
        else quantiles(values, n=100, method="inclusive")[percentile - 1]
    )


def _finite_percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    try:
        result = _percentile(values, percentile)
    except OverflowError:
        return None
    return result if isfinite(result) else None


def review_node_history(
    evidence: HistoricalNodeEvidence, *, as_of: datetime, maximum_source_age_seconds: int
) -> HistoricalNodeReview:
    evaluated_at = _utc(as_of)
    if type(maximum_source_age_seconds) is not int or maximum_source_age_seconds < 1:
        raise ValueError("historical Node review requires a positive integer age budget")
    evidence = HistoricalNodeEvidence.model_validate(evidence.model_dump())
    if len(evidence.model_dump_json().encode("utf-8")) > MAXIMUM_NODE_HISTORY_BYTES:
        raise ValueError("historical Node evidence exceeds its byte budget")
    duration = (evidence.window_end - evidence.window_start).total_seconds()
    if duration < 0 or duration % evidence.step_seconds:
        raise ValueError("historical Node window must have an ordered aligned grid")
    count = int(duration / evidence.step_seconds) + 1
    if (
        count > MAXIMUM_NODE_HISTORY_POINTS
        or sum(len(point.contributions) + len(point.members or ()) for point in evidence.points)
        > MAXIMUM_NODE_HISTORY_CONTRIBUTIONS
    ):
        raise ValueError("historical Node evidence exceeds its point or contribution budget")
    timestamps = [point.timestamp for point in evidence.points]
    if len(timestamps) != len(set(timestamps)) or any(
        not evidence.window_start <= timestamp <= evidence.window_end
        or (timestamp - evidence.window_start).total_seconds() % evidence.step_seconds
        for timestamp in timestamps
    ):
        raise ValueError("historical Node timestamps must be distinct and on the declared grid")
    by_time = {point.timestamp: point for point in evidence.points}
    resource_gaps = {
        resource: _receipt_gaps(
            receipt,
            scope=evidence.cluster_resource_id,
            clock=evaluated_at,
            maximum_age=maximum_source_age_seconds,
        )
        for resource, receipt in [
            ("cpu", evidence.cpu_receipt),
            ("memory", evidence.memory_receipt),
        ]
    }
    if evidence.window_end > evaluated_at:
        for gaps in resource_gaps.values():
            gaps.append("future_window")
    elif (evaluated_at - evidence.window_end).total_seconds() > maximum_source_age_seconds:
        for gaps in resource_gaps.values():
            gaps.append("stale_metric_tail")
    points = []
    node_bindings: dict[str, str] = {}
    for index in range(count):
        timestamp = evidence.window_start + timedelta(seconds=index * evidence.step_seconds)
        point = by_time.get(timestamp)
        if point is None:
            points.append(
                HistoricalClusterPoint(
                    timestamp=timestamp,
                    members=None,
                    cpu_mcpu=None,
                    memory_working_set_mib=None,
                    cpu_gaps=["missing_evaluation_point"],
                    memory_gaps=["missing_evaluation_point"],
                )
            )
            continue
        members = point.members
        membership_gaps = _receipt_gaps(
            point.membership_receipt,
            scope=evidence.cluster_resource_id,
            clock=timestamp,
            maximum_age=evidence.step_seconds,
            completed_by=evaluated_at,
        )
        if members is None:
            membership_gaps.append("missing_historical_membership")
        for rows in [members or (), point.contributions]:
            if len({row.node_uid for row in rows}) != len(rows) or len(
                {row.node_resource_id for row in rows}
            ) != len(rows):
                raise ValueError("historical Node identities must be unambiguous per point")
            for row in rows:
                if (
                    node_bindings.setdefault(row.node_uid, row.node_resource_id)
                    != row.node_resource_id
                ):
                    raise ValueError("a historical Node UID cannot change its resource binding")
        if members is not None and not {
            (row.node_uid, row.node_resource_id) for row in point.contributions
        } <= {(row.node_uid, row.node_resource_id) for row in members}:
            raise ValueError("historical contributions must belong to the exact point roster")
        cpu, cpu_gaps = _point_total(
            point,
            resource="cpu",
            membership_gaps=membership_gaps + resource_gaps["cpu"],
            step_seconds=evidence.step_seconds,
        )
        memory, memory_gaps = _point_total(
            point,
            resource="memory",
            membership_gaps=membership_gaps + resource_gaps["memory"],
            step_seconds=evidence.step_seconds,
        )
        points.append(
            HistoricalClusterPoint(
                timestamp=timestamp,
                members=None if members is None else len(members),
                cpu_mcpu=cpu,
                memory_working_set_mib=memory,
                cpu_gaps=cpu_gaps,
                memory_gaps=memory_gaps,
            )
        )
    cpu_gaps = sorted(
        set(resource_gaps["cpu"]) | {gap for point in points for gap in point.cpu_gaps}
    )
    memory_gaps = sorted(
        set(resource_gaps["memory"]) | {gap for point in points for gap in point.memory_gaps}
    )
    cpu_p95 = (
        None
        if cpu_gaps
        else _finite_percentile(
            [point.cpu_mcpu for point in points if point.cpu_mcpu is not None], 95
        )
    )
    memory_p99 = (
        None
        if memory_gaps
        else _finite_percentile(
            [
                point.memory_working_set_mib
                for point in points
                if point.memory_working_set_mib is not None
            ],
            99,
        )
    )
    if not cpu_gaps and cpu_p95 is None:
        cpu_gaps.append("nonfinite_resource_percentile")
    if not memory_gaps and memory_p99 is None:
        memory_gaps.append("nonfinite_resource_percentile")
    result = HistoricalNodeReview(
        **{
            field: getattr(evidence, field)
            for field in [
                "tenant_id",
                "cluster_resource_id",
                "cluster_uid",
                "source",
                "source_version",
                "profile",
                "profile_version",
                "mapping_reference",
                "window_start",
                "window_end",
                "step_seconds",
                "cpu_rate_window_seconds",
            ]
        },
        evidence_digest=digest_json(evidence.model_dump(mode="json")),
        evaluated_at=evaluated_at,
        maximum_source_age_seconds=maximum_source_age_seconds,
        cpu_p95_mcpu=cpu_p95,
        memory_p99_working_set_mib=memory_p99,
        cpu_gaps=cpu_gaps,
        memory_gaps=memory_gaps,
        points=points,
    )
    if len(result.model_dump_json().encode("utf-8")) > MAXIMUM_NODE_HISTORY_BYTES:
        raise ValueError("historical Node review exceeds its byte budget")
    return result
