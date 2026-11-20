from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.models import CollectorResult, UtcDatetime
from aks_fleet_efficiency.node_history import (
    Digest,
    HistoricalNodeIdentity,
    Reference,
    _receipt_gaps,
    _utc,
)


class _ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BusinessOwnerDeclaration(_ContextModel):
    namespace_uid: Reference
    workload_uid: Reference
    owner_ref: Digest
    valid_from: UtcDatetime
    valid_until: UtcDatetime

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("owner declaration requires an ordered validity interval")
        return self


class HistoricalNodeMarket(HistoricalNodeIdentity):
    market: Literal["spot", "regular", "unknown"]


class HistoricalMarketPoint(_ContextModel):
    timestamp: UtcDatetime
    receipt: CollectorResult
    nodes: tuple[HistoricalNodeMarket, ...] | None = Field(default=None, max_length=100_000)


class SourceFallbackRecord(_ContextModel):
    timestamp: UtcDatetime
    from_node_uid: Reference
    to_node_uid: Reference
    source_reference: Digest


class HistoricalMarketEvidence(_ContextModel):
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: Annotated[int, Field(strict=True, ge=1, le=300)]
    points: tuple[HistoricalMarketPoint, ...] = Field(max_length=100_000)
    fallback_records: tuple[SourceFallbackRecord, ...] = Field(default=(), max_length=1000)
    fallback_receipt: CollectorResult | None = None


