from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
import yaml
from pydantic import RootModel

from aks_fleet_efficiency.artifacts import read_model, write_assessment_artifacts, write_exclusive
from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.catalog import load_catalog, render_pack_queries
from aks_fleet_efficiency.catalog.models import AssessmentMode, QueryExportManifest
from aks_fleet_efficiency.collection import collect_fragments
from aks_fleet_efficiency.collectors.cost_management import CostManagementCollector
from aks_fleet_efficiency.config import (
    AdvisorConfig,
    OnboardingConfig,
    load_config,
    load_onboarding_config,
)
from aks_fleet_efficiency.cost import CostImport
from aks_fleet_efficiency.history import HistoryRun, HistoryStore
from aks_fleet_efficiency.live_collection import builtin_readers, load_collection_plan
from aks_fleet_efficiency.models import (
    FleetSnapshot,
    MetricEntity,
    PrometheusMetricsSnapshot,
    SourceCapabilityReport,
)
from aks_fleet_efficiency.operator import (
    GUARDED_NOTICE,
    build_operator_catalog,
    configure_profile,
    grafana_dashboard,
    preview_execution,
    render_operator_catalog,
)
from aks_fleet_efficiency.readiness import evaluate_readiness
from aks_fleet_efficiency.reporting.markdown import (
    render_assessment_markdown,
    render_markdown,
    render_readiness_markdown,
)
from aks_fleet_efficiency.rules.engine import analyze

app = typer.Typer(no_args_is_help=True, help="Analyze an AKS fleet snapshot.")
catalog_app = typer.Typer(
    no_args_is_help=True, help="Inspect or export offline recommendation packs."
)
app.add_typer(catalog_app, name="catalog")
history_app = typer.Typer(no_args_is_help=True, help="Import and compare local assessment history.")
app.add_typer(history_app, name="history")


@history_app.command("import")
def history_import_command(
    artifacts: Annotated[Path, typer.Option("--artifacts", exists=True, file_okay=False)],
    store: Annotated[Path, typer.Option("--store")],
    tenant: Annotated[str, typer.Option("--tenant")],
) -> None:
    """Verify and retain an immutable local assessment; never collect sources."""
    try:
        run = HistoryStore(store, tenant_id=tenant).import_assessment(artifacts)
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "History import failed. Check tenant, artifact integrity, replay compatibility, "
            "store limits and filesystem permissions. Input is not echoed."
        ) from error
    typer.echo(run.model_dump_json(indent=2))


@history_app.command("list")
def history_list_command(
    store: Annotated[Path, typer.Option("--store")],
    tenant: Annotated[str, typer.Option("--tenant")],
) -> None:
    """List verified local runs without creating a store."""
    try:
        runs = HistoryStore(store, tenant_id=tenant).list_runs()
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "History cannot be read. Check tenant, schema, integrity and store limits. "
            "Input is not echoed."
        ) from error
    typer.echo(RootModel[list[HistoryRun]](runs).model_dump_json(indent=2))


@history_app.command("compare")
def history_compare_command(
    store: Annotated[Path, typer.Option("--store")],
    tenant: Annotated[str, typer.Option("--tenant")],
    previous: Annotated[str, typer.Option("--previous")],
    current: Annotated[str, typer.Option("--current")],
) -> None:
    """Compare explicit ordered runs; disappearance is never resolution."""
    try:
        trend = HistoryStore(store, tenant_id=tenant).compare(previous, current)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "History comparison failed. Check tenant, integrity, exact run IDs and time order. "
            "Input is not echoed."
        ) from error
    typer.echo(trend.model_dump_json(indent=2))


def _select_analysis(
    config: AdvisorConfig, mode: AssessmentMode | None, packs: list[str] | None
) -> AdvisorConfig:
    payload = config.model_dump()
    if mode is not None:
        payload["mode"] = mode
    if packs is not None:
        payload["packs"] = packs
    return AdvisorConfig.model_validate(payload)


def _check_destination(path: Path | None) -> None:
    if path is not None and (path.exists() or path.is_symlink() or not path.parent.is_dir()):
        typer.echo("Output must be new and its parent directory must exist.", err=True)
        raise typer.Exit(code=1)


