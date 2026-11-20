"""Offline alignment of owner-reviewed CPU HPA observations, not a source adapter."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from aks_fleet_efficiency.config import ClusterTarget
from aks_fleet_efficiency.models import UtcDatetime

_MAX_SLOTS = 1440
_Token = Annotated[str, Field(strict=True, min_length=1, max_length=128, pattern=r"^\S+$")]
_Count = Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
_PositiveInt = Annotated[int, Field(strict=True, gt=0, le=2**31 - 1)]
_Request = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


def _explicit_clock(value: object) -> object:
    if not isinstance(value, datetime) and not (isinstance(value, str) and "T" in value):
        raise ValueError("use an explicit timezone-aware timestamp")
    return value


_Clock = Annotated[UtcDatetime, BeforeValidator(_explicit_clock)]


class _SavedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ControllerWorkloadScope(_SavedModel):
    tenant_id: UUID
    cluster_resource_id: Annotated[str, Field(strict=True, max_length=512, pattern=r"^\S+$")]
    cluster_uid: _Token
    namespace_uid: _Token
    workload_uid: _Token
    workload_kind: Literal["Deployment"]

    @model_validator(mode="after")
    def validate_cluster_id(self) -> ControllerWorkloadScope:
        ClusterTarget(resource_id=self.cluster_resource_id)
        return self

    @property
    def workload_key(self) -> tuple[UUID, str, str, str, str]:
        return (
            self.tenant_id,
            self.cluster_resource_id,
            self.cluster_uid,
            self.namespace_uid,
            self.workload_uid,
        )


class ControllerScope(ControllerWorkloadScope):
    hpa_uid: _Token
    metric_kind: Literal["Resource"]
    resource: Literal["cpu"]
    target_type: Literal["Utilization"]
    unit: Literal["percent"]
    producer: _Token


class ControllerWindow(_SavedModel):
    start: _Clock
    end: _Clock
    step_seconds: Annotated[int, Field(strict=True, ge=1, le=3600)]

    @property
    def step(self) -> timedelta:
        return timedelta(seconds=self.step_seconds)

    @property
    def slots(self) -> int:
        return (self.end - self.start) // self.step

    @model_validator(mode="after")
    def validate_grid(self) -> ControllerWindow:
        if not 1 <= self.slots <= _MAX_SLOTS or (self.end - self.start) % self.step:
            raise ValueError("window must contain 1 to 1440 whole grid slots")
        return self


class HpaCounts(_SavedModel):
    desired: _Count
    current: _Count


class DeploymentAvailability(_SavedModel):
    ready: _Count | None = None
    available: _Count | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> DeploymentAvailability:
        if self.ready is None and self.available is None:
            raise ValueError("at least one availability count must be observed")
        if self.ready is not None and self.available is not None and self.available > self.ready:
            raise ValueError("available replicas cannot exceed ready replicas")
        return self


class ControllerSample[T](_SavedModel):
    scope: ControllerScope
    configuration_revision: _Token
    request_revision: _Token
    observed_at: _Clock
    captured_at: _Clock
    observation_ref: _Token
    value: T

    @property
    def revision(self) -> tuple[str, str]:
        return self.configuration_revision, self.request_revision


class ControllerEvidence(_SavedModel):
    schema_version: Literal["1.0"]
    window: ControllerWindow
    source_status: Literal["complete", "partial", "denied"]
    signal: Annotated[tuple[ControllerSample[_Count], ...], Field(max_length=_MAX_SLOTS)] = ()
    target: Annotated[tuple[ControllerSample[_PositiveInt], ...], Field(max_length=_MAX_SLOTS)] = ()
    hpa_replicas: Annotated[
        tuple[ControllerSample[HpaCounts], ...], Field(max_length=_MAX_SLOTS)
    ] = ()
    request_mcpu_per_pod: Annotated[
        tuple[ControllerSample[_Request], ...], Field(max_length=_MAX_SLOTS)
    ] = ()
    deployment_availability: Annotated[
        tuple[ControllerSample[DeploymentAvailability], ...], Field(max_length=_MAX_SLOTS)
    ] = ()


type _Issue = Literal[
    "window_mismatch",
    "future_window",
    "source_partial",
    "source_denied",
    "scope_mismatch",
    "off_grid",
    "duplicate",
    "invalid_capture_time",
    "stale",
    "inconsistent_revision",
    "revision_mismatch",
    "missing_hpa_observations",
]


@dataclass(frozen=True)
class ControllerPoint:
    observed_at: datetime
    signal: ControllerSample[int] | None = None
    target: ControllerSample[int] | None = None
    hpa_replicas: ControllerSample[HpaCounts] | None = None
    request_mcpu_per_pod: ControllerSample[float] | None = None
    deployment_availability: ControllerSample[DeploymentAvailability] | None = None


@dataclass(frozen=True)
class ControllerTimeline:
    status: Literal["qualified", "segmented", "partial", "blocked"]
    expected_slots: int
    covered_slots: int | None
    points: tuple[ControllerPoint, ...] = ()
    segment_starts: tuple[datetime, ...] = ()
    issues: tuple[_Issue, ...] = ()


class _Blocked(ValueError):
    def __init__(self, issue: _Issue) -> None:
        super().__init__(issue)
        self.issue = issue


def _index[T](
    samples: tuple[ControllerSample[T], ...],
    scope: ControllerScope,
    window: ControllerWindow,
    as_of: datetime,
) -> dict[datetime, ControllerSample[T]]:
    index: dict[datetime, ControllerSample[T]] = {}
    for sample in samples:
        time = sample.observed_at
        if sample.scope != scope:
            raise _Blocked("scope_mismatch")
        if not window.start <= time < window.end or (time - window.start) % window.step:
            raise _Blocked("off_grid")
        if not time <= sample.captured_at <= as_of:
            raise _Blocked("invalid_capture_time")
        if time in index:
            raise _Blocked("duplicate")
        index[time] = sample
    return index


def _check_revision_values(
    targets: dict[datetime, ControllerSample[int]],
    requests: dict[datetime, ControllerSample[float]],
) -> None:
    target_by_revision: dict[str, int] = {}
    for target in targets.values():
        known_target = target_by_revision.setdefault(target.configuration_revision, target.value)
        if known_target != target.value:
            raise _Blocked("inconsistent_revision")
    request_by_revision: dict[str, float] = {}
    for request in requests.values():
        if request_by_revision.setdefault(request.request_revision, request.value) != request.value:
            raise _Blocked("inconsistent_revision")


def qualify_controller_timeline(
    evidence: ControllerEvidence,
    *,
    expected_scope: ControllerScope,
    reviewed_window: ControllerWindow,
    as_of: datetime,
    max_age: timedelta,
) -> ControllerTimeline:
    """Align the saved input against independent review bindings without filling any gaps."""
    if as_of.utcoffset() is None or max_age < timedelta(0):
        raise ValueError("use a timezone-aware evaluation clock and nonnegative maximum age")
    expected = reviewed_window.slots
    try:
        if evidence.window != reviewed_window:
            raise _Blocked("window_mismatch")
        if reviewed_window.end > as_of:
            raise _Blocked("future_window")
        if evidence.source_status == "partial":
            raise _Blocked("source_partial")
        if evidence.source_status == "denied":
            raise _Blocked("source_denied")

        args = (expected_scope, reviewed_window, as_of)
        signals = _index(evidence.signal, *args)
        targets = _index(evidence.target, *args)
        counts = _index(evidence.hpa_replicas, *args)
        requests = _index(evidence.request_mcpu_per_pod, *args)
        availability = _index(evidence.deployment_availability, *args)
        latest_slot = reviewed_window.end - reviewed_window.step
        if as_of - latest_slot > max_age or any(
            series and as_of - max(series) > max_age for series in (signals, targets, counts)
        ):
            raise _Blocked("stale")
        _check_revision_values(targets, requests)
    except _Blocked as exc:
        return ControllerTimeline("blocked", expected, None, issues=(exc.issue,))

    points: list[ControllerPoint] = []
    issues: dict[_Issue, None] = {}
    starts: list[datetime] = []
    previous_revision: tuple[str, str] | None = None
    covered = 0
    for i in range(expected):
        time = reviewed_window.start + i * reviewed_window.step
        signal, target, replicas = signals.get(time), targets.get(time), counts.get(time)
        request, deployment = requests.get(time), availability.get(time)
        revisions = {
            sample.revision
            for sample in (signal, target, replicas, request, deployment)
            if sample is not None
        }
        if len(revisions) > 1:
            issues["revision_mismatch"] = None
            points.append(ControllerPoint(time))
            continue
        points.append(ControllerPoint(time, signal, target, replicas, request, deployment))
        if signal is None or target is None or replicas is None:
            issues["missing_hpa_observations"] = None
            continue
        covered += 1
        if signal.revision != previous_revision:
            starts.append(time)
            previous_revision = signal.revision
    if issues:
        return ControllerTimeline("partial", expected, covered, tuple(points), issues=tuple(issues))
    return ControllerTimeline(
        "qualified" if len(starts) == 1 else "segmented",
        expected,
        covered,
        tuple(points),
        tuple(starts),
    )
