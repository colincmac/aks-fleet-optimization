from __future__ import annotations

from datetime import UTC, datetime

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.catalog.models import AssessmentMode, EntityKind
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import (
    CapabilityCheck,
    PrometheusMetricsSnapshot,
    SourceCapability,
)


def evaluate_source_capabilities(
    profile: OnboardingConfig,
    metrics: list[PrometheusMetricsSnapshot],
    *,
    pack_id: str,
    as_of: datetime,
) -> list[SourceCapability]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Capability evaluation time must be aware")
    as_of = as_of.astimezone(UTC)
    catalog = load_catalog()
    pack = catalog.pack(pack_id)
    if pack.evidence_kind == "inventory":
        return []
    targets = {item.resource_id: item for item in profile.clusters}
    for fragment in metrics:
        if fragment.tenant_id != str(profile.scope.tenant_id):
            raise ValueError("Capability evidence exceeds tenant scope")
        for scope in fragment.collection.requested_scope:
            if scope not in targets or targets[scope].metric_source != fragment.source_name:
                raise ValueError("Capability evidence exceeds approved source/cluster scope")
        for observation in fragment.observations:
            if observation.entity.cluster_resource_id not in fragment.collection.requested_scope:
                raise ValueError("Capability metric has foreign scope")
    result: list[SourceCapability] = []
    for target in profile.clusters:
        source = next(
            (item for item in profile.metric_sources if item.name == target.metric_source), None
        )
        if source is None:
            continue
        definition = catalog.source(source.catalog_profile)
        fragments = [
            fragment
            for fragment in metrics
            if fragment.source_name == source.name
            and target.resource_id in fragment.collection.requested_scope
        ]
        modes: tuple[AssessmentMode, ...] = ("baseline", "guarded")
        for mode in modes:
            checks: list[CapabilityCheck] = []

            def add(
                code: str, status: str, reason: str, *, records: list[CapabilityCheck] = checks
            ) -> None:
                records.append(
                    CapabilityCheck.model_validate(
                        {"code": code, "status": status, "reason_codes": [reason]}
                    )
                )

            if source.type not in definition.transports or source.type not in pack.sources:
                add("profile.transport", "unsupported", "unsupported_transport")
            else:
                add("profile.transport", "available", "declared_transport")
            uncharacterized = any(
                name not in definition.characterized_versions
                or value not in definition.characterized_versions[name]
                for name, value in source.component_versions.items()
            )
            add(
                "profile.versions",
                "unsupported"
                if uncharacterized
                else "available"
                if source.component_versions
                else "unknown",
                "uncharacterized_version"
                if uncharacterized
                else "synthetic_characterization"
                if source.component_versions
                else "versions_not_declared",
            )
            if definition.identity == "name-only" and mode == "guarded":
                add("history.identity", "unsupported", "historical_identity_unavailable")
            else:
                add("history.identity", "available", "declared_identity_shape")
            if (
                definition.identity == "name-only"
                and "unresolved_container" not in pack.queries[mode]
            ):
                add("history.identity", "unsupported", "identity_shape_mismatch")
            kind: EntityKind = (
                "unresolved_container" if definition.identity == "name-only" else "container"
            )
            if (
                definition.identity == "historical"
                and fragments
                and not any(item.entity.kind == "container" for item in fragments[0].observations)
                and any(
                    item.entity.kind == "workload_container" for item in fragments[0].observations
                )
            ):
                kind = "workload_container"
            kinds: list[EntityKind] = [kind]
            if definition.identity == "historical":
                supported: list[EntityKind] = [
                    expected
                    for expected in pack.queries[mode]
                    if expected != "unresolved_container"
                ]
                kinds = (
                    supported
                    if pack.evaluator == "hpa-floor-proposal"
                    else [
                        expected
                        for expected in supported
                        if fragments
                        and any(item.entity.kind == expected for item in fragments[0].observations)
                    ]
                    or supported
                )
            references = [
                (expected, name)
                for expected in kinds
                for name in pack.queries[mode].get(expected, [])
            ]
            if not fragments:
                add("source.evidence", "unknown", "not_collected")
            elif len(fragments) != 1:
                add("source.evidence", "unsupported", "ambiguous_source")
            else:
                fragment = fragments[0]
                maximum_age = profile.analysis.thresholds.maximum_evidence_age_hours * 3600
                if fragment.collection.status != "complete":
                    add("source.receipt", "unknown", "partial_source")
                if fragment.collection.source_observed_at is None:
                    add("source.freshness", "unknown", "unknown_source_freshness")
                elif (
                    fragment.collection.source_observed_at > as_of
                    or (as_of - fragment.collection.source_observed_at).total_seconds()
                    > maximum_age
                ):
                    add("source.freshness", "unknown", "stale_evidence")
                if (
                    fragment.generated_at > as_of
                    or (as_of - fragment.generated_at).total_seconds() > maximum_age
                    or fragment.query_end > as_of
                    or (as_of - fragment.query_end).total_seconds() > maximum_age
                ):
                    add("source.freshness", "unknown", "stale_evidence")
                if fragment.source_profile is not None and fragment.source_profile != definition:
                    add("profile.binding", "unsupported", "source_profile_mismatch")
                if any(
                    item.metric in definition.query_ids
                    and (
                        (item.entity.kind == "unresolved_container")
                        != (definition.identity == "name-only")
                    )
                    for item in fragment.observations
                ):
                    add("history.identity", "unsupported", "identity_shape_mismatch")
                for expected_kind, name in references:
                    observations = [
                        item
                        for item in fragment.observations
                        if item.metric == name
                        and item.entity.cluster_resource_id == target.resource_id
                        and item.entity.kind == expected_kind
                    ]
                    identities = [item.entity.model_dump_json() for item in observations]
                    if len(set(identities)) != len(identities):
                        add(name, "unsupported", "ambiguous_series")
                    elif not observations:
                        add(name, "unknown", "not_collected")
                    elif any("missing-series" in item.issues for item in observations):
                        add(name, "unavailable", "missing_series")
                    elif any(
                        item.issues
                        or item.p95 is None
                        or item.quality.unit != catalog.queries[name].unit
                        or item.quality.step_seconds
                        > profile.analysis.thresholds.maximum_metric_step_seconds
                        or item.quality.window.coverage_ratio
                        < profile.analysis.thresholds.minimum_coverage_ratio
                        or item.quality.observed_at > as_of
                        or (as_of - item.quality.observed_at).total_seconds() > maximum_age
                        or item.quality.observed_at > fragment.generated_at
                        or item.quality.window.sample_count == 0
                        or (item.quality.window.end - item.quality.window.start).total_seconds()
                        < profile.analysis.thresholds.minimum_observation_days * 86400
                        or (
                            item.latest_sample_at is not None
                            and (fragment.query_end - item.latest_sample_at).total_seconds()
                            > maximum_age
                        )
                        or (catalog.queries[name].delta and item.total is None)
                        for item in observations
                    ):
                        add(name, "unknown", "insufficient_metric_quality")
                    else:
                        add(name, "available", "series_observed")
            statuses = {check.status for check in checks}
            status = next(
                (value for value in ("unsupported", "unavailable", "unknown") if value in statuses),
                "available",
            )
            result.append(
                SourceCapability.model_validate(
                    {
                        "pack_id": pack.id,
                        "mode": mode,
                        "source": source.name,
                        "cluster_resource_id": target.resource_id,
                        "observed_at": as_of,
                        "source_profile": definition,
                        "status": status,
                        "checks": checks,
                    }
                )
            )
    return result
