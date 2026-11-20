from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, model_validator

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.catalog.models import (
    CatalogModel,
    Digest,
    QueryId,
    RenderedQuery,
    SourceProfileId,
    Text,
    Version,
)
from aks_fleet_efficiency.collectors.prometheus import (
    MetricReader,
    MetricReadError,
    RangeQueryResult,
)
from aks_fleet_efficiency.models import UtcDatetime

AcceptanceStatus = Literal["accepted", "partial", "blocked"]
MetricUnit = Literal["mCPU", "MiB", "ratio", "events", "pods", "boolean"]
ReasonCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,127}$")]
LabelKey = Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,127}$")]


@dataclass(frozen=True)
class PrometheusQueryExecution:
    query: RenderedQuery
    unit: MetricUnit
    required_label_keys: tuple[str, ...]
    expected_label_sets: tuple[dict[str, str], ...]
    result: RangeQueryResult | MetricReadError


class PrometheusQueryRequest(CatalogModel):
    query: RenderedQuery
    unit: MetricUnit
    required_label_keys: tuple[str, ...]
    expected_label_sets: tuple[dict[str, str], ...]

    @model_validator(mode="after")
    def validate_roster(self) -> PrometheusQueryRequest:
        if (
            not self.required_label_keys
            or len(set(self.required_label_keys)) != len(self.required_label_keys)
            or not self.expected_label_sets
            or len(self.expected_label_sets) > 10_000
            or any(set(item) != set(self.required_label_keys) for item in self.expected_label_sets)
            or len(
                {
                    tuple(item[key] for key in self.required_label_keys)
                    for item in self.expected_label_sets
                }
            )
            != len(self.expected_label_sets)
        ):
            raise ValueError("Query request requires a distinct closed expected roster")
        return self


