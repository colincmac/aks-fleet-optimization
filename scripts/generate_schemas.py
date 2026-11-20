from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, RootModel

from aks_fleet_efficiency.advisory import (
    AIChecklist,
    AIChecklistDraft,
    AIEvidencePackage,
    AIExperiment,
    AIExperimentDraft,
    AIExperimentIntent,
    AIExplanation,
    AIExplanationDraft,
    AIResourceEvidencePackage,
    AIReviewIntent,
)
from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment
from aks_fleet_efficiency.catalog.models import (
    FinancialSourceDefinition,
    PackManifest,
    QueryBundleExportManifest,
    QueryExportManifest,
    SourceDefinition,
)
from aks_fleet_efficiency.collection import CollectionPlan
from aks_fleet_efficiency.config import AdvisorConfig, OnboardingConfig
from aks_fleet_efficiency.controller_evidence import ControllerEvidence
from aks_fleet_efficiency.cost import (
    AllocationContext,
    AllocationObservation,
    ClusterCostReviewOrder,
    CostAllocation,
    CostImport,
    CostReconciliation,
)
from aks_fleet_efficiency.cost_sources.focus_export import FocusExportReview
from aks_fleet_efficiency.daemonsets import DaemonSetMembershipReview
from aks_fleet_efficiency.experiments import (
    ExperimentExecutionOutcome,
    ExperimentHandoff,
    ExperimentHandoffRequest,
    ExperimentOutcomeRequest,
)
from aks_fleet_efficiency.fleet import FleetInsightReport
from aks_fleet_efficiency.fleet_context import FleetContext, FleetContextReview
from aks_fleet_efficiency.history import (
    FleetDriftMatrix,
    FleetHistoryTrend,
    HistoryRun,
    HistoryTrend,
)
from aks_fleet_efficiency.models import (
    AnalysisReport,
    AzureInventorySnapshot,
    FleetSnapshot,
    KubernetesMetadataSnapshot,
    MetricQueryPlan,
    PodContainerAttempts,
    PrometheusMetricsSnapshot,
    ReadinessReport,
    SourceCapabilityReport,
    StartupHistoryEvidence,
)
from aks_fleet_efficiency.nap_policy import NapPolicyInput, NapPolicyReview
from aks_fleet_efficiency.node_history import HistoricalNodeEvidence, HistoricalNodeReview
from aks_fleet_efficiency.operator import (
    ExecutionPreview,
    OperatorCatalog,
    OperatorInspection,
    RetainedAssessmentQuality,
)
from aks_fleet_efficiency.scheduling import (
    DaemonSetStatusProjection,
    DisruptionProtectionProjection,
    SchedulingCompletenessAudit,
    SchedulingConstraintCalculation,
    SchedulingPlacementReview,
    SchedulingShapeDiagnostics,
    SchedulingShapeProjection,
    SchedulingSourceCollection,
)
from aks_fleet_efficiency.scheduling_fit import (
    PendingNapConstraintReview,
    SchedulingNecessaryFitReview,
)
from aks_fleet_efficiency.source_acceptance import (
    PrometheusSourceAcceptance,
    PrometheusSourceAcceptancePlan,
)
from aks_fleet_efficiency.storage import StorageContextProjection
from aks_fleet_efficiency.value_outcomes import (
    EngineeringChangeRecord,
    EngineeringCpuOutcome,
    ExperimentValueOutcome,
    ExperimentValueOutcomeRequest,
)
from aks_fleet_efficiency.vpa_review import CurrentVpaEvidence

ROOT = Path(__file__).resolve().parents[1]


