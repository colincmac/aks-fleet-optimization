from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from aks_fleet_efficiency.artifacts import MAXIMUM_INPUT_BYTES, read_model
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.collection import (
    CollectionPlan,
    CollectionReaders,
    validate_metadata_binding,
)
from aks_fleet_efficiency.collectors.azure_resource_graph import AzureSdkInventoryReader
from aks_fleet_efficiency.collectors.prometheus import PrometheusHttpReader
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import KubernetesMetadataSnapshot


def load_collection_plan(path: Path, *, resolve_exports: bool = True) -> CollectionPlan:
    plan = read_model(path, CollectionPlan)
    for target in plan.clusters:
        if target.metadata_export is not None and not target.metadata_export.is_absolute():
            export = path.parent / target.metadata_export
            target.metadata_export = export.resolve() if resolve_exports else export.absolute()
    return plan


@contextmanager
def builtin_readers(
    profile: OnboardingConfig, plan: CollectionPlan, *, allow_live: bool
) -> Iterator[CollectionReaders]:
    if not allow_live:
        raise PermissionError("explicit --allow-live is required before client construction")
    if {item.resource_id for item in plan.clusters} != {
        item.resource_id for item in profile.clusters
    }:
        raise ValueError("collection plan exceeds approved scope")
    exports = {}
    total_bytes = 0
    for target in plan.clusters:
        if target.metadata_export is None:
            raise ValueError(
                "CLI requires sanitized metadata_export files; "
                "inject approved Kubernetes readers through the Python API"
            )
        total_bytes += target.metadata_export.stat().st_size
        if total_bytes > MAXIMUM_INPUT_BYTES:
            raise ValueError("metadata export budget exceeded")
        metadata = read_model(target.metadata_export, KubernetesMetadataSnapshot)
        validate_metadata_binding(metadata, target, profile)
        exports[target.resource_id] = metadata
    required = (
        None
        if profile.analysis.packs is None
        else {
            name
            for pack_id in profile.analysis.packs
            for references in load_catalog().pack(pack_id).queries[profile.analysis.mode].values()
            for name in references
        }
    )
    source_names = {
        target.metric_source
        for target in profile.clusters
        if any(
            item.resource_id == target.resource_id
            and item.entities
            and (required is None or set(item.metrics) & required)
            for item in plan.clusters
        )
    }
    for source in profile.metric_sources:
        if source.name in source_names and source.authentication == "bearer-environment":
            raise ValueError(
                "CLI does not read bearer environment values; "
                "inject an approved credential reader through the Python API"
            )
    with ExitStack() as stack:
        inventory = stack.enter_context(AzureSdkInventoryReader(profile))
        metrics = {
            source: stack.enter_context(PrometheusHttpReader(profile, source_name=source))
            for source in sorted(name for name in source_names if name is not None)
        }
        yield CollectionReaders(inventory=inventory, metrics=metrics, metadata_snapshots=exports)
