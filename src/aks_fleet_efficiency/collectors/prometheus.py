from __future__ import annotations

import copy
import json
import math
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from importlib import import_module
from types import TracebackType
from typing import Any, Protocol
from urllib.parse import urlsplit

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.catalog.models import QueryAsset
from aks_fleet_efficiency.collectors.azure_resource_graph import (
    InventoryReadError,
    _TenantBoundCredential,
)
from aks_fleet_efficiency.collectors.metric_queries import metric_labels, render_query
from aks_fleet_efficiency.config import ClusterTarget, MetricSourceProfile, OnboardingConfig
from aks_fleet_efficiency.models import (
    CollectionError,
    CollectionErrorCode,
    CollectionStatus,
    CollectorResult,
    MetricEntity,
    MetricObservation,
    MetricQuality,
    MetricQueryPlan,
    MetricWindow,
    PrometheusMetricsSnapshot,
)

QUERY_CATALOG = load_catalog().queries


@dataclass(frozen=True)
class RangeQueryResult:
    series: list[dict[str, Any]]
    observed_at: datetime | None = None
    warnings: bool = False


class MetricReadError(Exception):
    def __init__(
        self, code: CollectionErrorCode, *, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(code)
        self.code: CollectionErrorCode = code
        self.retry_after_seconds = retry_after_seconds


class MetricReader(Protocol):
    source_name: str

    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult: ...


def _now() -> datetime:
    return datetime.now(UTC)


class PrometheusHttpReader:
    def __init__(
        self,
        profile: OnboardingConfig,
        *,
        source_name: str,
        credential: Any = None,
        bearer_token: str | None = None,
        transport: Any = None,
        request_timeout_seconds: float = 30,
        max_response_bytes: int = 16 * 1024 * 1024,
        max_series: int = 1000,
    ) -> None:
        source = next(
            (source for source in profile.metric_sources if source.name == source_name), None
        )
        if source is None:
            raise ValueError("an approved metric source is required")
        source = MetricSourceProfile.model_validate(source.model_dump())
        if (
            not math.isfinite(request_timeout_seconds)
            or not 0 < request_timeout_seconds <= 120
            or not 1024 <= max_response_bytes <= 64 * 1024 * 1024
            or not 1 <= max_series <= 10000
        ):
            raise ValueError("invalid metric HTTP timeout, size, or series bound")
        endpoint = urlsplit(str(source.endpoint))
        managed = source.type == "azure-managed-prometheus"
        if managed and (
            not (endpoint.hostname or "").endswith(".prometheus.monitor.azure.com")
            or endpoint.port not in {None, 443}
        ):
            raise ValueError(
                "managed Prometheus tokens require an approved public-Azure metrics endpoint"
            )
        if source.authentication == "bearer-environment" and not bearer_token:
            raise ValueError(
                "inject the bearer credential explicitly; environment values are not read"
            )
        if bearer_token is not None and (
            source.authentication != "bearer-environment"
            or not bearer_token.strip()
            or any(ord(character) < 33 for character in bearer_token)
        ):
            raise ValueError("invalid explicit bearer credential")
        if credential is not None and not managed:
            raise ValueError("Azure credentials may be used only for the managed metrics profile")
        try:
            self.http = import_module("httpx")
        except ImportError:
            raise RuntimeError("Install the project's metrics optional dependencies.") from None
        self.source_name = source_name
        self.source = source
        self.endpoint = str(source.endpoint).rstrip("/") + "/api/v1/query_range"
        self.max_response_bytes = max_response_bytes
        self.max_series = max_series
        self.timeout = request_timeout_seconds
        self.credential = credential
        self.owns_credential = managed and credential is None
        self.bearer_token = bearer_token
        if managed:
            try:
                identity = import_module("azure.identity")
                self.identity_errors = import_module("azure.core.exceptions")
            except ImportError:
                raise RuntimeError(
                    "Install the project's azure optional dependencies for managed metrics."
                ) from None
            if self.credential is None:
                self.credential = identity.DefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_broker_credential=True,
                    process_timeout=10,
                    connection_timeout=request_timeout_seconds,
                    read_timeout=request_timeout_seconds,
                    retry_total=0,
                )
            self.bound_credential = _TenantBoundCredential(
                self.credential, str(profile.scope.tenant_id)
            )
        self.client = self.http.Client(
            verify=True,
            follow_redirects=False,
            trust_env=False,
            timeout=request_timeout_seconds,
            transport=transport,
        )

    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult:
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or end < start
            or not 1 <= step_seconds <= 86400
            or len(query) > 65536
        ):
            raise MetricReadError("invalid-response")
        headers = {"Accept": "application/json"}
        if self.source.type == "azure-managed-prometheus":
            try:
                token = self.bound_credential.get_token(
                    "https://prometheus.monitor.azure.com/.default"
                )
                headers["Authorization"] = f"Bearer {token.token}"
            except (InventoryReadError, self.identity_errors.ClientAuthenticationError):
                raise MetricReadError("unauthorized") from None
            except self.identity_errors.ServiceRequestError:
                raise MetricReadError("unavailable") from None
        elif self.bearer_token is not None:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": step_seconds,
            "timeout": f"{self.timeout:g}s",
            "limit": self.max_series + 1,
        }
        try:
            with self.client.stream(
                "GET", self.endpoint, params=params, headers=headers
            ) as response:
                if response.status_code != 200:
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
                        value = float(response.headers.get("Retry-After", ""))
                        delay = value if math.isfinite(value) else None
                    except (TypeError, ValueError):
                        pass
                    raise MetricReadError(
                        codes.get(response.status_code, "invalid-response"),
                        retry_after_seconds=delay,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > self.max_response_bytes:
                        raise MetricReadError("invalid-response")
                    body.extend(chunk)
                payload = json.loads(body)
                if not isinstance(payload, dict) or payload.get("status") != "success":
                    raise MetricReadError("invalid-response")
                data = payload.get("data")
                if not isinstance(data, dict) or data.get("resultType") != "matrix":
                    raise MetricReadError("invalid-response")
                result = data.get("result")
                if not isinstance(result, list) or len(result) > self.max_series:
                    raise MetricReadError("invalid-response")
                expected_samples = math.floor((end - start).total_seconds() / step_seconds) + 1
                allowed_labels = set(self.source.label_mapping.values()) | {
                    "workload_uid",
                    "hpa_uid",
                    "pod_uid",
                    "node_resource_id",
                    "node_uid",
                    "membership_digest",
                }
                series = []
                for item in result:
                    if (
                        not isinstance(item, dict)
                        or item.get("histograms")
                        or not isinstance(item.get("metric"), dict)
                        or not isinstance(item.get("values"), list)
                        or len(item["values"]) > expected_samples
                    ):
                        raise MetricReadError("invalid-response")
                    if not all(
                        isinstance(name, str) and isinstance(value, str)
                        for name, value in item["metric"].items()
                    ):
                        raise MetricReadError("invalid-response")
                    series.append(
                        {
                            "metric": {
                                name: value
                                for name, value in item["metric"].items()
                                if name in allowed_labels
                            },
                            "values": item["values"],
                        }
                    )
                observed_at = None
                if response.headers.get("Date"):
                    try:
                        parsed = parsedate_to_datetime(response.headers["Date"])
                        if parsed.tzinfo is not None:
                            observed_at = parsed.astimezone(UTC)
                    except (TypeError, ValueError, OverflowError):
                        pass
                return RangeQueryResult(
                    series=series,
                    observed_at=observed_at,
                    warnings=bool(payload.get("warnings") or payload.get("infos")),
                )
        except self.http.TimeoutException:
            raise MetricReadError("timeout") from None
        except self.http.HTTPError:
            raise MetricReadError("unavailable") from None
        except (ValueError, TypeError, KeyError):
            raise MetricReadError("invalid-response") from None

    def close(self) -> None:
        self.client.close()
        if self.owns_credential:
            self.credential.close()

    def __enter__(self) -> PrometheusHttpReader:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class PrometheusMetricCollector:
    def __init__(
        self,
        profile: OnboardingConfig,
        *,
        source_name: str,
        reader: MetricReader,
        entities: Sequence[MetricEntity],
        clock: Callable[[], datetime] = _now,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        chunk_samples: int = 1000,
        max_queries: int = 10000,
        node_history_complete: bool = False,
        maximum_evaluations: int = 5000000,
        maximum_series: int = 10000,
    ) -> None:
        source = next(
            (source for source in profile.metric_sources if source.name == source_name), None
        )
        if source is None or reader.source_name != source_name or not entities:
            raise ValueError(
                "an approved source, bound reader, and explicit metric entities are required"
            )
        if len(entities) > 10000:
            raise ValueError("Metric entity bound exceeded")
        entities = tuple(MetricEntity.model_validate(entity.model_dump()) for entity in entities)
        if (
            not 0 <= max_retries <= 10
            or not 1 <= chunk_samples <= 11000
            or not 1 <= max_queries <= 100000
            or not 1 <= maximum_evaluations <= 100000000
            or not 1 <= maximum_series <= 10000
        ):
            raise ValueError("invalid metric retry, chunk, or query bound")
        identities: set[str] = set()
        self.source_definition = load_catalog().source(source.catalog_profile)
        for entity in entities:
            if entity.kind == "node_pool":
                raise ValueError("pool observations are derived from explicit node entities")
            if (entity.kind == "unresolved_container") != (
                self.source_definition.identity == "name-only"
            ):
                raise ValueError("Metric entity does not match the declared source identity shape")
            target = ClusterTarget(resource_id=entity.cluster_resource_id)
            if target.subscription_id not in profile.scope.subscription_ids or (
                profile.clusters
                and entity.cluster_resource_id
                not in {cluster.resource_id for cluster in profile.clusters}
            ):
                raise ValueError("metric entity is outside the approved cluster scope")
            configured = next(
                (
                    cluster
                    for cluster in profile.clusters
                    if cluster.resource_id == entity.cluster_resource_id
                ),
                None,
            )
            if configured is not None and configured.metric_source != source_name:
                raise ValueError("metric entity does not match the cluster's metric source")
            required = (
                {"cluster_resource_id", "namespace", "workload_kind", "workload", "container"}
                if entity.kind in {"container", "workload_container"}
                else {"cluster_resource_id", "namespace", "workload_kind", "workload"}
                if entity.kind == "workload"
                else {"cluster_resource_id"}
            )
            if not required <= source.label_mapping.keys():
                raise ValueError("explicit metric label mappings are required")
            metric_labels(entity, source)
            identity = entity.model_dump_json()
            if identity in identities:
                raise ValueError("metric entity identities must be unique")
            identities.add(identity)
        self.profile = profile
        self.source = source
        self.reader = reader
        self.entities = tuple(entities)
        self.clock = clock
        self.sleep = sleep
        self.max_retries = max_retries
        self.chunk_samples = chunk_samples
        self.max_queries = max_queries
        self.node_history_complete = node_history_complete
        self.maximum_evaluations = maximum_evaluations
        self.maximum_series = maximum_series

    def applicable(self, metric: str, entity: MetricEntity) -> bool:
        if entity.kind == "unresolved_container":
            return metric in self.source_definition.query_ids
        return QUERY_CATALOG[metric].kind == entity.kind

    def plan_queries(
        self, *, start: datetime, end: datetime, step_seconds: int, metrics: Sequence[str]
    ) -> MetricQueryPlan:
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or end <= start
            or not 1 <= step_seconds <= self.profile.analysis.thresholds.maximum_metric_step_seconds
            or not metrics
            or any(name not in QUERY_CATALOG for name in metrics)
        ):
            raise ValueError(
                "Query planning requires aware ordered times and approved metrics/step"
            )
        expected = math.ceil((end - start).total_seconds() / step_seconds)
        expressions = [
            (
                render_query(
                    QUERY_CATALOG[name].expression,
                    metric_labels(entity, self.source),
                    step_seconds,
                ),
                QUERY_CATALOG[name].delta,
            )
            for entity in self.entities
            for name in metrics
            if self.applicable(name, entity)
        ]
        bases = set(expressions)
        counts = [
            expected - (1 if delta and (end - start).total_seconds() % step_seconds else 0)
            for _, delta in bases
        ]
        unique = len(bases)
        requests = sum(math.ceil(count / self.chunk_samples) for count in counts)
        evaluations = sum(counts)
        if requests > self.max_queries or evaluations > self.maximum_evaluations:
            raise ValueError("Metric collection exceeds query bound or evaluation bound")
        return MetricQueryPlan(
            logical_queries=len(expressions),
            unique_queries=unique,
            requests=requests,
            expected_evaluations=evaluations,
            maximum_series=self.maximum_series,
        )

    def collect_observations(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        step_seconds: int = 300,
        metrics: Sequence[str] | None = None,
    ) -> PrometheusMetricsSnapshot:
        started = self.clock()
        if started.tzinfo is None or started.utcoffset() is None:
            raise ValueError("metric collection clock must be timezone-aware")
        if (start is None) != (end is None):
            raise ValueError("provide both start and end, or neither")
        if end is None:
            end = started.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=self.profile.analysis.thresholds.minimum_observation_days)
        assert start is not None
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or end <= start
            or end > started
            or not 1 <= step_seconds <= self.profile.analysis.thresholds.maximum_metric_step_seconds
        ):
            raise ValueError("metric range requires aware ordered times and an approved step")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        expected = math.ceil((end - start).total_seconds() / step_seconds)
        selected = (
            tuple(metrics)
            if metrics is not None
            else (
                tuple(self.source_definition.query_ids)
                if self.source_definition.identity == "name-only"
                else tuple(QUERY_CATALOG)
            )
        )
        if (
            not selected
            or len(set(selected)) != len(selected)
            or any(metric not in QUERY_CATALOG for metric in selected)
        ):
            raise ValueError("metric names must be distinct approved catalog entries")
        if self.source_definition.identity == "name-only" and any(
            name not in self.source_definition.query_ids for name in selected
        ):
            raise ValueError("Unsupported metric for the declared name-only source")
        query_plan = self.plan_queries(
            start=start, end=end, step_seconds=step_seconds, metrics=selected
        )
        if query_plan.logical_queries == 0:
            raise ValueError("no applicable catalog metrics for the requested entity kinds")
        requested = sorted({entity.cluster_resource_id for entity in self.entities})
        incomplete: set[str] = set()
        errors: list[CollectionError] = []
        missing: list[str] = []
        observations: list[MetricObservation] = []
        source_times: list[datetime | None] = []
        retries = 0
        observed_values = False
        node_samples: dict[tuple[str, str, str], dict[str, dict[int, float]]] = {}
        node_issues: dict[tuple[str, str, str], set[str]] = {}
        responses: dict[tuple[str, datetime, datetime], RangeQueryResult | MetricReadError] = {}

        def summarize(
            entity: MetricEntity,
            metric: str,
            definition: QueryAsset,
            values: dict[int, float],
            issues: set[str],
        ) -> None:
            nonlocal observed_values
            coverage = len(values) / expected
            latest = (
                start
                + timedelta(seconds=(max(values) + (1 if definition.delta else 0)) * step_seconds)
                if values
                else None
            )
            if (
                latest is not None
                and (end - latest).total_seconds()
                > self.profile.analysis.thresholds.maximum_evidence_age_hours * 3600
            ):
                issues.add("stale-series-tail")
            if not values:
                issues.add("missing-series")
            if coverage < self.profile.analysis.thresholds.minimum_coverage_ratio:
                issues.add("insufficient-coverage")
            if issues:
                incomplete.add(entity.cluster_resource_id)
                entity_uid = (
                    entity.hpa_uid or entity.pod_uid or entity.workload_uid or entity.node_uid
                )
                entity_uid = entity_uid or entity.node_pool_resource_id
                missing.append(f"{entity.cluster_resource_id}:{metric}:{entity_uid}")
            samples = list(values.values())
            observed_values = observed_values or bool(samples)
            minimum, maximum = (min(samples), max(samples)) if samples else (None, None)
            percentiles = (
                statistics.quantiles(samples, n=100, method="inclusive")
                if len(samples) > 1
                else [samples[0]] * 99
                if samples
                else []
            )
            observations.append(
                MetricObservation(
                    entity=entity,
                    metric=metric,
                    p50=statistics.median(samples) if samples else None,
                    p95=percentiles[94] if percentiles else None,
                    p99=percentiles[98] if percentiles else None,
                    minimum=minimum,
                    maximum=maximum,
                    total=math.fsum(samples)
                    if definition.delta and samples and coverage == 1 and not issues
                    else None,
                    latest_sample_at=latest,
                    quality=MetricQuality(
                        source=self.source.name,
                        query_version="1.0",
                        query_expression=query if entity.kind != "node_pool" else None,
                        step_seconds=step_seconds,
                        observed_at=self.clock(),
                        unit=definition.unit,
                        minimum=minimum,
                        maximum=maximum,
                        window=MetricWindow(
                            start=start, end=end, sample_count=len(values), coverage_ratio=coverage
                        ),
                    ),
                    issues=sorted(issues),
                )
            )

        for entity in self.entities:
            identity_labels = metric_labels(entity, self.source)
            for metric in selected:
                definition = QUERY_CATALOG[metric]
                if not self.applicable(metric, entity):
                    continue
                query = render_query(definition.expression, identity_labels, step_seconds)
                values: dict[int, float] = {}
                issues: set[str] = set()
                if definition.delta and (end - start).total_seconds() % step_seconds:
                    issues.add("partial-delta-interval")
                try:
                    metric_expected = expected - (1 if "partial-delta-interval" in issues else 0)
                    for first in range(0, metric_expected, self.chunk_samples):
                        last = min(metric_expected, first + self.chunk_samples) - 1
                        offset = step_seconds if definition.delta else 0
                        first_time = start + timedelta(seconds=first * step_seconds + offset)
                        last_time = start + timedelta(seconds=last * step_seconds + offset)
                        cache_key = (query, first_time, last_time)
                        cached_error = responses.get(cache_key)
                        if isinstance(cached_error, MetricReadError):
                            raise cached_error
                        for attempt in range(self.max_retries + 1):
                            try:
                                cached = responses.get(cache_key)
                                if isinstance(cached, MetricReadError):
                                    raise cached
                                if cached is not None:
                                    response = cached
                                else:
                                    read = self.reader.query_range(
                                        query=query,
                                        start=first_time,
                                        end=last_time,
                                        step_seconds=step_seconds,
                                    )
                                    if (
                                        len(read.series) > self.maximum_series
                                        or sum(
                                            len(series.get("values", [])) for series in read.series
                                        )
                                        > self.maximum_evaluations
                                    ):
                                        raise MetricReadError("response-budget-exceeded")
                                    response = RangeQueryResult(
                                        series=copy.deepcopy(read.series),
                                        observed_at=read.observed_at,
                                        warnings=read.warnings,
                                    )
                                    responses[cache_key] = response
                                break
                            except MetricReadError as error:
                                if (
                                    error.code not in {"throttled", "timeout", "unavailable"}
                                    or attempt == self.max_retries
                                ):
                                    responses[cache_key] = error
                                    raise
                                delay = (
                                    error.retry_after_seconds
                                    if error.retry_after_seconds is not None
                                    else 2**attempt
                                )
                                self.sleep(min(30, max(0, delay)))
                                retries += 1
                        if response.observed_at is not None and (
                            response.observed_at.tzinfo is None
                            or response.observed_at.utcoffset() is None
                            or response.observed_at > self.clock()
                        ):
                            raise MetricReadError("invalid-response")
                        source_times.append(response.observed_at)
                        if response.warnings:
                            issues.add("provider-warning")
                        matched = [
                            series
                            for series in response.series
                            if all(
                                series.get("metric", {}).get(name) == value
                                for name, value in identity_labels.items()
                            )
                        ]
                        if len(matched) > 1:
                            raise MetricReadError("identity-mismatch")
                        for series in matched:
                            for timestamp, raw_value in series.get("values", []):
                                if isinstance(timestamp, bool) or isinstance(raw_value, bool):
                                    raise MetricReadError("invalid-response")
                                sample_time = float(timestamp)
                                value = float(raw_value)
                                if (
                                    not math.isfinite(sample_time)
                                    or not math.isfinite(value)
                                    or value < 0
                                ):
                                    raise MetricReadError("invalid-response")
                                position = (sample_time - start.timestamp()) / step_seconds - (
                                    1 if definition.delta else 0
                                )
                                index = round(position)
                                if (
                                    abs(position - index) > 0.000001
                                    or index < first
                                    or index > last
                                ):
                                    raise MetricReadError("invalid-response")
                                if index in values:
                                    raise MetricReadError("invalid-response")
                                values[index] = value
                except MetricReadError as error:
                    errors.append(
                        CollectionError(scope=entity.cluster_resource_id, code=error.code)
                    )
                    issues.add(error.code)
                except (TypeError, ValueError, KeyError, AttributeError):
                    errors.append(
                        CollectionError(scope=entity.cluster_resource_id, code="invalid-response")
                    )
                    issues.add("invalid-response")
                summarize(entity, metric, definition, values, issues)
                if (
                    entity.kind == "node"
                    and entity.node_pool_resource_id is not None
                    and entity.node_uid is not None
                ):
                    key = (entity.cluster_resource_id, entity.node_pool_resource_id, metric)
                    node_samples.setdefault(key, {})[entity.node_uid] = values
                    node_issues.setdefault(key, set()).update(issues)
        for (cluster_id, pool_id, metric), members in sorted(node_samples.items()):
            timestamps = set.intersection(*(set(values) for values in members.values()))
            summed = (
                {
                    timestamp: math.fsum(values[timestamp] for values in members.values())
                    for timestamp in timestamps
                }
                if self.node_history_complete
                else {}
            )
            pool_issues = set(node_issues[(cluster_id, pool_id, metric)])
            if not self.node_history_complete:
                pool_issues.add("unverified-historical-membership")
            summarize(
                MetricEntity(
                    kind="node_pool", cluster_resource_id=cluster_id, node_pool_resource_id=pool_id
                ),
                metric.replace("node_", "pool_", 1),
                QUERY_CATALOG[metric],
                summed,
                pool_issues,
            )
        ended = self.clock()
        if ended.tzinfo is None or ended.utcoffset() is None or ended < started:
            raise ValueError("invalid metric completion clock")
        incomplete.update(error.scope for error in errors)
        completed = [scope for scope in requested if scope not in incomplete]
        state = (
            CollectionStatus.COMPLETE
            if not incomplete
            else CollectionStatus.PARTIAL
            if observed_values or not errors
            else CollectionStatus.FAILED
        )
        oldest = (
            min(value for value in source_times if value is not None)
            if source_times and all(value is not None for value in source_times)
            else None
        )
        return PrometheusMetricsSnapshot(
            tenant_id=str(self.profile.scope.tenant_id),
            source_name=self.source.name,
            generated_at=ended,
            query_start=start,
            query_end=end,
            step_seconds=step_seconds,
            collection=CollectorResult(
                collector="prometheus",
                status=state,
                requested_scope=requested,
                completed_scope=completed,
                started_at=started,
                completed_at=ended,
                source_observed_at=oldest,
                pagination_complete=not errors,
                retry_count=retries,
                errors=errors,
                missing_fields=sorted(set(missing)),
            ),
            observations=observations,
            source_profile=self.source_definition,
            query_plan=query_plan,
        )