def generate_schemas(output_dir: Path, *, check: bool = False) -> bool:
    matches = True
    models: dict[str, type[BaseModel]] = {
        "ai-evidence-package.schema.json": AIEvidencePackage,
        "ai-resource-evidence-package.schema.json": AIResourceEvidencePackage,
        "ai-explanation-draft.schema.json": AIExplanationDraft,
        "ai-explanation.schema.json": AIExplanation,
        "ai-review-intent.schema.json": AIReviewIntent,
        "ai-checklist-draft.schema.json": AIChecklistDraft,
        "ai-checklist.schema.json": AIChecklist,
        "ai-experiment-intent.schema.json": AIExperimentIntent,
        "ai-experiment-draft.schema.json": AIExperimentDraft,
        "ai-experiment.schema.json": AIExperiment,
        "experiment-handoff.schema.json": ExperimentHandoff,
        "experiment-handoff-request.schema.json": ExperimentHandoffRequest,
        "experiment-outcome-request.schema.json": ExperimentOutcomeRequest,
        "experiment-execution-outcome.schema.json": ExperimentExecutionOutcome,
        "experiment-value-outcome.schema.json": ExperimentValueOutcome,
        "experiment-value-outcome-request.schema.json": ExperimentValueOutcomeRequest,
        "engineering-change-record.schema.json": EngineeringChangeRecord,
        "engineering-cpu-outcome.schema.json": EngineeringCpuOutcome,
        "fleet-insight.schema.json": FleetInsightReport,
        "fleet-context.schema.json": FleetContext,
        "fleet-context-review.schema.json": FleetContextReview,
        "historical-node-evidence.schema.json": HistoricalNodeEvidence,
        "historical-node-review.schema.json": HistoricalNodeReview,
        "fleet-history-trend.schema.json": FleetHistoryTrend,
        "fleet-drift-matrix.schema.json": FleetDriftMatrix,
        "history-run.schema.json": HistoryRun,
        "history-trend.schema.json": HistoryTrend,
        "cost-allocation.schema.json": CostAllocation,
        "allocation-observation.schema.json": AllocationObservation,
        "allocation-context.schema.json": AllocationContext,
        "cluster-cost-review-order.schema.json": ClusterCostReviewOrder,
        "cost-import.schema.json": CostImport,
        "cost-reconciliation.schema.json": CostReconciliation,
        "focus-export-review.schema.json": FocusExportReview,
        "operator-catalog.schema.json": OperatorCatalog,
        "operator-inspection.schema.json": OperatorInspection,
        "execution-preview.schema.json": ExecutionPreview,
        "retained-assessment-quality.schema.json": RetainedAssessmentQuality,
        "controller-evidence.schema.json": ControllerEvidence,
        "current-vpa-evidence.schema.json": CurrentVpaEvidence,
        "source-profile.schema.json": SourceDefinition,
        "financial-source-profile.schema.json": FinancialSourceDefinition,
        "source-capabilities.schema.json": SourceCapabilityReport,
        "metric-query-plan.schema.json": MetricQueryPlan,
        "recommendation-pack.schema.json": PackManifest,
        "query-export.schema.json": RootModel[QueryExportManifest | QueryBundleExportManifest],
        "analysis-config.schema.json": AdvisorConfig,
        "fleet-snapshot.schema.json": FleetSnapshot,
        "analysis-report.schema.json": AnalysisReport,
        "onboarding-config.schema.json": OnboardingConfig,
        "readiness-report.schema.json": ReadinessReport,
        "azure-inventory.schema.json": AzureInventorySnapshot,
        "kubernetes-metadata.schema.json": KubernetesMetadataSnapshot,
        "daemonset-status-projection.schema.json": DaemonSetStatusProjection,
        "daemonset-membership-review.schema.json": DaemonSetMembershipReview,
        "storage-context-projection.schema.json": StorageContextProjection,
        "nap-policy-input.schema.json": NapPolicyInput,
        "nap-policy-review.schema.json": NapPolicyReview,
        "startup-history.schema.json": StartupHistoryEvidence,
        "scheduling-constraint-calculation.schema.json": SchedulingConstraintCalculation,
        "pod-container-attempts.schema.json": PodContainerAttempts,
        "scheduling-completeness-audit.schema.json": SchedulingCompletenessAudit,
        "scheduling-shape-projection.schema.json": SchedulingShapeProjection,
        "scheduling-shape-diagnostics.schema.json": SchedulingShapeDiagnostics,
        "scheduling-placement-review.schema.json": SchedulingPlacementReview,
        "disruption-protection-projection.schema.json": DisruptionProtectionProjection,
        "scheduling-source-collection.schema.json": SchedulingSourceCollection,
        "scheduling-necessary-fit-review.schema.json": SchedulingNecessaryFitReview,
        "pending-nap-constraint-review.schema.json": PendingNapConstraintReview,
        "prometheus-metrics.schema.json": PrometheusMetricsSnapshot,
        "prometheus-source-acceptance.schema.json": PrometheusSourceAcceptance,
        "prometheus-source-acceptance-plan.schema.json": PrometheusSourceAcceptancePlan,
        "assessment-fragments.schema.json": AssessmentFragments,
        "offline-assessment.schema.json": OfflineAssessment,
        "collection-plan.schema.json": CollectionPlan,
    }
    for name, model in models.items():
        expected = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        destination = output_dir / name
        if check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != expected:
                print(f"Schema missing or stale: {destination}")
                matches = False
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            destination.write_text(expected, encoding="utf-8", newline="\n")
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check the committed JSON Schemas.")
    parser.add_argument("--check", action="store_true", help="Report drift without writing files.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "schemas")
    arguments = parser.parse_args(argv)
    return 0 if generate_schemas(arguments.output_dir, check=arguments.check) else 1


if __name__ == "__main__":
    raise SystemExit(main())
