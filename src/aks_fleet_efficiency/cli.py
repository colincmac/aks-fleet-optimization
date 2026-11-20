from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import typer
import yaml
from pydantic import RootModel, TypeAdapter

from aks_fleet_efficiency.advisory import (
    MAXIMUM_AI_PACKAGE_BYTES,
    MAXIMUM_PROPOSAL_BYTES,
    AIEvidencePackage,
    AIExperimentIntent,
    AIReviewIntent,
)
from aks_fleet_efficiency.ai_export import (
    export_ai_evidence,
    export_ai_measurements,
    validate_ai_checklist,
    validate_ai_experiment,
    validate_ai_explanation,
)
from aks_fleet_efficiency.artifacts import (
    MAXIMUM_INPUT_BYTES,
    read_model,
    write_assessment_artifacts,
    write_exclusive,
)
from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
from aks_fleet_efficiency.assessment_batch import (
    BatchInputError,
    BatchStatusError,
    FeedLockedError,
    assess_batch,
    stage_assessment_input,
)
from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.catalog import digest_json, load_catalog, render_query_bundle
from aks_fleet_efficiency.catalog.models import (
    AssessmentMode,
    QueryBundleExportManifest,
    QueryExportManifest,
)
from aks_fleet_efficiency.collection import collect_fragments
from aks_fleet_efficiency.collectors.cost_management import CostManagementCollector
from aks_fleet_efficiency.collectors.metric_queries import (
    effective_label_mapping,
    render_query,
    required_metric_labels,
)
from aks_fleet_efficiency.collectors.prometheus import PrometheusHttpReader
from aks_fleet_efficiency.config import (
    AdvisorConfig,
    OnboardingConfig,
    load_config,
    load_onboarding_config,
)
from aks_fleet_efficiency.cost import (
    AllocationObservation,
    CostImport,
    CostPeriod,
    qualify_allocation_observation,
)
from aks_fleet_efficiency.cost_sources import (
    order_saved_cost_reviews,
    project_allocation,
    project_ledger,
)
from aks_fleet_efficiency.cost_sources.focus_export import convert_focus_export
from aks_fleet_efficiency.daemonsets import review_daemonset_membership
from aks_fleet_efficiency.experiments import (
    ExperimentHandoffRequest,
    ExperimentOutcomeRequest,
    prepare_experiment_handoff,
    record_experiment_outcome,
    write_experiment_handoff_bundle,
    write_experiment_outcome_bundle,
)
from aks_fleet_efficiency.fleet import FleetAssessment, aggregate_fleet
from aks_fleet_efficiency.fleet_context import FleetContext
from aks_fleet_efficiency.history import (
    HistoryRun,
    HistoryStore,
    _read_text,
    _read_verified_archive,
    compare_assessment_artifacts,
    project_fleet_drift_matrix,
    read_assessment_artifacts,
    summarize_fleet_artifacts,
)
from aks_fleet_efficiency.live_collection import builtin_readers, load_collection_plan
from aks_fleet_efficiency.models import (
    CollectorResult,
    FleetSnapshot,
    MetricEntity,
    PrometheusMetricsSnapshot,
    SourceCapabilityReport,
    StartupHistoryEvidence,
)
from aks_fleet_efficiency.nap_policy import NapPolicyInput, review_nap_policy
from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, review_node_history
from aks_fleet_efficiency.operator import (
    GUARDED_NOTICE,
    build_operator_catalog,
    configure_profile,
    grafana_dashboard,
    preview_execution,
    render_operator_catalog,
    retained_query_quality,
)
from aks_fleet_efficiency.readiness import evaluate_readiness
from aks_fleet_efficiency.reporting.grafana import fleet_grafana_dashboard
from aks_fleet_efficiency.reporting.markdown import (
    render_assessment_markdown,
    render_fleet_markdown,
    render_markdown,
    render_readiness_markdown,
)
from aks_fleet_efficiency.rules.engine import analyze
from aks_fleet_efficiency.scheduling import (
    calculate_scheduling_constraints,
    review_scheduling_placement,
)
from aks_fleet_efficiency.source_acceptance import (
    PrometheusSourceAcceptance,
    PrometheusSourceAcceptancePlan,
    collect_prometheus_source_acceptance,
)
from aks_fleet_efficiency.startup import review_startup_history
from aks_fleet_efficiency.storage import project_storage_context
from aks_fleet_efficiency.value_outcomes import (
    ExperimentValueOutcomeRequest,
    validate_experiment_value_outcome,
    write_experiment_value_outcome_bundle,
)

app = typer.Typer(no_args_is_help=True, help="Analyze an AKS fleet snapshot.")
catalog_app = typer.Typer(
    no_args_is_help=True, help="Inspect or export offline recommendation packs."
)
app.add_typer(catalog_app, name="catalog")
history_app = typer.Typer(no_args_is_help=True, help="Import and compare local assessment history.")
app.add_typer(history_app, name="history")
fleet_app = typer.Typer(no_args_is_help=True, help="Aggregate explicit offline assessments.")
app.add_typer(fleet_app, name="fleet")
ai_app = typer.Typer(no_args_is_help=True, help="Export and check bounded AI summaries offline.")
app.add_typer(ai_app, name="ai")