@app.callback()
def main() -> None:
    """AKS Fleet Efficiency Advisor command line interface."""


def _evaluation_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("evaluation time is timezone-naive")
    except ValueError as error:
        raise typer.BadParameter(
            "Use a timezone-aware ISO8601 datetime, for example 2026-10-29T12:00:00Z.",
            param_hint="--as-of",
        ) from error
    return parsed


@app.command("analyze")
def analyze_command(
    snapshot: Annotated[Path, typer.Option("--snapshot", exists=True, readable=True)],
    config: Annotated[Path | None, typer.Option("--config", exists=True, readable=True)] = None,
    output_format: Annotated[Literal["json", "markdown"], typer.Option("--format")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output")] = None,
    as_of: Annotated[
        str | None,
        typer.Option("--as-of", help="Timezone-aware ISO8601 evaluation time for replay."),
    ] = None,
    mode: Annotated[AssessmentMode | None, typer.Option("--mode")] = None,
    packs: Annotated[list[str] | None, typer.Option("--pack")] = None,
) -> None:
    """Analyze a normalized, read-only fleet snapshot."""
    evaluation_time = _evaluation_time(as_of)
    _check_destination(output)
    try:
        fleet_snapshot = read_model(snapshot, FleetSnapshot)
        analysis = _select_analysis(load_config(config), mode, packs)
        report = analyze(fleet_snapshot, analysis, as_of=evaluation_time)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid snapshot or analysis configuration; check schema and policy. "
            "Sensitive input is not echoed."
        ) from error
    rendered = (
        report.model_dump_json(indent=2) if output_format == "json" else render_markdown(report)
    )
    if output:
        try:
            write_exclusive(output, rendered)
        except OSError as error:
            typer.echo(
                "Could not create analysis output; existing files are not overwritten.", err=True
            )
            raise typer.Exit(code=1) from error
    else:
        typer.echo(rendered)


