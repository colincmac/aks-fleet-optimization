from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError

from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.config import ClusterTarget, OnboardingConfig
from aks_fleet_efficiency.models import (
    CollectionStatus,
    FleetSnapshot,
    ReadinessCheck,
    ReadinessReport,
)


def _digest(model: BaseModel) -> str:
    encoded = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _allowed_scope(unit: str, collector: str, profile: OnboardingConfig) -> bool:
    if collector == "azure-inventory":
        try:
            return UUID(unit) in profile.scope.subscription_ids
        except ValueError:
            pass
    try:
        target = ClusterTarget(resource_id=unit)
    except ValidationError:
        return False
    return target.subscription_id in profile.scope.subscription_ids and (
        not profile.clusters or unit in {cluster.resource_id for cluster in profile.clusters}
    )


def _entity_quality_status(
    snapshot: FleetSnapshot, profile: OnboardingConfig, evaluated_at: datetime
) -> Literal["pass", "blocked", "unknown"]:
    unknown = not any(cluster.workloads for cluster in snapshot.clusters)
    required = {
        "usage_cpu_p95_mcores": "mCPU",
        "usage_cpu_p99_mcores": "mCPU",
        "cpu_throttled_ratio": "ratio",
        "memory_oom_events": "events",
    }
    maximum_age = profile.analysis.thresholds.maximum_evidence_age_hours * 3600
    for cluster in snapshot.clusters:
        for workload in cluster.workloads:
            if not workload.containers:
                unknown = True
            for container in workload.containers:
                for metric, unit in required.items():
                    value = getattr(container.resources, metric)
                    quality = container.resources.metric_quality.get(metric)
                    if value is None or quality is None:
                        unknown = True
                        continue
                    window = quality.window
                    expected_samples = ceil(
                        (window.end - window.start).total_seconds() / quality.step_seconds
                    )
                    if (
                        quality.unit != unit
                        or quality.step_seconds
                        > profile.analysis.thresholds.maximum_metric_step_seconds
                        or quality.observed_at > snapshot.generated_at
                        or quality.observed_at > evaluated_at
                        or (evaluated_at - quality.observed_at).total_seconds() > maximum_age
                        or window.start != snapshot.metric_window.start
                        or window.end != snapshot.metric_window.end
                        or window.sample_count == 0
                        or window.coverage_ratio
                        < profile.analysis.thresholds.minimum_coverage_ratio
                        or window.coverage_ratio
                        > min(1, (window.sample_count + 1) / expected_samples)
                        or (quality.minimum is not None and value < quality.minimum)
                        or (quality.maximum is not None and value > quality.maximum)
                    ):
                        return "blocked"
    return "unknown" if unknown else "pass"


