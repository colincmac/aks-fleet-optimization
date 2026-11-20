from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.catalog import Catalog, digest_json, load_catalog
from aks_fleet_efficiency.catalog.models import (
    AssessmentMode,
    CatalogModel,
    Digest,
    PackManifest,
    PackParameters,
    PackProvenance,
    RenderedQuery,
    SourceDefinition,
)
from aks_fleet_efficiency.collection import CollectionPlan, selected_metric_inputs
from aks_fleet_efficiency.collectors.azure_resource_graph import inventory_query
from aks_fleet_efficiency.collectors.metric_queries import metric_labels, render_query
from aks_fleet_efficiency.collectors.prometheus import (
    PrometheusMetricCollector,
    RangeQueryResult,
)
from aks_fleet_efficiency.config import AdvisorConfig, OnboardingConfig
from aks_fleet_efficiency.models import (
    CollectionStatus,
    CollectorResult,
    MetricQuality,
    MetricQueryPlan,
    SourceCapability,
    UtcDatetime,
)
from aks_fleet_efficiency.source_acceptance import PrometheusSourceAcceptance

GUARDED_NOTICE = (
    "Guarded mode is not approval. Numeric proposals require independent owner policy, "
    "complete identity-bound evidence, reliability gates and a one-dimensional canary/rollback. "
    "Configuration never enables owner opt-ins or changes a cluster."
)


class ParameterGuidance(CatalogModel):
    unit: str
    bounds: str
    implication: str


class OperatorCard(CatalogModel):
    manifest: PackManifest
    provenance: PackProvenance
    parameter_guidance: dict[str, ParameterGuidance]
    synthetic_example: AdvisorConfig