class FleetContext(_ContextModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    cluster_resource_id: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    cluster_uid: Reference
    source: Reference
    source_version: Reference
    source_profile: Reference
    source_profile_version: Reference
    observed_at: UtcDatetime
    owner_declarations: list[BusinessOwnerDeclaration] = Field(
        default_factory=list, max_length=100_000
    )
    market_history: HistoricalMarketEvidence | None = None


class BusinessOwnerRouting(_ContextModel):
    namespace_uid: Reference
    workload_uid: Reference
    status: Literal["declared", "unknown", "conflicting"]
    owner_ref: Digest | None
    reason_codes: list[str]
    authority: Literal["routing_declaration_not_authorization"] = (
        "routing_declaration_not_authorization"
    )


class HistoricalMarketCounts(_ContextModel):
    timestamp: UtcDatetime
    market_counts: dict[Literal["spot", "regular", "unknown"], int] | None
    reason_codes: list[str]


class HistoricalMarketReview(_ContextModel):
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: int
    points: list[HistoricalMarketCounts]
    fallback_records: tuple[SourceFallbackRecord, ...] | None
    fallback_gaps: list[str]
    interpretation: Literal["sampled_source_market_not_inferred_fallback_or_placement"] = (
        "sampled_source_market_not_inferred_fallback_or_placement"
    )


class FleetContextReview(_ContextModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    cluster_resource_id: str
    cluster_uid: Reference
    source: Reference
    source_version: Reference
    source_profile: Reference
    source_profile_version: Reference
    observed_at: UtcDatetime
    evaluated_at: UtcDatetime
    context_digest: Digest
    business_owners: list[BusinessOwnerRouting]
    unmatched_owner_declarations: int = Field(ge=0)
    market_history: HistoricalMarketReview | None
    source_admission: Literal["unverified_saved_context"] = "unverified_saved_context"


def _review_markets(
    evidence: HistoricalMarketEvidence, *, scope: str, as_of: datetime, maximum_age: int
) -> HistoricalMarketReview:
    duration = (evidence.window_end - evidence.window_start).total_seconds()
    if duration < 0 or duration % evidence.step_seconds:
        raise ValueError("market history requires an ordered aligned grid")
    count = int(duration / evidence.step_seconds) + 1
    if count > 100_000 or sum(len(point.nodes or ()) for point in evidence.points) > 100_000:
        raise ValueError("market history exceeds its point or object budget")
    rows = {point.timestamp: point for point in evidence.points}
    if len(rows) != len(evidence.points) or any(
        not evidence.window_start <= timestamp <= evidence.window_end
        or (timestamp - evidence.window_start).total_seconds() % evidence.step_seconds
        for timestamp in rows
    ):
        raise ValueError("market history timestamps must be distinct and aligned")
    result = []
    bindings: dict[str, str] = {}
    markets: dict[str, set[str]] = {}
    for sample in evidence.points:
        for node in sample.nodes or ():
            if node.market != "unknown":
                markets.setdefault(node.node_uid, set()).add(node.market)
    for index in range(count):
        timestamp = evidence.window_start + timedelta(seconds=index * evidence.step_seconds)
        point = rows.get(timestamp)
        gaps = []
        counts: dict[Literal["spot", "regular", "unknown"], int] = {
            "spot": 0,
            "regular": 0,
            "unknown": 0,
        }
        if point is None or point.nodes is None:
            gaps.append("missing_historical_market_membership")
        else:
            gaps.extend(
                _receipt_gaps(
                    point.receipt,
                    scope=scope,
                    clock=timestamp,
                    maximum_age=evidence.step_seconds,
                    completed_by=as_of,
                )
            )
            if len({node.node_uid for node in point.nodes}) != len(point.nodes) or len(
                {node.node_resource_id for node in point.nodes}
            ) != len(point.nodes):
                raise ValueError("market history requires unambiguous per-point Node identities")
            for node in point.nodes:
                if (
                    bindings.setdefault(node.node_uid, node.node_resource_id)
                    != node.node_resource_id
                ):
                    raise ValueError("market history cannot change a Node UID resource binding")
                counts[node.market] += 1
                if len(markets.get(node.node_uid, set())) > 1:
                    gaps.append("conflicting_node_market_history")
        if evidence.window_end > as_of:
            gaps.append("future_market_window")
        elif (as_of - evidence.window_end).total_seconds() > maximum_age:
            gaps.append("stale_market_tail")
        result.append(
            HistoricalMarketCounts(
                timestamp=timestamp,
                market_counts=None if gaps else counts,
                reason_codes=sorted(set(gaps)),
            )
        )
    fallback_gaps = ["missing_separate_fallback_receipt"]
    if evidence.fallback_receipt is not None:
        fallback_gaps = _receipt_gaps(
            evidence.fallback_receipt,
            scope=scope,
            clock=as_of,
            maximum_age=maximum_age,
        )
        if any(
            record.from_node_uid == record.to_node_uid
            or record.from_node_uid not in bindings
            or record.to_node_uid not in bindings
            or not evidence.window_start <= record.timestamp <= evidence.window_end
            for record in evidence.fallback_records
        ) or len(
            {digest_json(record.model_dump(mode="json")) for record in evidence.fallback_records}
        ) != len(evidence.fallback_records):
            fallback_gaps.append("invalid_or_duplicate_fallback_binding")
    return HistoricalMarketReview(
        window_start=evidence.window_start,
        window_end=evidence.window_end,
        step_seconds=evidence.step_seconds,
        points=result,
        fallback_records=None
        if fallback_gaps
        else tuple(
            sorted(
                evidence.fallback_records,
                key=lambda row: (row.timestamp, row.from_node_uid, row.to_node_uid),
            )
        ),
        fallback_gaps=sorted(set(fallback_gaps)),
    )


def review_fleet_context(
    context: FleetContext,
    *,
    tenant_id: str,
    cluster_resource_id: str,
    cluster_uid: str,
    window_start: datetime,
    window_end: datetime,
    as_of: datetime,
    maximum_source_age_seconds: int,
    workload_identities: list[tuple[str, str]],
) -> FleetContextReview:
    evaluated_at = _utc(as_of)
    start, end = _utc(window_start), _utc(window_end)
    if type(maximum_source_age_seconds) is not int or maximum_source_age_seconds < 1:
        raise ValueError("fleet context requires a positive integer age budget")
    context = FleetContext.model_validate(context.model_dump())
    if len(context.model_dump_json().encode("utf-8")) > 32 * 1024 * 1024:
        raise ValueError("fleet context exceeds its byte budget")
    if (str(context.tenant_id), context.cluster_resource_id, context.cluster_uid) != (
        str(UUID(tenant_id)),
        cluster_resource_id,
        cluster_uid,
    ) or not start <= end <= evaluated_at:
        raise ValueError("fleet context requires exact original scope, fingerprint and clocks")
    identities = set(workload_identities)
    if len(identities) != len(workload_identities) or len(identities) > 100_000:
        raise ValueError("fleet context requires bounded distinct workload identities")
    owner_rows: dict[tuple[str, str], list[BusinessOwnerDeclaration]] = {}
    for declaration in context.owner_declarations:
        owner_rows.setdefault((declaration.namespace_uid, declaration.workload_uid), []).append(
            declaration
        )
    routing = []
    for namespace_uid, workload_uid in sorted(identities):
        declarations = owner_rows.get((namespace_uid, workload_uid), [])
        gaps = []
        owners = {item.owner_ref for item in declarations}
        if not declarations:
            gaps.append("missing_business_owner_declaration")
        if context.observed_at > evaluated_at:
            gaps.append("future_owner_context")
        elif (evaluated_at - context.observed_at).total_seconds() > maximum_source_age_seconds:
            gaps.append("stale_owner_context")
        if any(not item.valid_from <= start <= end <= item.valid_until for item in declarations):
            gaps.append("owner_validity_window_mismatch")
        if len(owners) > 1:
            gaps.append("conflicting_business_owner_declarations")
        routing.append(
            BusinessOwnerRouting(
                namespace_uid=namespace_uid,
                workload_uid=workload_uid,
                status="conflicting" if len(owners) > 1 else "unknown" if gaps else "declared",
                owner_ref=None if gaps else next(iter(owners)),
                reason_codes=sorted(set(gaps)),
            )
        )
    history = context.market_history
    if history is not None and not start <= history.window_start <= history.window_end <= end:
        raise ValueError("market history must remain within the original assessment window")
    return FleetContextReview(
        tenant_id=context.tenant_id,
        cluster_resource_id=cluster_resource_id,
        cluster_uid=cluster_uid,
        source=context.source,
        source_version=context.source_version,
        observed_at=context.observed_at,
        source_profile=context.source_profile,
        source_profile_version=context.source_profile_version,
        evaluated_at=evaluated_at,
        context_digest=digest_json(context.model_dump(mode="json")),
        business_owners=routing,
        unmatched_owner_declarations=sum(
            (item.namespace_uid, item.workload_uid) not in identities
            for item in context.owner_declarations
        ),
        market_history=None
        if history is None
        else _review_markets(
            history,
            scope=cluster_resource_id,
            as_of=evaluated_at,
            maximum_age=maximum_source_age_seconds,
        ),
    )