@app.command("assess")
def assess_command(
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    fragments: Annotated[
        Path | None, typer.Option("--fragments", exists=True, readable=True)
    ] = None,
    plan: Annotated[Path | None, typer.Option("--plan", exists=True, readable=True)] = None,
    allow_live: Annotated[bool, typer.Option("--allow-live")] = False,
    artifacts: Annotated[Path | None, typer.Option("--artifacts")] = None,
    output_format: Annotated[Literal["json", "markdown"], typer.Option("--format")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    mode: Annotated[AssessmentMode | None, typer.Option("--mode")] = None,
    packs: Annotated[list[str] | None, typer.Option("--pack")] = None,
) -> None:
    """Assess saved fragments, or explicitly collect approved sources then assess."""
    evaluation_time = _evaluation_time(as_of)
    if (fragments is None) == (plan is None):
        raise typer.BadParameter("Provide exactly one of --fragments or --plan.")
    if plan is not None and not allow_live:
        raise typer.BadParameter("--plan requires explicit --allow-live.")
    if fragments is not None and allow_live:
        raise typer.BadParameter("--allow-live is not valid for offline --fragments.")
    _check_destination(output)
    _check_destination(artifacts)
    try:
        profile = load_onboarding_config(config)
        profile.analysis = _select_analysis(profile.analysis, mode, packs)
        if fragments is not None:
            bundle = read_model(fragments, AssessmentFragments)
        else:
            assert plan is not None
            request = load_collection_plan(plan)
            with builtin_readers(profile, request, allow_live=allow_live) as readers:
                bundle = collect_fragments(profile, request, readers, allow_live=allow_live)
        result = assess_fragments(bundle, profile, as_of=evaluation_time)
    except (OSError, ValueError, RuntimeError, PermissionError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Assessment input or collection prerequisites are invalid. Check the unified schema, "
            "exact scope, sanitized exports/fingerprint, metric source/identity mapping, optional "
            "dependencies and supported authentication. No input or credentials are echoed.",
            param_hint="--fragments/--config",
        ) from error
    rendered = (
        result.model_dump_json(indent=2)
        if output_format == "json"
        else render_assessment_markdown(result)
    )
    try:
        if artifacts is not None:
            write_assessment_artifacts(artifacts, bundle, result, profile.analysis)
        if output is not None:
            write_exclusive(output, rendered)
        else:
            typer.echo(rendered)
    except OSError as error:
        typer.echo(
            "Could not create assessment artifacts; existing files/directories "
            "are not overwritten.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    raise typer.Exit(code=0 if result.status == "complete" else 3)


@catalog_app.command("list")
def catalog_list_command() -> None:
    """List the complete supported recommendation-pack catalog."""
    try:
        catalog = load_catalog()
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter("Installed catalog assets are invalid or incomplete.") from error
    for pack in sorted(catalog.manifests.values(), key=lambda item: item.id):
        typer.echo(f"{pack.id} v{pack.version}: {pack.title} (baseline, guarded)")
    typer.echo(
        f"{len(catalog.inventory)} inventoried rules; {len(catalog.manifests)} implemented packs."
    )


@catalog_app.command("show")
def catalog_show_command(pack_id: str) -> None:
    """Inspect a manifest and its query templates without accessing endpoints."""
    try:
        catalog = load_catalog()
        pack = catalog.provenance(pack_id)
        manifest = catalog.pack(pack_id)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter("Unknown pack or invalid installed catalog assets.") from error
    typer.echo(
        json.dumps(
            {
                "manifest": manifest.model_dump(mode="json"),
                "provenance": pack.model_dump(mode="json"),
            },
            indent=2,
        )
    )


@catalog_app.command("export")
def catalog_export_command(
    pack_id: str,
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    source: Annotated[str, typer.Option("--source")],
    entities: Annotated[Path, typer.Option("--entities", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output")],
    mode: Annotated[AssessmentMode, typer.Option("--mode")] = "baseline",
    step_seconds: Annotated[int, typer.Option("--step-seconds", min=1, max=300)] = 300,
    grafana: Annotated[bool, typer.Option("--grafana")] = False,
) -> None:
    """Export valid scope-bound PromQL and a manifest; perform no endpoint requests."""
    _check_destination(output)
    try:
        profile = load_onboarding_config(config)
        catalog = load_catalog()
        if catalog.pack(pack_id).evidence_kind == "inventory":
            raise typer.BadParameter(
                "This pack is metadata-only; use catalog show to inspect its scoped evidence. "
                "It has no PromQL queries or metric endpoint requirement."
            )
        targets = read_model(entities, RootModel[list[MetricEntity]]).root
        queries = render_pack_queries(
            catalog, pack_id, profile, source, targets, mode, step_seconds=step_seconds
        )
        provenance = catalog.provenance(pack_id, profile.analysis.pack_parameters.get(pack_id))
        if (
            profile.analysis.pack_locks
            and profile.analysis.pack_locks.get(pack_id) != provenance.digest
        ):
            raise ValueError("Export pack lock differs from installed assets")
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid pack, source, entity scope or profile. Use a declared source and "
            "explicit direct/replica identities; sensitive input is not echoed."
        ) from error
    try:
        output.mkdir(exist_ok=False)
        for query in queries:
            write_exclusive(
                output / f"{query.metric}-{query.entity_digest}.promql", query.expression
            )
        source_profile = catalog.source(
            next(item.catalog_profile for item in profile.metric_sources if item.name == source)
        )
        export = QueryExportManifest(
            mode=mode, pack=provenance, queries=queries, source_profile=source_profile
        )
        write_exclusive(output / "manifest.json", export.model_dump_json(indent=2))
        if grafana:
            write_exclusive(
                output / "dashboard.json", json.dumps(grafana_dashboard(queries), indent=2)
            )
    except OSError as error:
        typer.echo("Could not create query export; existing paths are not overwritten.", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Exported {len(queries)} scope-bound queries. No endpoints were contacted.")


@catalog_app.command("guide")
def catalog_guide_command(
    output_format: Annotated[Literal["json", "markdown"], typer.Option("--format")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Generate operator cards, glossary and synthetic configuration examples offline."""
    _check_destination(output)
    try:
        catalog = build_operator_catalog(load_catalog())
        rendered = (
            catalog.model_dump_json(indent=2)
            if output_format == "json"
            else render_operator_catalog(catalog)
        )
        if output is not None:
            write_exclusive(output, rendered)
        else:
            typer.echo(rendered)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Catalog generation failed; check installed assets/output."
        ) from error


def _guided_profile(config: Path | None) -> OnboardingConfig:
    payload = load_onboarding_config(config).model_dump(mode="json") if config else {}
    scope = payload.get("scope", {})
    payload["scope"] = {
        "tenant_id": typer.prompt("Approved tenant UUID", default=scope.get("tenant_id", "")),
        "subscription_ids": [
            item.strip()
            for item in typer.prompt(
                "Approved subscription UUIDs (comma-separated)",
                default=",".join(scope.get("subscription_ids", [])),
            ).split(",")
        ],
    }
    clusters = payload.get("clusters", [])
    cluster_ids = [
        item.strip()
        for item in typer.prompt(
            "Exact approved AKS resource IDs (comma-separated)",
            default=",".join(item["resource_id"] for item in clusters),
        ).split(",")
    ]
    sources = payload.get("metric_sources", [])
    if not sources and typer.confirm(
        "Declare a metric source (not needed for inventory-only packs)?"
    ):
        sources = [
            {
                "name": typer.prompt("Local source name", default="approved"),
                "type": typer.prompt("Transport", default="prometheus"),
                "endpoint": "https://metrics.example.invalid",
                "authentication": "anonymous",
                "catalog_profile": "cadvisor-ksm",
                "label_mapping": {
                    "cluster_resource_id": "azure_resource_id",
                    "namespace": "namespace",
                    "pod": "pod",
                    "workload_kind": "workload_kind",
                    "workload": "workload",
                    "container": "container",
                },
            }
        ]
    typer.echo(
        "cadvisor-ksm is name-only baseline telemetry; identity-enriched requires retained UIDs. "
        "Label mappings are explicit declarations, not discovered or certified."
    )
    for source in sources:
        source["endpoint"] = typer.prompt(
            f"HTTPS endpoint for {source['name']} (no credentials)", default=source["endpoint"]
        )
        source["catalog_profile"] = typer.prompt(
            "Source semantics (cadvisor-ksm/identity-enriched)",
            default=source.get("catalog_profile", "identity-enriched"),
        )
        source["authentication"] = typer.prompt(
            "Authentication (anonymous/default-azure-credential/bearer-environment)",
            default=(
                "default-azure-credential"
                if source["type"] == "azure-managed-prometheus"
                else source["authentication"]
            ),
        )
        if source["authentication"] == "bearer-environment":
            source["token_environment_variable"] = typer.prompt(
                "Credential variable NAME only (CLI never reads its value)",
                default=source.get("token_environment_variable") or "PROMETHEUS_TOKEN",
            )
        else:
            source["token_environment_variable"] = None
        for label, mapped in source["label_mapping"].items():
            source["label_mapping"][label] = typer.prompt(
                f"Source label for {label}", default=mapped
            )
    payload["metric_sources"] = sources
    payload["clusters"] = []
    for index, resource_id in enumerate(cluster_ids, start=1):
        previous: dict[str, Any] = next(
            (item for item in clusters if item["resource_id"] == resource_id), {}
        )
        source_name = typer.prompt(
            f"Metric source for target {index} (blank for metadata-only)",
            default=previous.get("metric_source") or (sources[0]["name"] if sources else ""),
        )
        payload["clusters"].append(
            {
                **previous,
                "resource_id": resource_id,
                "metric_source": source_name or None,
            }
        )
    payload["report_directory"] = typer.prompt(
        "Local artifact directory", default=payload.get("report_directory", "reports")
    )
    return OnboardingConfig.model_validate(payload)


@app.command("configure")
def configure_command(
    output: Annotated[Path, typer.Option("--output")],
    config: Annotated[Path | None, typer.Option("--config", exists=True, readable=True)] = None,
    interactive: Annotated[bool, typer.Option("--interactive/--no-interactive")] = True,
    mode: Annotated[AssessmentMode | None, typer.Option("--mode")] = None,
    packs: Annotated[list[str] | None, typer.Option("--pack")] = None,
    review_ratio: Annotated[list[str] | None, typer.Option("--review-ratio")] = None,
) -> None:
    """Guide local scope/source/pack setup; never request credentials or owner approval."""
    _check_destination(output)
    typer.echo(GUARDED_NOTICE)
    try:
        if not interactive and config is None:
            raise ValueError("Non-interactive configuration requires --config")
        if interactive:
            profile = _guided_profile(config)
        else:
            assert config is not None
            profile = load_onboarding_config(config)
        catalog = build_operator_catalog(load_catalog())
        selected = packs or profile.analysis.packs or [card.manifest.id for card in catalog.cards]
        selected_mode = mode or profile.analysis.mode
        if interactive:
            for card in catalog.cards:
                typer.echo(f"{card.manifest.id}: {card.manifest.title}")
            selected = [
                value.strip()
                for value in typer.prompt(
                    "Pack IDs (comma-separated)", default=",".join(selected)
                ).split(",")
            ]
            selected_mode = typer.prompt("Mode (baseline/guarded)", default=selected_mode)
        ratios = {}
        for item in review_ratio or []:
            name, value = item.split("=", 1)
            if name in ratios:
                raise ValueError("Duplicate review parameter")
            ratios[name] = float(value)
        for card in catalog.cards:
            if card.manifest.id not in selected:
                continue
            for name, guidance in card.parameter_guidance.items():
                default = profile.analysis.pack_parameters.get(
                    card.manifest.id, card.manifest.parameters
                ).review_ratio
                typer.echo(
                    f"{card.manifest.id} {name}: default {default} {guidance.unit}; "
                    f"{guidance.bounds}. {guidance.implication}"
                )
                if interactive and card.manifest.id not in ratios:
                    ratios[card.manifest.id] = float(
                        typer.prompt(f"{card.manifest.id} review ratio", default=str(default))
                    )
        result = configure_profile(profile, selected, selected_mode, ratios)
        write_exclusive(output, yaml.safe_dump(result.model_dump(mode="json"), sort_keys=False))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid configuration: use exact approved scope, declared HTTPS source semantics, "
            "known packs/mode and bounded PACK=NUMBER parameters. No input is echoed."
        ) from error
    typer.echo("Saved locked local configuration. No endpoint or credential was accessed.")


@app.command("preview")
def preview_command(
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    plan: Annotated[Path, typer.Option("--plan", exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Preview CLI operations, exact query expressions and budgets without constructing clients."""
    from datetime import UTC

    _check_destination(output)
    try:
        result = preview_execution(
            load_onboarding_config(config),
            load_collection_plan(plan, resolve_exports=False),
            as_of=_evaluation_time(as_of) or datetime.now(UTC),
        )
        if output is not None:
            write_exclusive(output, result.model_dump_json(indent=2))
        else:
            typer.echo(result.model_dump_json(indent=2))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid preview scope, source, window, policy binding or query/evaluation budget. "
            "No clients were constructed and no endpoints were contacted."
        ) from error


@catalog_app.command("capabilities")
def capabilities_command(
    pack_id: str,
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    metrics: Annotated[Path | None, typer.Option("--metrics", exists=True, readable=True)] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Inspect declared profiles or imported evidence; never probe endpoints."""
    from datetime import UTC

    evaluated_at = _evaluation_time(as_of) or datetime.now(UTC)
    try:
        profile = load_onboarding_config(config)
        if load_catalog().pack(pack_id).evidence_kind == "inventory":
            raise typer.BadParameter(
                "This pack uses current metadata, not Prometheus capabilities. "
                "Use catalog show/assess."
            )
        evidence = [read_model(metrics, PrometheusMetricsSnapshot)] if metrics is not None else []
        report = SourceCapabilityReport(
            generated_at=evaluated_at,
            capabilities=evaluate_source_capabilities(
                profile, evidence, pack_id=pack_id, as_of=evaluated_at
            ),
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid capability input, source profile or evidence scope; "
            "sensitive input is not echoed."
        ) from error
    typer.echo(report.model_dump_json(indent=2))


@app.command("collect")
def collect_command(
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    plan: Annotated[Path, typer.Option("--plan", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output")],
    allow_live: Annotated[bool, typer.Option("--allow-live")] = False,
) -> None:
    """Collect approved read-only sources into a replayable unified fragment bundle."""
    if not allow_live:
        raise typer.BadParameter(
            "Explicit --allow-live is required; configured endpoints are not consent."
        )
    _check_destination(output)
    try:
        profile = load_onboarding_config(config)
        request = load_collection_plan(plan)
        with builtin_readers(profile, request, allow_live=allow_live) as readers:
            bundle = collect_fragments(profile, request, readers, allow_live=allow_live)
    except (OSError, ValueError, RuntimeError, PermissionError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Collection prerequisites failed. Check scope, sanitized exports, fingerprints, "
            "authentication and optional dependencies; sensitive input is not echoed."
        ) from error
    try:
        write_exclusive(output, bundle.model_dump_json(indent=2))
    except OSError as error:
        typer.echo(
            "Could not create collection output; existing files are not overwritten.", err=True
        )
        raise typer.Exit(code=1) from error
    receipts = [item.collection for item in bundle.azure]
    receipts.extend(item.collection for item in bundle.kubernetes)
    receipts.extend(item.collection for item in bundle.metrics)
    partial = any(item.status != "complete" for item in receipts)
    raise typer.Exit(code=3 if partial else 0)


@app.command("reconcile-costs")
def reconcile_costs_command(
    costs: Annotated[Path, typer.Option("--costs", exists=True, readable=True)],
    snapshot: Annotated[Path, typer.Option("--snapshot", exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    minimum_allocation_coverage: Annotated[
        str, typer.Option("--minimum-allocation-coverage")
    ] = "0.95",
    maximum_evidence_age_hours: Annotated[
        int, typer.Option("--maximum-evidence-age-hours", min=1, max=8760)
    ] = 24,
) -> None:
    """Reconcile saved amortized costs and reviewed shares, without endpoint access."""
    from datetime import UTC
    from decimal import InvalidOperation

    evaluation_time = _evaluation_time(as_of) or datetime.now(UTC)
    _check_destination(output)
    try:
        result = CostManagementCollector().collect_costs(
            read_model(costs, CostImport),
            read_model(snapshot, FleetSnapshot),
            as_of=evaluation_time,
            minimum_allocation_coverage=Decimal(minimum_allocation_coverage),
            maximum_evidence_age_hours=maximum_evidence_age_hours,
        )
    except (OSError, ValueError, InvalidOperation) as error:
        raise typer.BadParameter(
            "Invalid cost projection, allocation shares, decimal threshold, period or scope. "
            "Check the cost-import schema; sensitive financial input is not echoed."
        ) from error
    try:
        if output is not None:
            write_exclusive(output, result.model_dump_json(indent=2))
        else:
            typer.echo(result.model_dump_json(indent=2))
    except OSError as error:
        typer.echo("Could not create cost output; existing files are not overwritten.", err=True)
        raise typer.Exit(code=1) from error
    raise typer.Exit(code=0 if result.status == "reconciled" else 3)


@app.command("readiness")
def readiness_command(
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    snapshot: Annotated[Path | None, typer.Option("--snapshot", exists=True, readable=True)] = None,
    output_format: Annotated[Literal["json", "markdown"], typer.Option("--format")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Check onboarding and optional snapshot evidence without contacting endpoints."""
    evaluation_time = _evaluation_time(as_of)
    _check_destination(output)
    try:
        profile = load_onboarding_config(config)
        fleet_snapshot = read_model(snapshot, FleetSnapshot) if snapshot is not None else None
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid onboarding profile or snapshot. Check scope, source references, "
            "HTTPS/authentication fields, and schema version; sensitive input is not echoed.",
            param_hint="--config/--snapshot",
        ) from error
    report = evaluate_readiness(profile, snapshot=fleet_snapshot, as_of=evaluation_time)
    rendered = (
        report.model_dump_json(indent=2)
        if output_format == "json"
        else render_readiness_markdown(report)
    )
    if output is not None:
        try:
            write_exclusive(output, rendered)
        except OSError as error:
            typer.echo("Could not write readiness report to the requested file.", err=True)
            raise typer.Exit(code=1) from error
    else:
        typer.echo(rendered)
    raise typer.Exit(code={"ready": 0, "unknown": 3, "blocked": 4}[report.status])


if __name__ == "__main__":
    app()