class OperatorCatalog(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    cards: list[OperatorCard]
    glossary: dict[str, str]
    guarded_notice: str = GUARDED_NOTICE


class OperatorInspection(CatalogModel):
    card: OperatorCard
    mode: AssessmentMode
    capabilities: list[SourceCapability]
    resolved_queries: list[RenderedQuery] = Field(default_factory=list)


class PreviewOperation(CatalogModel):
    method: Literal["POST", "GET", "local-read"]
    endpoint: str
    scope: list[str]
    query: str | None = None
    detail: str


class ExecutionPreview(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["offline"] = "offline"
    generated_at: UtcDatetime
    configuration_digest: str
    plan_digest: str
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: int
    packs: list[PackProvenance]
    operations: list[PreviewOperation]
    queries: list[RenderedQuery]
    query_plan: MetricQueryPlan
    budgets: dict[str, int]
    excluded_fields: list[str]
    artifact_destination: str
    unresolved_prerequisites: list[str] = Field(min_length=1)
    capabilities: list[SourceCapability]
    notice: str = "Preview only; no clients, credentials, source exports or endpoints were read."


class RetainedQueryQuality(CatalogModel):
    query: RenderedQuery
    unit: Literal["mCPU", "MiB", "ratio", "events", "pods", "boolean"]
    status: Literal["matched", "unknown", "blocked"]
    reason_codes: list[str]
    quality: MetricQuality | None = None
    latest_sample_at: UtcDatetime | None = None
    receipt_digest: Digest | None = None
    source_profile_digest: Digest | None = None
    observation_digest: Digest | None = None

    @model_validator(mode="after")
    def validate_match(self) -> RetainedQueryQuality:
        if self.status == "matched":
            if (
                self.reason_codes
                or self.quality is None
                or self.latest_sample_at is None
                or self.receipt_digest is None
                or self.source_profile_digest is None
                or self.observation_digest is None
            ):
                raise ValueError("Matched retained quality requires original execution evidence")
        elif not self.reason_codes:
            raise ValueError("Unmatched retained quality requires explicit reasons")
        return self


class RetainedAssessmentQuality(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["retained-assessment"] = "retained-assessment"
    run_id: Digest
    evaluated_at: UtcDatetime
    cluster_resource_id: str
    cluster_uid: str
    window_start: UtcDatetime
    window_end: UtcDatetime
    assessment_status: Literal["complete", "partial"]
    source_profile: SourceDefinition
    receipts: list[CollectorResult]
    records: list[RetainedQueryQuality] = Field(min_length=1, max_length=1000)
    live_quality: Literal["unknown"] = "unknown"
    notice: Literal[
        "Original retained execution only, not live datasource quality, source authentication, "
        "finding eligibility or change approval. Logical source names do not identify an endpoint."
    ] = (
        "Original retained execution only, not live datasource quality, source authentication, "
        "finding eligibility or change approval. Logical source names do not identify an endpoint."
    )

    @model_validator(mode="after")
    def validate_bindings(self) -> RetainedAssessmentQuality:
        if self.window_end <= self.window_start or self.evaluated_at < self.window_end:
            raise ValueError("Retained quality requires an ordered original window and clock")
        keys = [
            (record.query.source, record.query.metric, record.query.entity_digest)
            for record in self.records
        ]
        if len(set(keys)) != len(keys) or len({key[0] for key in keys}) != 1:
            raise ValueError("Retained quality requires distinct queries from one logical source")
        receipts = {
            digest_json(receipt.model_dump(mode="json")): receipt for receipt in self.receipts
        }
        profile_digest = digest_json(self.source_profile.model_dump(mode="json"))
        for record in self.records:
            if record.receipt_digest is not None and record.receipt_digest not in receipts:
                raise ValueError("Retained query receipt must belong to its original context")
            if record.status != "matched":
                continue
            quality = record.quality
            receipt = receipts[record.receipt_digest or ""]
            if (
                quality is None
                or receipt.status != CollectionStatus.COMPLETE
                or set(receipt.requested_scope) != {self.cluster_resource_id}
                or record.source_profile_digest != profile_digest
                or quality.query_asset_version != record.query.version
                or quality.query_expression != record.query.expression
                or quality.source != record.query.source
                or quality.unit != record.unit
                or quality.step_seconds != record.query.step_seconds
                or quality.window.start != self.window_start
                or quality.window.end != self.window_end
            ):
                raise ValueError("Matched retained quality requires exact execution bindings")
        return self


def retained_query_quality(
    directory: Path,
    queries: list[RenderedQuery],
    source_profile: SourceDefinition,
    *,
    tenant_id: str,
) -> RetainedAssessmentQuality:
    from aks_fleet_efficiency.assessment import AssessmentFragments
    from aks_fleet_efficiency.history import _digest, _read_verified_archive

    source_profile = SourceDefinition.model_validate(source_profile.model_dump())
    queries = [RenderedQuery.model_validate(query.model_dump()) for query in queries]
    keys = [(query.source, query.metric, query.entity_digest) for query in queries]
    if (
        not 1 <= len(keys) <= 1000
        or len(set(keys)) != len(keys)
        or len({query.source for query in queries}) != 1
    ):
        raise ValueError("Retained quality requires distinct queries from one logical source")
    catalog = load_catalog()
    if source_profile != catalog.source(source_profile.id):
        raise ValueError("Retained quality requires the exact installed source profile")
    for query in queries:
        asset = catalog.queries.get(query.metric)
        if (
            asset is None
            or query.version != asset.version
            or query.expression_digest != sha256(query.expression.encode()).hexdigest()
        ):
            raise ValueError("Retained quality requires exact installed query provenance")
    archive, assessment, config = _read_verified_archive(directory, tenant_id=UUID(tenant_id))
    if len(assessment.snapshot.clusters) != 1:
        raise ValueError("Retained quality requires one original cluster assessment")
    cluster = assessment.snapshot.clusters[0]
    if cluster.uid is None or not cluster.uid.strip():
        raise ValueError("Retained quality requires the original cluster fingerprint")
    fragments = AssessmentFragments.model_validate_json(archive.payloads["fragments.json"])
    fingerprints = [
        metadata.cluster_uid
        for metadata in fragments.kubernetes
        if metadata.cluster_resource_id == cluster.resource_id
    ]
    if fingerprints != [cluster.uid]:
        raise ValueError("Retained quality fingerprint must match original cluster metadata")
    report = assessment.report
    window = report.observation_window
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    original_profiles = [
        fragment for fragment in fragments.metrics if fragment.source_name == queries[0].source
    ]
    records = []
    unknown_reasons = {
        "missing_source",
        "missing_entity_series",
        "source_profile_unknown",
        "query_expression_unknown",
        "query_asset_version_unknown",
        "source_clock_unknown",
        "latest_sample_unknown",
    }
    for query in sorted(queries, key=lambda item: (item.source, item.metric, item.entity_digest)):
        reasons = []
        record = RetainedQueryQuality(
            query=query,
            unit=catalog.queries[query.metric].unit,
            status="unknown",
            reason_codes=["missing_source"],
        )
        if len(original_profiles) != 1:
            reasons.append("ambiguous_source" if original_profiles else "missing_source")
        else:
            fragment = original_profiles[0]
            receipt = fragment.collection
            record.receipt_digest = digest_json(receipt.model_dump(mode="json"))
            if fragment.source_profile is None:
                reasons.append("source_profile_unknown")
            else:
                record.source_profile_digest = digest_json(
                    fragment.source_profile.model_dump(mode="json")
                )
                if fragment.source_profile != source_profile:
                    reasons.append("source_profile_mismatch")
            if receipt.collector != "prometheus" or set(receipt.requested_scope) != {
                cluster.resource_id
            }:
                reasons.append("receipt_scope_mismatch")
            if receipt.status != CollectionStatus.COMPLETE:
                reasons.append("incomplete_source")
            if receipt.source_observed_at is None:
                reasons.append("source_clock_unknown")
            elif (report.generated_at - receipt.source_observed_at).total_seconds() > maximum_age:
                reasons.append("stale_source")
            if (
                receipt.completed_at > fragment.generated_at
                or fragment.generated_at > report.generated_at
                or (
                    receipt.source_observed_at is not None
                    and receipt.source_observed_at > receipt.completed_at
                )
            ):
                reasons.append("future_source")
            if (
                fragment.query_start != window.start
                or fragment.query_end != window.end
                or fragments.window_start != window.start
                or fragments.window_end != window.end
            ):
                reasons.append("window_mismatch")
            observations = [
                item
                for item in fragment.observations
                if item.metric == query.metric
                and digest_json(item.entity.model_dump(mode="json")) == query.entity_digest
            ]
            if len(observations) != 1:
                reasons.append("ambiguous_series" if observations else "missing_entity_series")
            else:
                observation = observations[0]
                quality = observation.quality
                record.quality = quality
                record.latest_sample_at = observation.latest_sample_at
                record.observation_digest = digest_json(observation.model_dump(mode="json"))
                if quality.query_expression is None:
                    reasons.append("query_expression_unknown")
                elif quality.query_expression != query.expression:
                    reasons.append("query_expression_mismatch")
                if quality.query_asset_version is None:
                    reasons.append("query_asset_version_unknown")
                elif quality.query_asset_version != query.version:
                    reasons.append("query_version_mismatch")
                if quality.query_version != fragment.query_version:
                    reasons.append("query_adapter_version_mismatch")
                if quality.source != query.source:
                    reasons.append("metric_source_mismatch")
                if quality.unit != record.unit:
                    reasons.append("unit_mismatch")
                if (
                    quality.step_seconds != query.step_seconds
                    or quality.step_seconds > config.thresholds.maximum_metric_step_seconds
                ):
                    reasons.append("step_mismatch")
                if not quality.window.sample_count:
                    reasons.append("missing_samples")
                expected_samples = ceil(
                    (quality.window.end - quality.window.start).total_seconds()
                    / quality.step_seconds
                )
                if quality.window.coverage_ratio > min(
                    1, (quality.window.sample_count + 1) / expected_samples
                ):
                    reasons.append("inconsistent_coverage")
                if quality.window.coverage_ratio < config.thresholds.minimum_coverage_ratio:
                    reasons.append("low_coverage")
                if quality.observed_at > fragment.generated_at:
                    reasons.append("future_metric_observation")
                elif (report.generated_at - quality.observed_at).total_seconds() > maximum_age:
                    reasons.append("stale_metric_observation")
                if observation.latest_sample_at is None:
                    reasons.append("latest_sample_unknown")
                elif not window.start <= observation.latest_sample_at <= window.end:
                    reasons.append("sample_time_mismatch")
                elif (
                    window.end - observation.latest_sample_at
                ).total_seconds() > query.step_seconds:
                    reasons.append("stale_sample_tail")
                if observation.issues:
                    reasons.append("observation_issues")
        record.reason_codes = sorted(set(reasons))
        record.status = (
            "blocked" if set(reasons) - unknown_reasons else "unknown" if reasons else "matched"
        )
        records.append(RetainedQueryQuality.model_validate(record.model_dump()))
    return RetainedAssessmentQuality(
        run_id=_digest(archive),
        evaluated_at=report.generated_at,
        cluster_resource_id=cluster.resource_id,
        cluster_uid=cluster.uid,
        window_start=window.start,
        window_end=window.end,
        assessment_status=assessment.status,
        source_profile=source_profile,
        receipts=[fragment.collection for fragment in original_profiles],
        records=records,
    )


def build_operator_catalog(catalog: Catalog) -> OperatorCatalog:
    cards = []
    bounds = {
        "cpu-request-review": "0 < review_ratio < 1",
        "cpu-request-risk": "review_ratio > 0",
        "node-pool-review": "0 <= review_ratio < 1",
    }
    for pack in sorted(catalog.manifests.values(), key=lambda item: item.id):
        parameters = {}
        if pack.parameters.review_ratio is not None:
            parameters["review_ratio"] = ParameterGuidance(
                unit="ratio",
                bounds=bounds[pack.evaluator],
                implication=(
                    "Investigation threshold only, not a utilization target or proposal bound. "
                    "Equality produces no signal; safety/owner gates cannot be overridden."
                ),
            )
        provenance = catalog.provenance(pack.id)
        cards.append(
            OperatorCard(
                manifest=pack,
                provenance=provenance,
                parameter_guidance=parameters,
                synthetic_example=AdvisorConfig(
                    packs=[pack.id],
                    pack_parameters={pack.id: pack.parameters},
                    pack_locks={pack.id: provenance.digest},
                ),
            )
        )
    return OperatorCatalog(
        cards=cards,
        glossary={
            "baseline": "Qualified investigations only; no numeric resource or replica proposals.",
            "guarded": GUARDED_NOTICE,
            "coverage": "Returned evaluation points, not proof of raw scrape completeness.",
            "identity": (
                "Historical UIDs and exact Azure IDs; current names cannot backfill history."
            ),
            "unknown": "Missing or unsupported evidence is not zero or proof of health.",
            "query-only": "Executable exports measure signals; they do not pass assessment gates.",
            "provenance": "Pack/query versions and digests bind replay, not source attestation.",
            "mCPU": "One thousandth of a CPU core.",
            "MiB": "1,048,576 bytes; working set and full usage are distinct measurements.",
            "ratio": "Dimensionless fraction; not a universal utilization target.",
            "events": "Complete interval counts; missing intervals are not zero.",
            "pods": "Sampled replica counts, not availability or safe capacity by themselves.",
            "boolean": "Explicit observed state; missing observations remain unknown.",
        },
    )


def _markdown(value: str) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", lambda match: f"\\u{ord(match.group()):04x}", value)
    escaped = html.escape(value, quote=False)
    return re.sub(r"([\\`*_\[\]{}()#!|>])", r"\\\1", escaped).replace("\n", " ")


def render_operator_catalog(catalog: OperatorCatalog) -> str:
    lines = [
        "# Generated operator catalog",
        "",
        "Generated from packaged manifests. Do not edit; "
        "run `scripts/generate_operator_catalog.py`.",
        "",
        catalog.guarded_notice,
        "",
        "## Glossary",
        "",
    ]
    for term, meaning in catalog.glossary.items():
        lines.append(f"- **{_markdown(term)}**: {_markdown(meaning)}")
    for card in catalog.cards:
        pack = card.manifest
        lines.extend(
            [
                "",
                f"## {pack.id}: {_markdown(pack.title)}",
                "",
                f"Version: {pack.version}; family: {pack.family}; evidence: {pack.evidence_kind}.",
                "",
                _markdown(pack.purpose),
                "",
                f"Pack/query digest: `{card.provenance.digest}`.",
                "",
                f"Baseline: {_markdown(pack.baseline_summary)}",
                "",
                f"Guarded: {_markdown(pack.guarded_summary)}",
                "",
                "### Review parameters",
                "",
            ]
        )
        if not card.parameter_guidance:
            lines.append("No pack ratio controls. Proposal bounds belong to owner policy.")
        for name, guidance in card.parameter_guidance.items():
            lines.append(
                f"- {name}: default {getattr(pack.parameters, name)} {guidance.unit}; "
                f"{_markdown(guidance.bounds)}. {_markdown(guidance.implication)}"
            )
        if pack.summary_variants:
            lines.extend(["", "### Evidence-selected summaries", ""])
            lines.extend(
                f"- {_markdown(code)}: {_markdown(text)}"
                for code, text in pack.summary_variants.items()
            )
        for label, values in [
            ("Prerequisites", pack.prerequisites),
            ("Limitations", pack.limitations),
            ("Risks", pack.risks),
            ("Validation", pack.validation),
            ("Rollback", pack.rollback),
            ("Baseline rollback", pack.baseline_rollback),
        ]:
            lines.extend(["", f"### {label}", ""])
            lines.extend(f"- {_markdown(value)}" for value in values)
        for mode in ("baseline", "guarded"):
            lines.extend(["", f"### {mode.title()} evidence and actions", ""])
            lines.extend(f"- {_markdown(value)}" for value in pack.required_evidence[mode])
            lines.extend(f"- {_markdown(value)}" for value in pack.actions[mode])
        lines.extend(["", "### Query templates (not executable exports)", ""])
        if not card.provenance.queries:
            lines.append("Inventory-only; no metric endpoint or PromQL required.")
        for query in card.provenance.queries:
            lines.extend(
                [
                    f"- {query.id} v{query.version}, {query.kind}, {query.unit}.",
                    f"  Template: {_markdown(query.expression)}",
                ]
            )
        lines.extend(
            [
                "",
                "### Synthetic baseline configuration example",
                "",
                "This selects a pack, not a healthy result or owner approval.",
                "",
                "```json",
                card.synthetic_example.model_dump_json(indent=2),
                "```",
                "",
                f"Inspect: `aks-fleet-advisor catalog show {pack.id}`.",
            ]
        )
    return "\n".join(lines) + "\n"


def configure_profile(
    profile: OnboardingConfig, packs: list[str], mode: AssessmentMode, ratios: dict[str, float]
) -> OnboardingConfig:
    catalog = load_catalog()
    payload = profile.model_dump()
    analysis = payload["analysis"]
    analysis.update(
        packs=packs,
        mode=mode,
        pack_parameters={
            name: PackParameters(review_ratio=value).model_dump() for name, value in ratios.items()
        },
        pack_locks={name: catalog.provenance(name).digest for name in packs},
    )
    for name in packs:
        analysis["pack_parameters"].setdefault(
            name,
            profile.analysis.pack_parameters.get(name, catalog.pack(name).parameters).model_dump(),
        )
    return OnboardingConfig.model_validate(payload)


class _NoMetricReads:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult:
        raise RuntimeError("Offline preview cannot execute metric requests")


def preview_execution(
    profile: OnboardingConfig, plan: CollectionPlan, *, as_of: datetime
) -> ExecutionPreview:
    profile = OnboardingConfig.model_validate(profile.model_dump())
    plan = CollectionPlan.model_validate(plan.model_dump())
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Preview requires an aware evaluation time")
    targets = {target.resource_id: target for target in profile.clusters}
    if set(targets) != {target.resource_id for target in plan.clusters}:
        raise ValueError("Collection plan exceeds approved scope")
    end = plan.window_end or as_of.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = plan.window_start or end - timedelta(
        days=profile.analysis.thresholds.minimum_observation_days
    )
    if end > as_of or plan.step_seconds > profile.analysis.thresholds.maximum_metric_step_seconds:
        raise ValueError("Collection window or resolution exceeds approved bounds")
    if any(
        binding.safety_policy.reviewed_window_start != start
        or binding.safety_policy.reviewed_window_end != end
        for binding in plan.workload_assessments
    ):
        raise ValueError("Historical policy must review the exact requested window")
    catalog = load_catalog()
    operations = []
    for subscription in sorted({str(target.subscription_id) for target in profile.clusters}):
        scope = {
            target.resource_id
            for target in profile.clusters
            if str(target.subscription_id) == subscription
        }
        operations.append(
            PreviewOperation(
                method="POST",
                endpoint="https://management.azure.com/providers/Microsoft.ResourceGraph/resources",
                scope=[subscription],
                query=inventory_query(scope),
                detail="Read-only ARG query; page size 250, at most 20 pages per subscription.",
            )
        )
    unresolved = [
        "Independent operator consent, read-only identity, tenant and endpoint access "
        "are untested.",
        GUARDED_NOTICE,
        "Source history, coverage, freshness, membership and owner evidence remain unverified.",
        "Artifact destination is configured, not created; execution requires explicit "
        "--artifacts/--output flags matching the reviewed preview.",
    ]
    queries: list[RenderedQuery] = []
    plans: list[MetricQueryPlan] = []
    for target in plan.clusters:
        operations.append(
            PreviewOperation(
                method="local-read",
                endpoint=str(target.metadata_export)
                if target.metadata_export
                else "metadata_export: unset",
                scope=[target.resource_id],
                detail="Sanitized metadata import only; CLI performs no Kubernetes API calls.",
            )
        )
        unresolved.append(
            f"{target.resource_id}: metadata_export/fingerprint/projection must be validated "
            "at execution; preview reads no export files."
        )
        metrics, entities = selected_metric_inputs(profile, target)
        kinds = {entity.kind for entity in target.entities}
        required = {
            name
            for pack_id in (profile.analysis.packs or catalog.default_pack_ids)
            for kind, names in catalog.pack(pack_id).queries[profile.analysis.mode].items()
            if not kinds or kind in kinds
            for name in names
        }
        if required - set(metrics) or (required and not entities):
            unresolved.append(f"{target.resource_id}: selected pack metrics/entities are missing.")
        if not entities:
            continue
        source_name = targets[target.resource_id].metric_source
        if source_name is None:
            raise ValueError("Metric entities require an approved source")
        source = next(item for item in profile.metric_sources if item.name == source_name)
        collector = PrometheusMetricCollector(
            profile,
            source_name=source_name,
            reader=_NoMetricReads(source_name),
            entities=entities,
            clock=lambda: as_of,
            max_retries=0,
            max_queries=plan.maximum_queries,
            maximum_evaluations=plan.maximum_metric_evaluations,
            maximum_series=plan.maximum_series_per_response,
        )
        if collector.source_definition.identity == "name-only" and (
            set(metrics) - set(collector.source_definition.query_ids)
        ):
            raise ValueError("Unsupported metric for the declared name-only source")
        plans.append(
            collector.plan_queries(
                start=start, end=end, step_seconds=plan.step_seconds, metrics=metrics
            )
        )
        operations.append(
            PreviewOperation(
                method="GET",
                endpoint=str(source.endpoint).rstrip("/") + "/api/v1/query_range",
                scope=[target.resource_id],
                detail=(
                    f"{source.authentication}; step {plan.step_seconds}s, chunks of "
                    f"{collector.chunk_samples} points; delta queries offset one step. "
                    "HTTP timeout 30s, response 16 MiB/1000 series, no redirects; no retries."
                ),
            )
        )
        if source.authentication == "bearer-environment":
            unresolved.append("CLI cannot read bearer values; inject an approved reader via SDK.")
        for entity in entities:
            for name in metrics:
                if collector.applicable(name, entity):
                    query = catalog.queries[name]
                    expression = render_query(
                        query.expression,
                        metric_labels(entity, source, name),
                        plan.step_seconds,
                    )
                    rendered = RenderedQuery(
                        metric=name,
                        version=query.version,
                        source=source_name,
                        expression=expression,
                        expression_digest=sha256(expression.encode()).hexdigest(),
                        entity_digest=digest_json(entity.model_dump(mode="json")),
                        step_seconds=plan.step_seconds,
                    )
                    if rendered not in queries:
                        queries.append(rendered)
    total = MetricQueryPlan(
        logical_queries=sum(item.logical_queries for item in plans),
        unique_queries=sum(item.unique_queries for item in plans),
        requests=sum(item.requests for item in plans),
        expected_evaluations=sum(item.expected_evaluations for item in plans),
        maximum_series=plan.maximum_series_per_response,
    )
    if total.requests > plan.maximum_queries or (
        total.expected_evaluations > plan.maximum_metric_evaluations
    ):
        raise ValueError("Collection exceeds total query/evaluation budget")
    if total.requests + len(operations) > plan.maximum_reads:
        unresolved.append(
            "Global read budget may stop collection before all pages/queries complete."
        )
    return ExecutionPreview(
        generated_at=as_of,
        configuration_digest=digest_json(profile.model_dump(mode="json")),
        plan_digest=digest_json(plan.model_dump(mode="json")),
        window_start=start,
        window_end=end,
        step_seconds=plan.step_seconds,
        packs=[
            catalog.provenance(name, profile.analysis.pack_parameters.get(name))
            for name in sorted(profile.analysis.packs or catalog.default_pack_ids)
        ],
        operations=operations,
        queries=queries,
        query_plan=total,
        budgets={
            name: value
            for name, value in plan.model_dump().items()
            if name.startswith("maximum_") and isinstance(value, int)
        },
        excluded_fields=[
            "Secrets and ConfigMap bodies",
            "Environment values and credentials",
            "Logs, request payloads and termination messages",
        ],
        artifact_destination=str(profile.report_directory),
        unresolved_prerequisites=unresolved,
        capabilities=[
            capability
            for pack_id in sorted(profile.analysis.packs or catalog.default_pack_ids)
            for capability in evaluate_source_capabilities(
                profile, [], pack_id=pack_id, as_of=as_of
            )
            if capability.mode == profile.analysis.mode
        ],
    )


def _query_journey(metric: str) -> str:
    if metric in {
        "oom_events",
        "replica_oom_events",
        "restarts",
        "replica_restarts",
        "evictions",
    }:
        return "Reliability"
    if metric.startswith("hpa_") or metric in {
        "desired_replicas",
        "available_replicas",
        "observed_replicas",
        "hpa_present",
        "keda_present",
        "vpa_present",
    }:
        return "Autoscaling"
    if metric.startswith("node_"):
        return "Node capacity"
    if metric == "unschedulable_pods":
        return "Scheduling"
    if "memory" in metric:
        return "Workload memory"
    return "Workload CPU"


def grafana_dashboard(
    queries: list[RenderedQuery],
    source_profile: SourceDefinition,
    *,
    retained_quality: RetainedAssessmentQuality | None = None,
    source_acceptance: PrometheusSourceAcceptance | None = None,
) -> dict[str, Any]:
    if not queries:
        raise ValueError("Grafana export requires scope-bound queries")
    catalog = load_catalog()
    grouped: dict[str, list[RenderedQuery]] = {}
    for query in queries:
        grouped.setdefault(_query_journey(query.metric), []).append(query)
    source_names = _markdown(", ".join(sorted({query.source for query in queries})))
    steps = ", ".join(str(value) for value in sorted({query.step_seconds for query in queries}))
    quality_content = (
        f"**Source:** `{source_names}`  \n"
        f"**Profile:** `{source_profile.id}` v{source_profile.version} "
        f"({source_profile.identity} identity)  \n"
        f"**Window:** Grafana time picker; not a retained assessment window  \n"
        f"**Minimum query step:** {steps} seconds; Grafana may coarsen it  \n\n"
        "Coverage: **unknown** until source execution and assessment.  \n"
        "Freshness: **unknown** until source execution and assessment.  \n"
        "Missing series: **unknown** until these queries run against the selected datasource.  \n"
        "A rendered query, visible series, or empty panel does not attest source completeness, "
        "historical identity, approval, or a safe target."
    )
    panels: list[dict[str, Any]] = [
        {
            "id": 1,
            "title": "Evidence quality and missing series",
            "description": "Export metadata and unresolved evidence-quality limits.",
            "type": "text",
            "gridPos": {"x": 0, "y": 0, "w": 24, "h": 6},
            "options": {"mode": "markdown", "content": quality_content},
        }
    ]
    panel_id = 2
    y = 6
    if source_acceptance is not None:
        source_acceptance = PrometheusSourceAcceptance.model_validate(
            source_acceptance.model_dump()
        )
        query_keys = {(query.metric, query.version, query.expression_digest) for query in queries}
        acceptance_keys = {
            (record.query_id, record.query_version, record.expression_digest)
            for record in source_acceptance.records
        }
        if (
            source_acceptance.source_profile_id != source_profile.id
            or source_acceptance.source_profile_version != source_profile.version
            or {query.source for query in queries} != {source_acceptance.source}
            or query_keys != acceptance_keys
            or {query.step_seconds for query in queries} != {source_acceptance.step_seconds}
        ):
            raise ValueError(
                "Source acceptance must match the exact exported queries, source and profile"
            )
        content = [
            "**Supplied fixed window evidence, not mutable live Grafana quality.**",
            "Query bindings match this export; the original execution was not "
            "independently replayed.",
            "",
            f"Input digest: `{source_acceptance.input_digest}`  ",
            f"Cluster: {_markdown(source_acceptance.cluster_resource_id)}  ",
            f"Fingerprint: {_markdown(source_acceptance.cluster_uid)}  ",
            f"Evaluated: {source_acceptance.evaluated_at.isoformat()}  ",
            f"Fixed window: {source_acceptance.window_start.isoformat()} "
            f"to {source_acceptance.window_end.isoformat()}  ",
            f"Acceptance: {source_acceptance.status}  ",
            "Live time picker: unknown",
            "",
            "| Metric/expression | Status | Roster | Duplicates | Latest UTC | Reasons |",
            "|---|---|---|---|---|---|",
        ]
        for acceptance_record in source_acceptance.records:
            latest_sample = (
                acceptance_record.latest_sample_at.isoformat()
                if acceptance_record.latest_sample_at
                else "unknown"
            )
            content.append(
                f"| {acceptance_record.query_id}/{acceptance_record.expression_digest} | "
                f"{acceptance_record.status} | "
                f"{acceptance_record.matched_expected_entities}/"
                f"{acceptance_record.expected_entities} | "
                f"{acceptance_record.duplicate_series} | "
                f"{latest_sample} | "
                f"{_markdown(', '.join(acceptance_record.reason_codes))} |"
            )
        content.extend(["", source_acceptance.notice])
        panels.append(
            {
                "id": panel_id,
                "title": "Supplied source acceptance",
                "description": (
                    "Supplied fixed-window evidence; live time-picker quality unknown."
                ),
                "type": "text",
                "gridPos": {"x": 0, "y": y, "w": 24, "h": 12},
                "options": {"mode": "markdown", "content": "\n".join(content)},
            }
        )
        panel_id += 1
        y += 12
    if retained_quality is not None:
        retained_quality = RetainedAssessmentQuality.model_validate(retained_quality.model_dump())
        if retained_quality.source_profile != source_profile or {
            digest_json(retained_record.query.model_dump(mode="json"))
            for retained_record in retained_quality.records
        } != {digest_json(query.model_dump(mode="json")) for query in queries}:
            raise ValueError("Retained quality must match the exact exported queries and profile")
        content = [
            "**Retained evidence only, not live Grafana quality.**",
            "",
            f"Original bundle: `{retained_quality.run_id}`  ",
            f"Cluster: {_markdown(retained_quality.cluster_resource_id)}  ",
            f"Fingerprint: {_markdown(retained_quality.cluster_uid)}  ",
            f"Evaluated: {retained_quality.evaluated_at.isoformat()}  ",
            f"Window: {retained_quality.window_start.isoformat()} "
            f"to {retained_quality.window_end.isoformat()}  ",
            f"Assessment: {retained_quality.assessment_status}",
            "",
            "| Metric/entity | Retained match | Coverage | Observed UTC | Reasons |",
            "|---|---|---|---|---|",
        ]
        for retained_record in retained_quality.records:
            quality = retained_record.quality
            content.append(
                f"| {retained_record.query.metric}/{retained_record.query.entity_digest} | "
                f"{retained_record.status} | "
                f"{quality.window.coverage_ratio if quality else 'unknown'} | "
                f"{quality.observed_at.isoformat() if quality else 'unknown'} | "
                f"{_markdown(', '.join(retained_record.reason_codes))} |"
            )
        content.extend(["", retained_quality.notice])
        panels.append(
            {
                "id": panel_id,
                "title": "Retained assessment quality",
                "description": "Original replay-verified evidence; live quality unknown.",
                "type": "text",
                "gridPos": {"x": 0, "y": y, "w": 24, "h": 12},
                "options": {"mode": "markdown", "content": "\n".join(content)},
            }
        )
        panel_id += 1
        y += 12
    for journey in [
        "Node capacity",
        "Workload CPU",
        "Workload memory",
        "Reliability",
        "Autoscaling",
        "Scheduling",
    ]:
        journey_queries = grouped.get(journey, [])
        if not journey_queries:
            continue
        panels.append(
            {
                "id": panel_id,
                "title": journey,
                "type": "row",
                "collapsed": False,
                "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
            }
        )
        panel_id += 1
        y += 1
        for index, query in enumerate(journey_queries):
            unit = catalog.queries[query.metric].unit
            panels.append(
                {
                    "id": panel_id,
                    "title": f"{query.metric} v{query.version}",
                    "fieldConfig": {"defaults": {"unit": f"suffix:{unit}"}},
                    "description": (
                        f"Source {query.source}; profile {source_profile.id} "
                        f"v{source_profile.version}; entity {query.entity_digest}; "
                        f"minimum step {query.step_seconds}s; unit {unit}. Grafana may coarsen "
                        "evaluation and its time range is the "
                        "query window, not retained assessment evidence."
                    ),
                    "type": "timeseries",
                    "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
                    "gridPos": {
                        "x": (index % 2) * 12,
                        "y": y + (index // 2) * 8,
                        "w": 12,
                        "h": 8,
                    },
                    "targets": [
                        {
                            "refId": "A",
                            "expr": query.expression,
                            "interval": f"{query.step_seconds}s",
                            "format": "time_series",
                        }
                    ],
                }
            )
            panel_id += 1
        y += ((len(journey_queries) + 1) // 2) * 8
    return {
        "title": "AKS advisor query-only measurements",
        "description": "Measurements only, not safe-change approval or source attestation.",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "__inputs": [
            {
                "name": "DS_PROMETHEUS",
                "label": "Approved Prometheus source",
                "type": "datasource",
                "pluginId": "prometheus",
                "pluginName": "Prometheus",
            }
        ],
        "panels": panels,
    }


def generated_operator_assets(root: Path) -> dict[Path, str]:
    from pydantic import RootModel

    from aks_fleet_efficiency.artifacts import read_model
    from aks_fleet_efficiency.collection import ClusterCollectionPlan
    from aks_fleet_efficiency.config import load_onboarding_config
    from aks_fleet_efficiency.models import MetricEntity

    catalog = build_operator_catalog(load_catalog())
    profile = load_onboarding_config(root / "examples" / "cpu-pack-config.yaml")
    inspection = OperatorInspection(
        card=next(card for card in catalog.cards if card.manifest.id == "AKS-RQ-002"),
        mode="guarded",
        capabilities=[
            item
            for item in evaluate_source_capabilities(
                profile,
                [],
                pack_id="AKS-RQ-002",
                as_of=datetime(2026, 10, 29, 12, tzinfo=UTC),
            )
            if item.mode == "guarded"
        ],
    )
    plan = CollectionPlan(
        window_start=datetime(2026, 9, 29, tzinfo=UTC),
        window_end=datetime(2026, 10, 29, tzinfo=UTC),
        clusters=[
            ClusterCollectionPlan(
                resource_id=profile.clusters[0].resource_id,
                expected_cluster_uid="synthetic-cluster-uid",
                entities=read_model(
                    root / "examples" / "cpu-pack-entities.json",
                    RootModel[list[MetricEntity]],
                ).root,
            )
        ],
    )
    return {
        root / "docs" / "operator-catalog.md": render_operator_catalog(catalog),
        root / "examples" / "operator-catalog.json": catalog.model_dump_json(indent=2) + "\n",
        root / "examples" / "operator-inspection.json": inspection.model_dump_json(indent=2) + "\n",
        root / "examples" / "operator-plan.json": plan.model_dump_json(indent=2) + "\n",
    }