@ai_app.command("export")
def ai_export_command(
    assessments: Annotated[list[Path], typer.Option("--assessment")],
    tenant: Annotated[str, typer.Option("--tenant")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    allow_ai_export: Annotated[bool, typer.Option("--allow-ai-export")] = False,
    allow_ai_measurements: Annotated[bool, typer.Option("--allow-ai-measurements")] = False,
    ttl_seconds: Annotated[int, typer.Option("--ttl-seconds", min=60, max=3600)] = 3600,
) -> None:
    """Export pseudonymous finding summaries; never invoke AI or grant action authority."""
    if not allow_ai_export:
        raise typer.BadParameter(
            "AI summary export requires explicit --allow-ai-export data-release consent."
        )
    _check_destination(output)
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        if any(path.name != "assessment.json" for path in assessments):
            raise ValueError("AI export requires original assessment files")
        exporter = export_ai_measurements if allow_ai_measurements else export_ai_evidence
        package = exporter(
            [path.parent for path in assessments],
            tenant_id=tenant,
            as_of=evaluated_at,
            ttl_seconds=ttl_seconds,
        )
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "AI export failed. Check original artifact bundles, tenant, fingerprint, replay, "
            "clocks and budgets. Input values are not echoed."
        ) from error
    try:
        write_exclusive(output, package.model_dump_json(indent=2))
    except OSError as error:
        typer.echo("Could not create AI package; existing files are not overwritten.", err=True)
        raise typer.Exit(code=1) from error
    label = "measurements and summaries" if allow_ai_measurements else "summaries"
    typer.echo(f"Saved bounded pseudonymous {label}. No model or endpoint was called.")


def _validate_ai_draft_files(
    assessments: list[Path],
    tenant: str,
    as_of: str,
    package_path: Path,
    draft_path: Path,
    intent_path: Path | None = None,
    *,
    experiment: bool = False,
) -> None:
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        if any(path.name != "assessment.json" for path in assessments):
            raise ValueError("AI validation requires original assessment files")
        package = AIEvidencePackage.model_validate_json(
            _read_text(package_path, MAXIMUM_AI_PACKAGE_BYTES)
        )
        directories = [path.parent for path in assessments]
        payload = _read_text(draft_path, MAXIMUM_PROPOSAL_BYTES)
        if intent_path is None:
            result = validate_ai_explanation(
                directories,
                tenant_id=tenant,
                package=package,
                payload=payload,
                as_of=evaluated_at,
            ).model_dump_json(indent=2)
        elif experiment:
            experiment_intent = AIExperimentIntent.model_validate_json(
                _read_text(intent_path, 4096)
            )
            result = validate_ai_experiment(
                directories,
                tenant_id=tenant,
                package=package,
                intent=experiment_intent,
                payload=payload,
                as_of=evaluated_at,
            ).model_dump_json(indent=2)
        else:
            intent = AIReviewIntent.model_validate_json(_read_text(intent_path, 4096))
            result = validate_ai_checklist(
                directories,
                tenant_id=tenant,
                package=package,
                intent=intent,
                payload=payload,
                as_of=evaluated_at,
            ).model_dump_json(indent=2)
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "AI draft rejected. Check original artifacts, tenant, package/intent binding, "
            "citations, copied facts, steps, clocks and budgets. Input values are not echoed."
        ) from error
    typer.echo(result)


@ai_app.command("validate-explanation")
def ai_validate_explanation_command(
    assessments: Annotated[list[Path], typer.Option("--assessment")],
    tenant: Annotated[str, typer.Option("--tenant")],
    as_of: Annotated[str, typer.Option("--as-of")],
    package_path: Annotated[Path, typer.Option("--package")],
    draft_path: Annotated[Path, typer.Option("--draft")],
) -> None:
    """Verify copied facts and citations against originals; interpretation stays unverified."""
    _validate_ai_draft_files(assessments, tenant, as_of, package_path, draft_path)


@ai_app.command("validate-checklist")
def ai_validate_checklist_command(
    assessments: Annotated[list[Path], typer.Option("--assessment")],
    tenant: Annotated[str, typer.Option("--tenant")],
    as_of: Annotated[str, typer.Option("--as-of")],
    package_path: Annotated[Path, typer.Option("--package")],
    intent_path: Annotated[Path, typer.Option("--intent")],
    draft_path: Annotated[Path, typer.Option("--draft")],
) -> None:
    """Validate a closed cited checklist; never approve or execute its interpretation."""
    _validate_ai_draft_files(assessments, tenant, as_of, package_path, draft_path, intent_path)


@ai_app.command("validate-experiment")
def ai_validate_experiment_command(
    assessments: Annotated[list[Path], typer.Option("--assessment")],
    tenant: Annotated[str, typer.Option("--tenant")],
    as_of: Annotated[str, typer.Option("--as-of")],
    package_path: Annotated[Path, typer.Option("--package")],
    intent_path: Annotated[Path, typer.Option("--intent")],
    draft_path: Annotated[Path, typer.Option("--draft")],
) -> None:
    """Validate a cited non-executable experiment; never approve or perform a change."""
    _validate_ai_draft_files(
        assessments, tenant, as_of, package_path, draft_path, intent_path, experiment=True
    )


@app.command("prepare-experiment")
def prepare_experiment_command(
    assessment: Annotated[Path, typer.Option("--assessment", exists=True, readable=True)],
    tenant: Annotated[str, typer.Option("--tenant")],
    request_path: Annotated[Path, typer.Option("--request", exists=True, readable=True)],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Prepare a portable review record; never approve, execute, or publish a change."""
    _check_destination(output)
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        if assessment.name != "assessment.json":
            raise ValueError("experiment handoff requires the original assessment file")
        request = read_model(request_path, ExperimentHandoffRequest)
        handoff = prepare_experiment_handoff(
            assessment.parent,
            tenant_id=tenant,
            request=request,
            as_of=evaluated_at,
        )
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "Experiment handoff failed. Check the original artifact bundle, tenant, finding, "
            "single dimension, owner criteria, staged checks, rollback, clocks and budgets. "
            "Sensitive input is not echoed."
        ) from error
    try:
        write_experiment_handoff_bundle(output, handoff)
    except (OSError, ValueError) as error:
        typer.echo(
            "Could not create experiment handoff; existing files are not overwritten.", err=True
        )
        raise typer.Exit(code=1) from error
    raise typer.Exit(code=0 if handoff.state == "prepared" else 3)


@app.command("record-experiment-outcome")
def record_experiment_outcome_command(
    experiment: Annotated[Path, typer.Option("--experiment", exists=True, readable=True)],
    request_path: Annotated[Path, typer.Option("--request", exists=True, readable=True)],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Record an operator-declared outcome; never infer execution or financial value."""
    _check_destination(output)
    recorded_at = _evaluation_time(as_of)
    assert recorded_at is not None
    try:
        request = read_model(request_path, ExperimentOutcomeRequest)
        outcome = record_experiment_outcome(experiment, request=request, recorded_at=recorded_at)
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "Experiment outcome rejected. Check the original handoff bundle, declared outcome, "
            "execution evidence, before/after references, clocks and budgets. Sensitive input "
            "is not echoed."
        ) from error
    try:
        write_experiment_outcome_bundle(output, outcome)
    except (OSError, ValueError) as error:
        typer.echo(
            "Could not create experiment outcome; existing files are not overwritten.", err=True
        )
        raise typer.Exit(code=1) from error


