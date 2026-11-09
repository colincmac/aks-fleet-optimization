from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.catalog import Catalog, digest_json, load_catalog
from aks_fleet_efficiency.catalog.models import (
    AssessmentMode,
    CatalogModel,
    PackManifest,
    PackParameters,
    PackProvenance,
    RenderedQuery,
)
from aks_fleet_efficiency.collection import CollectionPlan, selected_metric_inputs
from aks_fleet_efficiency.collectors.azure_resource_graph import inventory_query
from aks_fleet_efficiency.collectors.metric_queries import metric_labels, render_query
from aks_fleet_efficiency.collectors.prometheus import (
    PrometheusMetricCollector,
    RangeQueryResult,
)
from aks_fleet_efficiency.config import AdvisorConfig, OnboardingConfig
from aks_fleet_efficiency.models import MetricQueryPlan, SourceCapability, UtcDatetime

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
            for pack_id in (profile.analysis.packs or sorted(catalog.manifests))
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
                        query.expression, metric_labels(entity, source), plan.step_seconds
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
            for name in sorted(profile.analysis.packs or catalog.manifests)
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
            for pack_id in sorted(profile.analysis.packs or catalog.manifests)
            for capability in evaluate_source_capabilities(
                profile, [], pack_id=pack_id, as_of=as_of
            )
            if capability.mode == profile.analysis.mode
        ],
    )


def grafana_dashboard(queries: list[RenderedQuery]) -> dict[str, Any]:
    if not queries:
        raise ValueError("Grafana export requires scope-bound queries")
    catalog = load_catalog()
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
        "panels": [
            {
                "id": index + 1,
                "title": f"{query.metric} v{query.version}",
                "fieldConfig": {
                    "defaults": {"unit": f"suffix:{catalog.queries[query.metric].unit}"}
                },
                "description": f"Source {query.source}; entity {query.entity_digest}; query-only.",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
                "gridPos": {"x": (index % 2) * 12, "y": (index // 2) * 8, "w": 12, "h": 8},
                "targets": [{"refId": "A", "expr": query.expression}],
            }
            for index, query in enumerate(queries)
        ],
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