def evaluate_readiness(
    profile: OnboardingConfig,
    *,
    snapshot: FleetSnapshot | None = None,
    as_of: datetime | None = None,
) -> ReadinessReport:
    evaluated_at = as_of if as_of is not None else datetime.now(UTC)
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("readiness evaluation time must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(UTC)
    checks: list[ReadinessCheck] = []

    def add(
        code: str,
        status: Literal["pass", "blocked", "unknown"],
        scope: str,
        message: str,
    ) -> None:
        checks.append(ReadinessCheck(code=code, status=status, scope=scope, message=message))

    add(
        "configuration.validated",
        "pass",
        "configuration",
        "Versioned configuration and explicit allowlists validated.",
    )
    for pack_id in profile.analysis.packs or list(load_catalog().manifests):
        for capability in evaluate_source_capabilities(
            profile, [], pack_id=pack_id, as_of=evaluated_at
        ):
            add(
                f"pack.{capability.pack_id}.{capability.mode}",
                "blocked" if capability.status in {"unsupported", "unavailable"} else "unknown",
                capability.cluster_resource_id,
                f"Declared source profile {capability.source_profile.id}: {capability.status}. "
                "Offline readiness has not probed required series or source history.",
            )
    add(
        "scope.permissions",
        "unknown",
        "scope",
        "Azure and Kubernetes permissions have not been probed.",
    )
    add(
        "destination.permissions",
        "unknown",
        "reports",
        "Report destination access and retention approval have not been tested; "
        "no directory was created.",
    )
    if not profile.clusters:
        add(
            "scope.discovery",
            "unknown",
            "scope",
            "Subscription scope is explicit, but live cluster discovery has not run.",
        )
    needs_metrics = any(
        load_catalog().pack(pack_id).evidence_kind == "metrics"
        for pack_id in profile.analysis.packs or list(load_catalog().manifests)
    )
    if not profile.metric_sources and needs_metrics:
        add("source.configuration", "blocked", "sources", "No metric source profile is configured.")
    for source in profile.metric_sources:
        add(
            "source.connectivity",
            "unknown",
            source.name,
            "Endpoint, authentication, required series, and label identity have not been probed.",
        )
        retention = source.declared_retention_days
        add(
            "source.retention",
            "unknown"
            if retention is None
            else "pass"
            if retention >= profile.analysis.thresholds.minimum_observation_days
            else "blocked",
            source.name,
            "Declared retention is checked against the requested window; "
            "this is not observed endpoint retention.",
        )
        step = source.declared_step_seconds
        add(
            "source.resolution",
            "unknown"
            if step is None
            else "pass"
            if step <= profile.analysis.thresholds.maximum_metric_step_seconds
            else "blocked",
            source.name,
            "Declared resolution is checked against the configured maximum; "
            "retained resolution remains unverified.",
        )
        labels = source.label_mapping
        mapped = {
            "cluster_resource_id",
            "namespace",
            "workload_kind",
            "workload",
            "container",
        } <= labels.keys()
        add(
            "source.labels",
            "pass" if mapped and len(set(labels.values())) == len(labels) else "blocked",
            source.name,
            "Distinct cluster resource ID, namespace, workload kind, workload, and container "
            "label mappings are required; this does not verify retained historical UID labels.",
        )
        for code, message in (
            (
                "source.historical_identity",
                "Historical workload/Pod/node UIDs, deleted-member rosters, request history "
                "and pool membership have not been independently verified; current metadata "
                "and declared retention cannot reconstruct them.",
            ),
            (
                "source.recording_semantics",
                "Required retained series, upstream recording definitions, units, alignment "
                "and controller history have not been verified against the query catalog; "
                "new recordings cannot backfill missing history.",
            ),
            (
                "source.provenance",
                "Operator approval of endpoint, credential/client origin and cluster "
                "fingerprint provenance has not been verified; references and digests "
                "are not source attestation or live-access consent.",
            ),
            (
                "source.network",
                "Private DNS/routing, proxy and CA requirements have not been verified "
                "from the intended runner; TLS verification must remain enabled.",
            ),
        ):
            add(code, "unknown", source.name, message)
    for target in profile.clusters:
        add(
            "cluster.source",
            "pass" if target.metric_source or not needs_metrics else "blocked",
            target.resource_id,
            "Each metric-based assessment needs a named source; inventory-only packs do not.",
        )
        risk = profile.analysis.environment_risk.get(target.environment or "")
        add(
            "cluster.environment",
            "unknown"
            if target.environment is None
            else "pass"
            if risk in {"low", "medium", "high"}
            else "blocked",
            target.resource_id,
            "Environment classification must reference an explicit recognized risk policy.",
        )
        owners = any(
            mapping.cluster_resource_id == target.resource_id for mapping in profile.ownership
        )
        add(
            "cluster.ownership",
            "pass" if owners else "unknown",
            target.resource_id,
            "Namespace owner mappings are declarations, not workload policy or change approval.",
        )

    if snapshot is None:
        add(
            "snapshot.evidence",
            "unknown",
            "snapshot",
            "No normalized snapshot supplied; observed inventory and metric quality are unknown.",
        )
    else:
        expected = {target.resource_id for target in profile.clusters}
        observed: set[str] = set()
        scope_valid = True
        for cluster in snapshot.clusters:
            try:
                target = ClusterTarget(resource_id=cluster.resource_id)
                scope_valid = scope_valid and target.subscription_id == UUID(
                    cluster.subscription_id
                )
                scope_valid = (
                    scope_valid and target.subscription_id in profile.scope.subscription_ids
                )
            except (ValidationError, ValueError):
                scope_valid = False
            if cluster.resource_id in observed or (
                expected and cluster.resource_id not in expected
            ):
                scope_valid = False
            observed.add(cluster.resource_id)
        scope_valid = scope_valid and expected <= observed
        add(
            "snapshot.scope",
            "pass" if scope_valid and observed else "blocked",
            "snapshot",
            "Snapshot scope must match exact expected cluster IDs and the subscription allowlist.",
        )
        manifest = snapshot.collection_manifest
        add(
            "snapshot.tenant",
            "unknown"
            if manifest is None
            else "pass"
            if manifest.tenant_id == str(profile.scope.tenant_id)
            else "blocked",
            "snapshot",
            "Snapshot tenant must match the configured tenant; names are not join keys.",
        )
        maximum_age = profile.analysis.thresholds.maximum_evidence_age_hours * 3600
        inventory_fresh = 0 <= (evaluated_at - snapshot.generated_at).total_seconds() <= maximum_age
        add(
            "snapshot.freshness",
            "pass" if inventory_fresh else "blocked",
            "snapshot",
            "Snapshot generation must be neither stale nor in the future.",
        )
        window = snapshot.metric_window
        history_valid = (
            snapshot.generated_at >= window.end
            and 0 <= (evaluated_at - window.end).total_seconds() <= maximum_age
            and (window.end - window.start).total_seconds()
            >= profile.analysis.thresholds.minimum_observation_days * 86400
            and window.sample_count > 0
            and window.coverage_ratio >= profile.analysis.thresholds.minimum_coverage_ratio
        )
        add(
            "snapshot.history",
            "pass" if history_valid else "blocked",
            "snapshot",
            "Observed history must meet duration, freshness, and coverage requirements "
            "without extending missing data.",
        )
        results = {result.collector: result for result in manifest.results} if manifest else {}
        collection_valid = manifest is not None
        for collector in ["azure-inventory", "kubernetes-metadata", "prometheus"]:
            result = results.get(collector)
            if result is None:
                collection_valid = False
                continue
            collection_valid = collection_valid and (
                result.status == CollectionStatus.COMPLETE
                and result.completed_at <= snapshot.generated_at
                and result.source_observed_at is not None
                and 0 <= (evaluated_at - result.source_observed_at).total_seconds() <= maximum_age
                and all(_allowed_scope(unit, collector, profile) for unit in result.requested_scope)
                and all(
                    cluster.resource_id in result.completed_scope
                    or (
                        collector == "azure-inventory"
                        and cluster.subscription_id in result.completed_scope
                    )
                    for cluster in snapshot.clusters
                )
            )
        add(
            "snapshot.collection",
            "pass" if collection_valid else "blocked",
            "snapshot",
            "Required collectors must be fresh, complete, and correctly scoped; "
            "optional costs do not gate capacity readiness.",
        )
        quality_status = (
            _entity_quality_status(snapshot, profile, evaluated_at) if scope_valid else "unknown"
        )
        add(
            "snapshot.entity-quality",
            quality_status,
            "snapshot",
            "Per-container CPU, throttling, and OOM observations need aligned, fresh, "
            "sufficiently covered quality metadata.",
        )

    status: Literal["ready", "blocked", "unknown"] = "ready"
    if any(check.status == "blocked" for check in checks):
        status = "blocked"
    elif any(check.status == "unknown" for check in checks):
        status = "unknown"
    return ReadinessReport(
        generated_at=evaluated_at,
        status=status,
        requested_subscriptions=len(profile.scope.subscription_ids),
        requested_clusters=len(profile.clusters),
        configuration_digest=_digest(profile),
        snapshot_digest=_digest(snapshot) if snapshot is not None else None,
        checks=sorted(checks, key=lambda check: (check.scope, check.code)),
    )
