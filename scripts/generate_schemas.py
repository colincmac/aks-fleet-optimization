from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment
from aks_fleet_efficiency.catalog.models import PackManifest, QueryExportManifest, SourceDefinition
from aks_fleet_efficiency.collection import CollectionPlan
from aks_fleet_efficiency.config import AdvisorConfig, OnboardingConfig
from aks_fleet_efficiency.cost import CostImport, CostReconciliation
from aks_fleet_efficiency.history import HistoryRun, HistoryTrend
from aks_fleet_efficiency.models import (
    AnalysisReport,
    AzureInventorySnapshot,
    FleetSnapshot,
    KubernetesMetadataSnapshot,
    MetricQueryPlan,
    PrometheusMetricsSnapshot,
    ReadinessReport,
    SourceCapabilityReport,
)
from aks_fleet_efficiency.operator import ExecutionPreview, OperatorCatalog, OperatorInspection

ROOT = Path(__file__).resolve().parents[1]


def generate_schemas(output_dir: Path, *, check: bool = False) -> bool:
    matches = True
    models: dict[str, type[BaseModel]] = {
        "history-run.schema.json": HistoryRun,
        "history-trend.schema.json": HistoryTrend,
        "cost-import.schema.json": CostImport,
        "cost-reconciliation.schema.json": CostReconciliation,
        "operator-catalog.schema.json": OperatorCatalog,
        "operator-inspection.schema.json": OperatorInspection,
        "execution-preview.schema.json": ExecutionPreview,
        "source-profile.schema.json": SourceDefinition,
        "source-capabilities.schema.json": SourceCapabilityReport,
        "metric-query-plan.schema.json": MetricQueryPlan,
        "recommendation-pack.schema.json": PackManifest,
        "query-export.schema.json": QueryExportManifest,
        "analysis-config.schema.json": AdvisorConfig,
        "fleet-snapshot.schema.json": FleetSnapshot,
        "analysis-report.schema.json": AnalysisReport,
        "onboarding-config.schema.json": OnboardingConfig,
        "readiness-report.schema.json": ReadinessReport,
        "azure-inventory.schema.json": AzureInventorySnapshot,
        "kubernetes-metadata.schema.json": KubernetesMetadataSnapshot,
        "prometheus-metrics.schema.json": PrometheusMetricsSnapshot,
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