class PrometheusSourceAcceptancePlan(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["prometheus-source-acceptance-plan"] = "prometheus-source-acceptance-plan"
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    source: Text
    source_profile_id: SourceProfileId
    source_profile_version: Version
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: int = Field(gt=0, le=300, strict=True)
    configuration_digest: Digest
    requests: list[PrometheusQueryRequest] = Field(min_length=1, max_length=1000)
    notice: Literal[
        "Expected identity roster and installed query plan only; not live consent, source "
        "authentication, finding eligibility, approval or savings."
    ] = (
        "Expected identity roster and installed query plan only; not live consent, source "
        "authentication, finding eligibility, approval or savings."
    )

    @model_validator(mode="after")
    def validate_plan(self) -> PrometheusSourceAcceptancePlan:
        if self.window_end <= self.window_start:
            raise ValueError("Source acceptance plan requires an ordered fixed window")
        request_keys = [
            (item.query.metric, item.query.version, item.query.entity_digest)
            for item in self.requests
        ]
        if len(set(request_keys)) != len(request_keys):
            raise ValueError("Source acceptance plan query requests must be distinct")
        if any(
            item.query.source != self.source or item.query.step_seconds != self.step_seconds
            for item in self.requests
        ):
            raise ValueError("Source acceptance plan requires exact source and step bindings")
        return self


class PrometheusQueryAcceptance(CatalogModel):
    query_id: QueryId
    query_version: Version
    expression_digest: Digest
    unit: MetricUnit
    status: AcceptanceStatus
    reason_codes: list[ReasonCode] = Field(default_factory=list, max_length=32)
    required_label_keys: list[LabelKey] = Field(min_length=1, max_length=16)
    observed_series: int = Field(ge=0, strict=True)
    matched_expected_entities: int = Field(ge=0, strict=True)
    expected_entities: int = Field(ge=1, strict=True)
    duplicate_series: int = Field(ge=0, strict=True)
    latest_sample_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> PrometheusQueryAcceptance:
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Query acceptance reasons must be distinct")
        if len(set(self.required_label_keys)) != len(self.required_label_keys):
            raise ValueError("Query acceptance label keys must be distinct")
        if self.matched_expected_entities > self.expected_entities:
            raise ValueError("Matched entities cannot exceed the expected roster")
        if self.matched_expected_entities > self.observed_series:
            raise ValueError("Matched entities cannot exceed observed series")
        if self.duplicate_series > self.observed_series:
            raise ValueError("Duplicate series cannot exceed observed series")
        if self.status == "accepted":
            if self.reason_codes:
                raise ValueError("Accepted query evidence cannot have reasons")
            if (
                self.observed_series == 0
                or self.matched_expected_entities != self.expected_entities
                or self.duplicate_series != 0
                or self.latest_sample_at is None
            ):
                raise ValueError("Accepted query evidence requires a complete distinct roster")
        elif not self.reason_codes:
            raise ValueError("Unaccepted query evidence requires explicit reasons")
        return self


class PrometheusSourceAcceptance(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["executed-prometheus-source"] = "executed-prometheus-source"
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    source: Text
    source_profile_id: SourceProfileId
    source_profile_version: Version
    evaluated_at: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: int = Field(gt=0, le=86400, strict=True)
    status: AcceptanceStatus
    reason_codes: list[ReasonCode] = Field(default_factory=list, max_length=64)
    input_digest: Digest
    configuration_digest: Digest
    records: list[PrometheusQueryAcceptance] = Field(min_length=1, max_length=1000)
    endpoint: None = None
    live_time_picker_quality: Literal["unknown"] = "unknown"
    notice: Literal[
        "Fixed-window executed evidence only; not endpoint authentication, mutable live "
        "datasource quality, finding eligibility, scheduler fit, change approval or savings."
    ] = (
        "Fixed-window executed evidence only; not endpoint authentication, mutable live "
        "datasource quality, finding eligibility, scheduler fit, change approval or savings."
    )

    @model_validator(mode="after")
    def validate_acceptance(self) -> PrometheusSourceAcceptance:
        if self.window_end <= self.window_start or self.evaluated_at < self.window_end:
            raise ValueError("Source acceptance requires an ordered fixed window and clock")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Source acceptance reasons must be distinct")
        query_keys = [
            (record.query_id, record.query_version, record.expression_digest)
            for record in self.records
        ]
        if len(set(query_keys)) != len(query_keys):
            raise ValueError("Source acceptance query records must be distinct")
        record_statuses = {record.status for record in self.records}
        expected_status: AcceptanceStatus = (
            "accepted"
            if record_statuses == {"accepted"}
            else "blocked"
            if record_statuses == {"blocked"}
            else "partial"
        )
        if self.status != expected_status:
            raise ValueError("Source acceptance status must reflect query records")
        if self.status == "accepted" and self.reason_codes:
            raise ValueError("Accepted source evidence cannot have reasons")
        if self.status != "accepted" and not self.reason_codes:
            raise ValueError("Unaccepted source evidence requires explicit reasons")
        for record in self.records:
            if record.latest_sample_at is not None and not (
                self.window_start <= record.latest_sample_at <= self.window_end
            ):
                raise ValueError("Query sample clocks must remain inside the fixed window")
        return self


def _series_clock(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        timestamp = float(value)
        if not math.isfinite(timestamp):
            return None
        return datetime.fromtimestamp(timestamp, UTC)
    except OverflowError, OSError, ValueError:
        return None


def _finite_sample(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError, ValueError:
        return False


def _query_acceptance(
    execution: PrometheusQueryExecution,
    *,
    window_start: datetime,
    window_end: datetime,
    evaluated_at: datetime,
) -> PrometheusQueryAcceptance:
    required = execution.required_label_keys
    expected = execution.expected_label_sets
    if (
        not required
        or len(set(required)) != len(required)
        or not expected
        or len(expected) > 10_000
        or any(set(item) != set(required) for item in expected)
        or len({tuple(item[key] for key in required) for item in expected}) != len(expected)
    ):
        raise ValueError("Source acceptance requires a distinct closed expected roster")
    if isinstance(execution.result, MetricReadError):
        return PrometheusQueryAcceptance(
            query_id=execution.query.metric,
            query_version=execution.query.version,
            expression_digest=execution.query.expression_digest,
            unit=execution.unit,
            status="blocked",
            reason_codes=[f"source_{execution.result.code.replace('-', '_')}"],
            required_label_keys=list(required),
            observed_series=0,
            matched_expected_entities=0,
            expected_entities=len(expected),
            duplicate_series=0,
            latest_sample_at=None,
        )
    reasons: set[str] = set()
    blocking: set[str] = set()
    identities: list[tuple[str | None, ...]] = []
    latest_sample_at: datetime | None = None
    step = timedelta(seconds=execution.query.step_seconds)
    expected_points = (window_end - window_start) // step + 1
    for series in execution.result.series:
        metric = series.get("metric")
        values = series.get("values")
        if not isinstance(metric, dict) or not isinstance(values, list):
            raise ValueError("Source acceptance received an invalid bounded matrix series")
        if any(not isinstance(metric.get(key), str) or not metric.get(key) for key in required):
            reasons.add("required_label_missing")
            blocking.add("required_label_missing")
        identity = tuple(
            metric.get(key) if isinstance(metric.get(key), str) else None for key in required
        )
        identities.append(identity)
        sample_clocks: set[datetime] = set()
        for sample in values:
            if not isinstance(sample, list) or len(sample) != 2:
                raise ValueError("Source acceptance received an invalid matrix sample")
            observed = _series_clock(sample[0])
            if observed is None:
                blocking.add("sample_clock_invalid")
            elif not window_start <= observed <= window_end:
                blocking.add("sample_clock_outside_window")
            elif (observed - window_start) % step != timedelta(0):
                blocking.add("sample_clock_off_grid")
            else:
                if observed in sample_clocks:
                    blocking.add("duplicate_sample_clock")
                sample_clocks.add(observed)
                if latest_sample_at is None or observed > latest_sample_at:
                    latest_sample_at = observed
            if not _finite_sample(sample[1]):
                blocking.add("sample_value_invalid")
        if len(sample_clocks) != expected_points:
            reasons.add("sample_grid_incomplete")
    expected_identities = {tuple(item[key] for key in required) for item in expected}
    observed_identities = set(identities)
    if observed_identities - expected_identities:
        reasons.add("unexpected_identity")
        blocking.add("unexpected_identity")
    matched = len(expected_identities & observed_identities)
    if matched != len(expected_identities):
        reasons.add("expected_entity_missing")
    duplicates = sum(count - 1 for count in Counter(identities).values() if count > 1)
    if duplicates:
        reasons.add("duplicate_series")
        blocking.add("duplicate_series")
    if not execution.result.series:
        reasons.add("empty_result")
    if execution.result.warnings:
        reasons.add("source_warning")
    if execution.result.observed_at is None:
        reasons.add("source_observation_clock_missing")
    elif execution.result.observed_at > evaluated_at:
        reasons.add("source_observation_clock_future")
        blocking.add("source_observation_clock_future")
    if latest_sample_at is None:
        reasons.add("latest_sample_missing")
    reasons.update(blocking)
    status: AcceptanceStatus = "blocked" if blocking else "partial" if reasons else "accepted"
    return PrometheusQueryAcceptance(
        query_id=execution.query.metric,
        query_version=execution.query.version,
        expression_digest=execution.query.expression_digest,
        unit=execution.unit,
        status=status,
        reason_codes=sorted(reasons),
        required_label_keys=list(required),
        observed_series=len(execution.result.series),
        matched_expected_entities=matched,
        expected_entities=len(expected),
        duplicate_series=duplicates,
        latest_sample_at=latest_sample_at,
    )


def evaluate_prometheus_source_acceptance(
    *,
    tenant_id: str,
    cluster_resource_id: str,
    cluster_uid: str,
    source_profile_id: SourceProfileId,
    source_profile_version: Version,
    evaluated_at: datetime,
    window_start: datetime,
    window_end: datetime,
    step_seconds: int,
    configuration_digest: Digest,
    executions: list[PrometheusQueryExecution],
) -> PrometheusSourceAcceptance:
    if not 1 <= len(executions) <= 1000:
        raise ValueError("Source acceptance requires one to 1000 query executions")
    if (
        any(execution.query.step_seconds != step_seconds for execution in executions)
        or len({execution.query.source for execution in executions}) != 1
    ):
        raise ValueError("Source acceptance executions require one source and exact step")
    records = [
        _query_acceptance(
            execution,
            window_start=window_start,
            window_end=window_end,
            evaluated_at=evaluated_at,
        )
        for execution in executions
    ]
    statuses = {record.status for record in records}
    status: AcceptanceStatus = (
        "accepted"
        if statuses == {"accepted"}
        else "blocked"
        if statuses == {"blocked"}
        else "partial"
    )
    reason_codes = sorted({reason for record in records for reason in record.reason_codes})
    digest_input = []
    for execution in executions:
        if isinstance(execution.result, MetricReadError):
            result_input: object = {"error_code": execution.result.code}
        else:
            result_input = {
                "series": execution.result.series,
                "observed_at": (
                    execution.result.observed_at.isoformat()
                    if execution.result.observed_at is not None
                    else None
                ),
                "warnings": execution.result.warnings,
            }
        digest_input.append(
            {
                "query": execution.query.model_dump(mode="json"),
                "unit": execution.unit,
                "required_label_keys": execution.required_label_keys,
                "expected_label_sets": execution.expected_label_sets,
                "result": result_input,
            }
        )
    if len(str(digest_input).encode("utf-8")) > 32 * 1024 * 1024:
        raise ValueError("Source acceptance input exceeds its byte budget")
    return PrometheusSourceAcceptance(
        tenant_id=tenant_id,
        cluster_resource_id=cluster_resource_id,
        cluster_uid=cluster_uid,
        source=executions[0].query.source,
        source_profile_id=source_profile_id,
        source_profile_version=source_profile_version,
        evaluated_at=evaluated_at,
        window_start=window_start,
        window_end=window_end,
        step_seconds=step_seconds,
        status=status,
        reason_codes=reason_codes,
        input_digest=digest_json(digest_input),
        configuration_digest=configuration_digest,
        records=records,
    )


def collect_prometheus_source_acceptance(
    *,
    reader: MetricReader,
    requests: list[PrometheusQueryRequest],
    tenant_id: str,
    cluster_resource_id: str,
    cluster_uid: str,
    source_profile_id: SourceProfileId,
    source_profile_version: Version,
    evaluated_at: datetime,
    window_start: datetime,
    window_end: datetime,
    step_seconds: int,
    configuration_digest: Digest,
) -> PrometheusSourceAcceptance:
    if not 1 <= len(requests) <= 1000:
        raise ValueError("Source acceptance requires one to 1000 query requests")
    request_keys = [
        (item.query.metric, item.query.version, item.query.entity_digest) for item in requests
    ]
    if len(set(request_keys)) != len(request_keys):
        raise ValueError("Source acceptance query requests must be distinct")
    if any(
        request.query.source != reader.source_name or request.query.step_seconds != step_seconds
        for request in requests
    ):
        raise ValueError("Source acceptance requires a bound reader and exact query step")
    executions = []
    for request in requests:
        try:
            result: RangeQueryResult | MetricReadError = reader.query_range(
                query=request.query.expression,
                start=window_start,
                end=window_end,
                step_seconds=step_seconds,
            )
        except MetricReadError as error:
            result = error
        executions.append(
            PrometheusQueryExecution(
                query=request.query,
                unit=request.unit,
                required_label_keys=request.required_label_keys,
                expected_label_sets=request.expected_label_sets,
                result=result,
            )
        )
    return evaluate_prometheus_source_acceptance(
        tenant_id=tenant_id,
        cluster_resource_id=cluster_resource_id,
        cluster_uid=cluster_uid,
        source_profile_id=source_profile_id,
        source_profile_version=source_profile_version,
        evaluated_at=evaluated_at,
        window_start=window_start,
        window_end=window_end,
        step_seconds=step_seconds,
        configuration_digest=configuration_digest,
        executions=executions,
    )