@app.command("validate-value-outcome")
def validate_value_outcome_command(
    experiment: Annotated[Path, typer.Option("--experiment", exists=True, readable=True)],
    outcome: Annotated[Path, typer.Option("--outcome", exists=True, readable=True)],
    request_path: Annotated[Path, typer.Option("--request", exists=True, readable=True)],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Validate separate engineering/value layers; never infer or combine savings."""
    _check_destination(output)
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        request = read_model(request_path, ExperimentValueOutcomeRequest)
        value = validate_experiment_value_outcome(
            experiment,
            outcome,
            request=request,
            evaluated_at=evaluated_at,
        )
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "Experiment value outcome rejected. Check exact handoff/outcome bundles, "
            "before/after bindings, engineering and capacity evidence, financial qualification, "
            "clocks and budgets. Sensitive input is not echoed."
        ) from error
    try:
        write_experiment_value_outcome_bundle(output, value)
    except (OSError, ValueError) as error:
        typer.echo(
            "Could not create experiment value output; existing files are not overwritten.",
            err=True,
        )
        raise typer.Exit(code=1) from error


def _review_native_infrastructure(
    *,
    kind: Literal["storage", "daemonsets"],
    fragments_path: Path,
    native_path: Path,
    tenant: str,
    cluster: str,
    as_of: str,
    output: Path,
    maximum_source_age_seconds: int,
) -> None:
    _check_destination(output)
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        original_text = _read_text(fragments_path, MAXIMUM_INPUT_BYTES)
        native_text = _read_text(
            native_path, MAXIMUM_INPUT_BYTES - len(original_text.encode("utf-8"))
        )
        fragments = AssessmentFragments.model_validate_json(original_text)
        selected = [
            item
            for item in fragments.kubernetes
            if item.tenant_id == str(UUID(tenant)) and item.cluster_resource_id == cluster
        ]
        if len(selected) != 1:
            raise ValueError("native review requires one exact original metadata scope")
        native = json.loads(native_text)
        expected = {"objects", "receipts"} if kind == "storage" else {"daemonsets", "nodes"}
        if not isinstance(native, dict) or set(native) != expected:
            raise ValueError("native review requires closed input fields")
        metadata = selected[0]
        if kind == "storage":
            result = project_storage_context(
                metadata,
                objects=TypeAdapter(list[dict[str, Any]]).validate_python(native["objects"]),
                receipts=TypeAdapter(dict[str, CollectorResult]).validate_python(
                    native["receipts"]
                ),
                as_of=evaluated_at,
                maximum_source_age_seconds=maximum_source_age_seconds,
            ).model_dump_json(indent=2)
        else:
            result = review_daemonset_membership(
                metadata,
                daemonsets=TypeAdapter(list[dict[str, Any]]).validate_python(native["daemonsets"]),
                nodes=TypeAdapter(list[dict[str, Any]]).validate_python(native["nodes"]),
                as_of=evaluated_at,
                maximum_source_age_seconds=maximum_source_age_seconds,
            ).model_dump_json(indent=2)
        if len(result.encode("utf-8")) > MAXIMUM_INPUT_BYTES:
            raise ValueError("native review exceeds its formatted output budget")
        write_exclusive(output, result)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Native review failed. Check exact original scope, allowed fields, receipts, "
            "clocks and budgets. Input values are not echoed."
        ) from error
    typer.echo("Saved supplied-native review; admission and full feasibility remain unverified.")


@app.command("review-storage")
def review_storage_command(
    fragments_path: Annotated[Path, typer.Option("--fragments")],
    native_path: Annotated[Path, typer.Option("--native-storage")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Project approved saved PVC/PV/CSI facts without collecting sources or declaring fit."""
    _review_native_infrastructure(
        kind="storage",
        fragments_path=fragments_path,
        native_path=native_path,
        tenant=tenant,
        cluster=cluster,
        as_of=as_of,
        output=output,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )


@app.command("review-daemonsets")
def review_daemonsets_command(
    fragments_path: Annotated[Path, typer.Option("--fragments")],
    native_path: Annotated[Path, typer.Option("--native-objects")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Model saved DaemonSet controller Node selection; never certify fit or reconciliation."""
    _review_native_infrastructure(
        kind="daemonsets",
        fragments_path=fragments_path,
        native_path=native_path,
        tenant=tenant,
        cluster=cluster,
        as_of=as_of,
        output=output,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )


@app.command("review-nap-policy")
def review_nap_policy_command(
    policy_path: Annotated[Path, typer.Option("--policy")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Review the selected supplied NAP policy reference, never actual disruption feasibility."""
    _check_destination(output)
    clock = _evaluation_time(as_of)
    assert clock is not None
    try:
        evidence = NapPolicyInput.model_validate_json(_read_text(policy_path, MAXIMUM_INPUT_BYTES))
        if str(evidence.tenant_id) != str(UUID(tenant)) or evidence.cluster_resource_id != cluster:
            raise ValueError("NAP policy requires exact scope")
        result = review_nap_policy(
            evidence,
            as_of=clock,
            maximum_source_age_seconds=maximum_source_age_seconds,
        )
        payload = result.model_dump_json(indent=2)
        if len(payload.encode("utf-8")) > MAXIMUM_INPUT_BYTES:
            raise ValueError("NAP policy exceeds its output budget")
        write_exclusive(output, payload)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "NAP policy review failed. Check scope, reference, clocks, allowed fields "
            "and budgets. Input values are not echoed."
        ) from error
    typer.echo(
        "Saved supplied-policy calculation; deployed controller admission remains unverified."
    )


@app.command("review-retained-capacity")
def review_retained_capacity_command(
    assessment_path: Annotated[Path, typer.Option("--assessment", exists=True, readable=True)],
    tenant: Annotated[str, typer.Option("--tenant")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Summarize retained capacity evidence from one original assessment without source calls."""
    from aks_fleet_efficiency.retained_capacity import render_retained_capacity_review

    _check_destination(output)
    try:
        if assessment_path.name != "assessment.json":
            raise ValueError("Retained capacity review requires original assessment.json")
        payload = render_retained_capacity_review(assessment_path.parent, tenant_id=UUID(tenant))
        write_exclusive(output, payload)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Retained capacity review failed. Supply the original single-cluster assessment "
            "bundle and exact tenant. Protected input values are not echoed."
        ) from error


@app.command("compare")
def compare_command(
    previous: Annotated[Path, typer.Option("--previous")],
    current: Annotated[Path, typer.Option("--current")],
    tenant: Annotated[str, typer.Option("--tenant")],
) -> None:
    """Compare two verified artifact directories without importing a history store."""
    try:
        trend = compare_assessment_artifacts(previous, current, tenant_id=tenant)
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "Artifact comparison failed. Check tenant, complete artifact bundles, integrity, "
            "replay compatibility, byte limits and time order. Input values are not echoed."
        ) from error
    typer.echo(trend.model_dump_json(indent=2))


@fleet_app.command("trends")
def fleet_trends_command(
    assessments: Annotated[list[Path], typer.Option("--assessment")],
    peer_groups: Annotated[list[str], typer.Option("--peer-group")],
    tenant: Annotated[str, typer.Option("--tenant")],
    output_format: Annotated[
        Literal["json", "matrix", "grafana"], typer.Option("--format")
    ] = "json",
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Compare explicit saved cluster histories without a store or source access."""
    try:
        if len(assessments) != len(peer_groups):
            raise ValueError("one peer group is required per assessment")
        if any(path.name != "assessment.json" for path in assessments):
            raise ValueError("fleet trends require original assessment files")
        inputs = [
            (path.parent, group) for path, group in zip(assessments, peer_groups, strict=True)
        ]
        if (output_format != "json") != (as_of is not None):
            raise ValueError("matrix and Grafana formats require an explicit evaluation clock")
        if as_of is not None:
            evaluated_at = _evaluation_time(as_of)
            assert evaluated_at is not None
            matrix = project_fleet_drift_matrix(inputs, tenant_id=tenant, as_of=evaluated_at)
            output = (
                fleet_grafana_dashboard(matrix)
                if output_format == "grafana"
                else matrix.model_dump_json()
            )
        else:
            output = summarize_fleet_artifacts(inputs, tenant_id=tenant).model_dump_json(indent=2)
    except (OSError, ValueError, RuntimeError) as error:
        raise typer.BadParameter(
            "Fleet trends failed. Check tenant, complete original artifact bundles, replay, "
            "one peer group per assessment, distinct samples, clocks and limits. "
            "Matrix and Grafana formats require --as-of. "
            "Input values are not echoed."
        ) from error
    typer.echo(output)


@fleet_app.command("summarize")
def fleet_summarize_command(
    assessments: Annotated[
        list[Path], typer.Option("--assessment", exists=True, readable=True, dir_okay=False)
    ],
    peer_groups: Annotated[list[str], typer.Option("--peer-group")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output_format: Annotated[Literal["json", "markdown"], typer.Option("--format")] = "json",
    output: Annotated[Path | None, typer.Option("--output")] = None,
    node_history_paths: Annotated[list[Path] | None, typer.Option("--node-history")] = None,
    context_paths: Annotated[list[Path] | None, typer.Option("--context")] = None,
) -> None:
    """Aggregate completed assessment artifacts without collecting sources."""
    generated_at = _evaluation_time(as_of)
    assert generated_at is not None
    if len(assessments) != len(peer_groups):
        raise typer.BadParameter(
            "Provide one --peer-group for each --assessment; input values are not echoed."
        )
    if len(node_history_paths or []) > 1000 or len(context_paths or []) > 1000:
        raise typer.BadParameter("Fleet supplemental input count exceeds the supported budget.")
    _check_destination(output)
    try:
        histories = []
        remaining = MAXIMUM_INPUT_BYTES
        for history_path in node_history_paths or []:
            text = _read_text(history_path, remaining)
            remaining -= len(text.encode("utf-8"))
            histories.append(HistoricalNodeEvidence.model_validate_json(text))
        contexts = []
        for context_path in context_paths or []:
            text = _read_text(context_path, remaining)
            remaining -= len(text.encode("utf-8"))
            contexts.append(FleetContext.model_validate_json(text))
        entries = []
        for path, peer_group in zip(assessments, peer_groups, strict=True):
            if path.name != "assessment.json":
                raise ValueError("fleet aggregation requires the original assessment.json")
            assessment, analysis_config = read_assessment_artifacts(path.parent)
            entries.append(
                FleetAssessment(
                    peer_group=peer_group,
                    assessment=assessment,
                    analysis_config=analysis_config,
                    node_history=[
                        item
                        for item in histories
                        if item.cluster_resource_id
                        in {cluster.resource_id for cluster in assessment.snapshot.clusters}
                    ],
                    external_context=[
                        item
                        for item in contexts
                        if item.cluster_resource_id
                        in {cluster.resource_id for cluster in assessment.snapshot.clusters}
                    ],
                )
            )
        if any(not any(item in entry.node_history for entry in entries) for item in histories):
            raise ValueError("historical input requires an original selected assessment")
        if any(not any(item in entry.external_context for entry in entries) for item in contexts):
            raise ValueError("fleet context requires an original selected assessment")
        report = aggregate_fleet(entries, generated_at=generated_at)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Fleet aggregation failed. Check assessment integrity, tenant and cluster identity, "
            "peer groups and bounded input count. Input values are not echoed."
        ) from error
    rendered = (
        report.model_dump_json(indent=2)
        if output_format == "json"
        else render_fleet_markdown(report)
    )
    if output is None:
        typer.echo(rendered)
        return
    try:
        write_exclusive(output, rendered)
    except OSError as error:
        typer.echo("Could not create fleet output; existing files are not overwritten.", err=True)
        raise typer.Exit(code=1) from error


@fleet_app.command("review-node-history")
def fleet_review_node_history_command(
    history_path: Annotated[Path, typer.Option("--history")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Review approved saved Node history; no source is contacted or certified."""
    _check_destination(output)
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        evidence = HistoricalNodeEvidence.model_validate_json(
            _read_text(history_path, MAXIMUM_INPUT_BYTES)
        )
        if str(evidence.tenant_id) != str(UUID(tenant)) or evidence.cluster_resource_id != cluster:
            raise ValueError("historical Node scope mismatch")
        result = review_node_history(
            evidence,
            as_of=evaluated_at,
            maximum_source_age_seconds=maximum_source_age_seconds,
        )
        write_exclusive(output, result.model_dump_json(indent=2))
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Historical Node review failed. Check exact scope, original receipts, grid, "
            "values and budgets. Input values are not echoed."
        ) from error
    typer.echo("Saved supplied-history review; source admission remains unverified.")


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


def _emit_output(output: Path | None, rendered: str) -> None:
    if output is None:
        typer.echo(rendered)
    else:
        write_exclusive(output, rendered)


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
        _emit_output(output, rendered)
    except OSError as error:
        typer.echo(
            "Could not create assessment artifacts; existing files/directories "
            "are not overwritten.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    raise typer.Exit(code=0 if result.status == "complete" else 3)


@app.command("stage-assessment-input")
def stage_assessment_input_command(
    batch: Annotated[Path, typer.Option("--batch", help="Single-target batch profile.")],
    inventory: Annotated[Path, typer.Option("--inventory", help="Approved Azure inventory JSON.")],
    metadata: Annotated[
        Path, typer.Option("--metadata", help="Sanitized Kubernetes metadata JSON.")
    ],
    slot: Annotated[str, typer.Option("--slot", help="Original scheduled UTC time.")],
) -> None:
    """Stage an inventory-only input from approved exports without querying sources."""
    try:
        scheduled_at = _evaluation_time(slot)
        assert scheduled_at is not None
        stage_assessment_input(batch, inventory, metadata, now=datetime.now(UTC), slot=scheduled_at)
    except BatchInputError as error:
        typer.echo(f"Input not staged: {error}", err=True)
        raise typer.Exit(2) from error
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Input not staged. Check export and batch formats, source clocks, approved scope "
            "and destination. Input values are not echoed."
        ) from error
    typer.echo("Staged inventory input for the scheduled slot.")


@app.command("assess-batch")
def assess_batch_command(
    batch: Annotated[Path, typer.Option("--batch", help="Approved JSON batch profile.")],
    artifacts: Annotated[Path, typer.Option("--artifacts", help="Existing protected archive.")],
    feed: Annotated[Path, typer.Option("--feed", help="Headlamp JSON destination.")],
    slot: Annotated[str | None, typer.Option("--slot", help="Original scheduled UTC time.")] = None,
) -> None:
    """Assess fresh saved fragments and publish a single Headlamp feed. No source requests."""
    now = datetime.now(UTC)
    try:
        run, partial = assess_batch(batch, artifacts, feed, now=now, slot=_evaluation_time(slot))
    except BatchInputError as error:
        typer.echo(f"Batch not published: {error}", err=True)
        raise typer.Exit(2) from error
    except FeedLockedError as error:
        typer.echo("Batch not published: feed is locked; see the scheduling runbook.", err=True)
        raise typer.Exit(1) from error
    except BatchStatusError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    except (OSError, ValueError) as error:
        typer.echo("Batch not published: check storage, replay and feed limits.", err=True)
        raise typer.Exit(1) from error
    outcome = "partial" if partial else "complete"
    if run is None:
        typer.echo(
            f"Schedule slot already published ({outcome}); retained the original evaluation."
        )
    else:
        typer.echo(f"Published {outcome} assessment batch: {run.name}")
    raise typer.Exit(3 if partial else 0)


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
    additional_packs: Annotated[list[str] | None, typer.Option("--pack")] = None,
    assessment_artifacts: Annotated[
        Path | None,
        typer.Option(
            "--assessment-artifacts",
            help="Original bundle for retained quality only; live quality stays unknown.",
        ),
    ] = None,
    source_acceptance_path: Annotated[
        Path | None,
        typer.Option(
            "--source-acceptance",
            help="Fixed-window executed source evidence; live Grafana quality stays unknown.",
        ),
    ] = None,
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
        provenance, queries = render_query_bundle(
            catalog,
            [pack_id, *(additional_packs or [])],
            profile,
            source,
            targets,
            mode,
            step_seconds=step_seconds,
        )
        source_profile = catalog.source(
            next(item.catalog_profile for item in profile.metric_sources if item.name == source)
        )
        export = (
            QueryExportManifest(
                mode=mode, pack=provenance[0], queries=queries, source_profile=source_profile
            )
            if len(provenance) == 1
            else QueryBundleExportManifest(
                mode=mode, packs=provenance, queries=queries, source_profile=source_profile
            )
        )
        retained = (
            retained_query_quality(
                assessment_artifacts,
                queries,
                source_profile,
                tenant_id=str(profile.scope.tenant_id),
            )
            if assessment_artifacts is not None
            else None
        )
        source_acceptance = (
            read_model(source_acceptance_path, PrometheusSourceAcceptance)
            if source_acceptance_path is not None
            else None
        )
        if source_acceptance is not None and (
            source_acceptance.tenant_id != str(profile.scope.tenant_id)
            or source_acceptance.cluster_resource_id
            not in {target.cluster_resource_id for target in targets}
            or source_acceptance.source != source
            or source_acceptance.configuration_digest
            != digest_json(profile.model_dump(mode="json"))
        ):
            raise ValueError("Source acceptance does not match the export scope or configuration")
        dashboard = (
            grafana_dashboard(
                queries,
                source_profile,
                retained_quality=retained,
                source_acceptance=source_acceptance,
            )
            if grafana
            else None
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Invalid pack, source, entity scope, profile or original assessment artifacts. "
            "Use a declared source, explicit identities and a replay-compatible bundle; "
            "sensitive input is not echoed."
        ) from error
    try:
        output.mkdir(exist_ok=False)
        for query in queries:
            write_exclusive(
                output / f"{query.metric}-{query.entity_digest}.promql", query.expression
            )
        write_exclusive(output / "manifest.json", export.model_dump_json(indent=2))
        if retained is not None:
            write_exclusive(output / "retained-quality.json", retained.model_dump_json(indent=2))
        if source_acceptance is not None:
            write_exclusive(
                output / "source-acceptance.json",
                source_acceptance.model_dump_json(indent=2),
            )
        if dashboard is not None:
            write_exclusive(
                output / "dashboard.json",
                json.dumps(dashboard, indent=2),
            )
    except OSError as error:
        typer.echo("Could not create query export; existing paths are not overwritten.", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Exported {len(queries)} scope-bound queries. No endpoints were contacted.")
    if retained is not None:
        typer.echo("Retained quality describes original evidence only; live quality stays unknown.")


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
        _emit_output(output, rendered)
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
        _emit_output(output, result.model_dump_json(indent=2))
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


@app.command("accept-prometheus-source")
def accept_prometheus_source_command(
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    plan: Annotated[Path, typer.Option("--plan", exists=True, readable=True)],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    allow_live: Annotated[bool, typer.Option("--allow-live")] = False,
) -> None:
    """Execute a fixed installed Prometheus plan and retain redacted source evidence."""
    if not allow_live:
        raise typer.BadParameter(
            "Explicit --allow-live is required; configured endpoints are not consent."
        )
    _check_destination(output)
    evaluated_at = _evaluation_time(as_of)
    assert evaluated_at is not None
    try:
        profile = load_onboarding_config(config)
        request = read_model(plan, PrometheusSourceAcceptancePlan)
        if request.configuration_digest != digest_json(profile.model_dump(mode="json")):
            raise ValueError("source acceptance configuration lock mismatch")
        if str(profile.scope.tenant_id) != request.tenant_id:
            raise ValueError("source acceptance tenant mismatch")
        source = next(
            (item for item in profile.metric_sources if item.name == request.source), None
        )
        cluster = next(
            (item for item in profile.clusters if item.resource_id == request.cluster_resource_id),
            None,
        )
        if (
            source is None
            or cluster is None
            or cluster.metric_source != request.source
            or source.catalog_profile != request.source_profile_id
            or source.authentication == "bearer-environment"
        ):
            raise ValueError("source acceptance scope or CLI authentication is unsupported")
        catalog = load_catalog()
        source_definition = catalog.source(source.catalog_profile)
        if source_definition.version != request.source_profile_version:
            raise ValueError("source acceptance profile version mismatch")
        mapping_by_query = {
            item.query.metric: effective_label_mapping(source, item.query.metric)
            for item in request.requests
        }
        for item in request.requests:
            asset = catalog.queries.get(item.query.metric)
            if asset is None or asset.version != item.query.version or asset.unit != item.unit:
                raise ValueError("source acceptance query asset mismatch")
            if source_definition.identity == "name-only":
                if item.query.metric not in source_definition.query_ids:
                    raise ValueError("source acceptance query is unsupported by its profile")
                logical_keys = {"cluster_resource_id", "namespace", "pod", "container"}
                reserved_keys: set[str] = set()
            else:
                logical_keys = required_metric_labels(asset.kind)
                reserved_keys = {
                    "container": {"workload_uid", "pod_uid"},
                    "workload_container": {"workload_uid", "membership_digest"},
                    "workload": {"workload_uid"},
                    "hpa": {"workload_uid", "hpa_uid"},
                    "node": {"node_resource_id", "node_uid"},
                    "unresolved_container": set(),
                }[asset.kind]
            mapping = mapping_by_query[item.query.metric]
            expected_keys = {mapping[key] for key in logical_keys} | reserved_keys
            if set(item.required_label_keys) != expected_keys:
                raise ValueError("source acceptance label keys do not match the profile")
            if len(item.expected_label_sets) != 1:
                raise ValueError("CLI source acceptance requires one exact entity per query")
            labels = item.expected_label_sets[0]
            if labels[mapping["cluster_resource_id"]] != request.cluster_resource_id:
                raise ValueError("source acceptance cluster label value mismatch")
            expression = render_query(asset.expression, labels, request.step_seconds)
            if item.query.expression != expression or item.query.expression_digest != digest_json(
                expression
            ):
                raise ValueError("source acceptance requires the exact installed expression")
        with PrometheusHttpReader(profile, source_name=request.source) as reader:
            result = collect_prometheus_source_acceptance(
                reader=reader,
                requests=request.requests,
                tenant_id=request.tenant_id,
                cluster_resource_id=request.cluster_resource_id,
                cluster_uid=request.cluster_uid,
                source_profile_id=request.source_profile_id,
                source_profile_version=request.source_profile_version,
                evaluated_at=evaluated_at,
                window_start=request.window_start,
                window_end=request.window_end,
                step_seconds=request.step_seconds,
                configuration_digest=request.configuration_digest,
            )
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as error:
        raise typer.BadParameter(
            "Prometheus source acceptance failed. Check the protected plan, exact configuration, "
            "installed query/profile, identity roster, authentication, clocks and budgets. "
            "Sensitive input is not echoed."
        ) from error
    try:
        write_exclusive(output, result.model_dump_json(indent=2))
    except OSError as error:
        typer.echo(
            "Could not create source acceptance output; existing files are not overwritten.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    raise typer.Exit(code=0 if result.status == "accepted" else 3)


def _attach_cost_allocation(
    ledger: CostImport, profile: str | None, path: Path | None
) -> CostImport:
    if (profile is None) != (path is None):
        raise ValueError("Supply both allocation profile and file, or neither")
    if profile is None or path is None:
        return ledger
    payload = read_model(path, RootModel[dict[str, Any]]).root
    allocation = project_allocation(profile, payload)
    return CostImport.model_validate(ledger.model_dump() | {"allocation": allocation})


@app.command("qualify-allocation")
def qualify_allocation_command(
    observation: Annotated[Path, typer.Option("--observation")],
    assessment: Annotated[Path, typer.Option("--assessment")],
    tenant: Annotated[str, typer.Option("--tenant")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Qualify saved aggregate context against an original replay-verified assessment."""
    _check_destination(output)
    try:
        clock = _evaluation_time(as_of)
        if clock is None or assessment.name != "assessment.json":
            raise ValueError("an explicit clock and original assessment file are required")
        _, original, configuration = _read_verified_archive(
            assessment.parent, tenant_id=UUID(tenant)
        )
        manifest = original.snapshot.collection_manifest
        if manifest is None or UUID(manifest.tenant_id) != UUID(tenant):
            raise ValueError("original assessment tenant binding is invalid")
        if len(original.snapshot.clusters) != 1 or clock < original.report.generated_at:
            raise ValueError("one cluster and a nonfuture assessment are required")
        cluster = original.snapshot.clusters[0]
        if cluster.uid is None or not cluster.uid.strip():
            raise ValueError("an exact original cluster fingerprint is required")
        source = AllocationObservation.model_validate_json(
            _read_text(observation, 32 * 1024 * 1024)
        )
        context = qualify_allocation_observation(
            source,
            tenant_id=tenant,
            cluster_resource_id=cluster.resource_id,
            cluster_uid=cluster.uid,
            period=CostPeriod(
                start=original.report.observation_window.start,
                end=original.report.observation_window.end,
            ),
            as_of=clock,
            maximum_evidence_age_hours=configuration.thresholds.maximum_evidence_age_hours,
        )
        write_exclusive(output, context.model_dump_json(indent=2))
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid allocation observation, original assessment, scope, clock or output. "
            "Sensitive financial input is not echoed."
        ) from error
    if context.status == "blocked":
        raise typer.Exit(3)


@app.command("review-startup")
def review_startup_command(
    history: Annotated[Path, typer.Option("--history")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Replay saved lifecycle observations; never infer application startup or sizing."""
    _check_destination(output)
    try:
        clock = _evaluation_time(as_of)
        evidence = read_model(history, StartupHistoryEvidence)
        if clock is None or evidence.tenant_id != tenant or evidence.cluster_resource_id != cluster:
            raise ValueError("Startup review requires exact scope and evaluation clock")
        result = review_startup_history(
            evidence,
            as_of=clock,
            maximum_source_age_seconds=min(
                maximum_source_age_seconds, evidence.maximum_source_age_seconds
            ),
        )
        serialized = result.model_dump_json(indent=2)
        if len(serialized.encode("utf-8")) > MAXIMUM_INPUT_BYTES:
            raise ValueError("Startup review exceeds its output budget")
        write_exclusive(output, serialized)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid saved lifecycle history, exact scope, clock, budget or output. "
            "Sensitive input values are not echoed."
        ) from error
    typer.echo(
        "Saved sampled readiness review. Application startup remains unknown; "
        "no sources were contacted."
    )


@app.command("calculate-scheduling")
def calculate_scheduling_command(
    fragments: Annotated[Path, typer.Option("--fragments")],
    native_objects: Annotated[Path, typer.Option("--native-objects")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Compare supplied CPU, memory and Pod-slot constraints offline; never certify fit."""
    _check_destination(output)
    try:
        if fragments.stat().st_size + native_objects.stat().st_size > MAXIMUM_INPUT_BYTES:
            raise ValueError("Scheduling inputs exceed their combined byte budget")
        clock = _evaluation_time(as_of)
        bundle = read_model(fragments, AssessmentFragments)
        native = read_model(native_objects, RootModel[dict[str, list[dict[str, Any]]]]).root
        selected = [item for item in bundle.kubernetes if item.cluster_resource_id == cluster]
        if (
            clock is None
            or len(selected) != 1
            or selected[0].tenant_id != tenant
            or set(native) != {"pods", "nodes"}
        ):
            raise ValueError("Scheduling calculation requires exact scope and native roster")
        result = calculate_scheduling_constraints(
            selected[0],
            pods=native["pods"],
            nodes=native["nodes"],
            as_of=clock,
            maximum_source_age_seconds=maximum_source_age_seconds,
        )
        serialized = result.model_dump_json(indent=2)
        if len(serialized.encode("utf-8")) > MAXIMUM_INPUT_BYTES:
            raise ValueError("Scheduling calculation exceeds its output byte budget")
        write_exclusive(output, serialized)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid saved scheduling evidence, exact scope, clock, budget or output. "
            "Sensitive input values are not echoed."
        ) from error
    typer.echo(
        "Saved three-resource comparisons. Source/scheduler admission and fit remain blocked."
    )


@app.command("review-placement")
def review_placement_command(
    fragments: Annotated[Path, typer.Option("--fragments")],
    tenant: Annotated[str, typer.Option("--tenant")],
    cluster: Annotated[str, typer.Option("--cluster")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
    maximum_source_age_seconds: Annotated[
        int, typer.Option("--max-source-age-seconds", min=1)
    ] = 3600,
) -> None:
    """Review retained current hard constraints offline; never calculate scheduler fit."""
    _check_destination(output)
    try:
        clock = _evaluation_time(as_of)
        bundle = read_model(fragments, AssessmentFragments)
        selected = [item for item in bundle.kubernetes if item.cluster_resource_id == cluster]
        if clock is None or len(selected) != 1 or selected[0].tenant_id != tenant:
            raise ValueError("Placement review requires one exact tenant/cluster metadata fragment")
        result = review_scheduling_placement(
            selected[0],
            as_of=clock,
            maximum_source_age_seconds=maximum_source_age_seconds,
        )
        serialized = result.model_dump_json(indent=2)
        if len(serialized.encode("utf-8")) > MAXIMUM_INPUT_BYTES:
            raise ValueError("Placement review exceeds its output byte budget")
        write_exclusive(output, serialized)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid saved metadata, exact tenant/cluster scope, clock, budget or output. "
            "Sensitive input values are not echoed."
        ) from error
    typer.echo("Saved current constraint review. Fit remains blocked; no sources were contacted.")


@app.command("order-cost-review")
def order_cost_review_command(
    observation: Annotated[list[Path], typer.Option("--observation")],
    assessment: Annotated[list[Path], typer.Option("--assessment")],
    tenant: Annotated[str, typer.Option("--tenant")],
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Order a separate comparable cluster cost review from original local artifacts."""
    _check_destination(output)
    try:
        clock = _evaluation_time(as_of)
        if (
            clock is None
            or len(observation) != len(assessment)
            or not 2 <= len(observation) <= 1000
        ):
            raise ValueError("Cost review requires an explicit clock and two to 1000 matched pairs")
        inputs = []
        remaining = 128 * 1024 * 1024
        for source, original in zip(observation, assessment, strict=True):
            if original.name != "assessment.json" or remaining <= 0:
                raise ValueError("Cost review requires bounded original assessment files")
            text = _read_text(source, min(32 * 1024 * 1024, remaining))
            remaining -= len(text.encode("utf-8"))
            inputs.append((original.parent, AllocationObservation.model_validate_json(text)))
        result = order_saved_cost_reviews(inputs, tenant_id=tenant, as_of=clock)
        serialized = result.model_dump_json(indent=2)
        if len(serialized.encode("utf-8")) > 128 * 1024 * 1024:
            raise ValueError("Cost review exceeds its output byte budget")
        write_exclusive(output, serialized)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid or incomparable cost observations, original assessments, scope, "
            "clock or output. "
            "Sensitive financial input is not echoed."
        ) from error


@app.command("project-allocation")
def project_allocation_command(
    allocation_profile: Annotated[str, typer.Option("--allocation-profile")],
    allocation: Annotated[Path, typer.Option("--allocation")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Normalize a saved allocation without a ledger, reconciliation or source access."""
    _check_destination(output)
    try:
        payload = read_model(allocation, RootModel[dict[str, Any]]).root
        result = project_allocation(allocation_profile, payload)
        if result.shares:
            raise ValueError("row shares require an authoritative ledger")
        write_exclusive(output, result.model_dump_json(indent=2))
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid saved allocation projection, profile or output. "
            "Sensitive financial input is not echoed."
        ) from error


@app.command("project-costs")
def project_costs_command(
    ledger_profile: Annotated[str, typer.Option("--ledger-profile")],
    ledger: Annotated[Path, typer.Option("--ledger", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output")],
    allocation_profile: Annotated[str | None, typer.Option("--allocation-profile")] = None,
    allocation: Annotated[
        Path | None, typer.Option("--allocation", exists=True, readable=True)
    ] = None,
) -> None:
    """Normalize approved saved financial projections; never contact an endpoint."""
    _check_destination(output)
    if (allocation_profile is None) != (allocation is None):
        raise typer.BadParameter("Supply both --allocation-profile and --allocation, or neither.")
    try:
        ledger_payload = read_model(ledger, RootModel[dict[str, Any]]).root
        result = project_ledger(ledger_profile, ledger_payload)
        result = _attach_cost_allocation(result, allocation_profile, allocation)
        write_exclusive(output, result.model_dump_json(indent=2))
    except (OSError, ValueError) as error:
        raise typer.BadParameter(
            "Invalid saved financial projection, profile, or output. "
            "Sensitive financial input is not echoed."
        ) from error


@app.command("convert-focus")
def convert_focus_command(
    manifest: Annotated[Path, typer.Option("--manifest")],
    part: Annotated[list[Path], typer.Option("--part")],
    review: Annotated[Path, typer.Option("--review")],
    output: Annotated[Path, typer.Option("--output")],
    allocation_profile: Annotated[str | None, typer.Option("--allocation-profile")] = None,
    allocation: Annotated[Path | None, typer.Option("--allocation")] = None,
) -> None:
    """Convert a bounded local Azure FOCUS CSV export; never download source files."""
    _check_destination(output)
    try:
        result = convert_focus_export(manifest, part, review)
        result = _attach_cost_allocation(result, allocation_profile, allocation)
        write_exclusive(output, result.model_dump_json(indent=2))
    except OSError, ValueError:
        raise typer.BadParameter(
            "Invalid or unsupported FOCUS manifest, CSV parts, review controls, or output. "
            "Sensitive financial input is not echoed."
        ) from None


@app.command("reconcile-costs")
def reconcile_costs_command(
    costs: Annotated[Path, typer.Option("--costs", exists=True, readable=True)],
    snapshot: Annotated[Path | None, typer.Option("--snapshot", exists=True, readable=True)] = None,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    minimum_allocation_coverage: Annotated[
        str, typer.Option("--minimum-allocation-coverage")
    ] = "0.95",
    maximum_evidence_age_hours: Annotated[
        int, typer.Option("--maximum-evidence-age-hours", min=1, max=8760)
    ] = 24,
) -> None:
    """Reconcile normalized saved financial evidence, without endpoint access."""
    from datetime import UTC
    from decimal import InvalidOperation

    evaluation_time = _evaluation_time(as_of) or datetime.now(UTC)
    _check_destination(output)
    try:
        result = CostManagementCollector().collect_costs(
            read_model(costs, CostImport),
            read_model(snapshot, FleetSnapshot) if snapshot is not None else None,
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
        _emit_output(output, result.model_dump_json(indent=2))
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
