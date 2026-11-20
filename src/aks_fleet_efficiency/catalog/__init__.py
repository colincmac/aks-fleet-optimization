from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from aks_fleet_efficiency.catalog.models import (
    AssessmentMode,
    FinancialSourceDefinition,
    Inventory,
    PackManifest,
    PackParameters,
    PackProvenance,
    QueryAsset,
    QueryCatalog,
    RenderedQuery,
    RuleInventory,
    SourceDefinition,
    validate_parameters,
)

if TYPE_CHECKING:
    from aks_fleet_efficiency.config import OnboardingConfig
    from aks_fleet_efficiency.models import MetricEntity


def digest_json(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _check_yaml_keys(node: Node) -> None:
    if isinstance(node, MappingNode):
        seen: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode) or key.value in seen:
                raise ValueError("Catalog YAML keys must be simple and distinct")
            seen.add(key.value)
            _check_yaml_keys(value)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            _check_yaml_keys(value)


def _catalog_yaml(text: str) -> object:
    return json.loads(json.dumps(_parsed_catalog_yaml(text)))


@lru_cache(maxsize=64)
def _parsed_catalog_yaml(text: str) -> object:
    node = yaml.compose(text, Loader=yaml.SafeLoader)
    if node is None:
        raise ValueError("Catalog assets must not be empty")
    _check_yaml_keys(node)
    return yaml.safe_load(text)


@dataclass(frozen=True)
class Catalog:
    manifests: dict[str, PackManifest]
    queries: dict[str, QueryAsset]
    inventory: list[RuleInventory]
    sources: dict[str, SourceDefinition]
    financial_sources: dict[str, FinancialSourceDefinition]

    @property
    def default_pack_ids(self) -> list[str]:
        return sorted(set(self.manifests) - {"AKS-START-001"})

    def financial_source(self, source_id: str) -> FinancialSourceDefinition:
        if source_id not in self.financial_sources:
            raise ValueError("Unknown financial source catalog profile")
        return self.financial_sources[source_id]

    def source(self, source_id: str) -> SourceDefinition:
        if source_id not in self.sources:
            raise ValueError("Unknown source catalog profile")
        return self.sources[source_id]

    def pack(self, pack_id: str) -> PackManifest:
        if pack_id not in self.manifests:
            raise ValueError(f"Unknown or unimplemented pack: {pack_id}")
        return self.manifests[pack_id]

    def provenance(self, pack_id: str, parameters: PackParameters | None = None) -> PackProvenance:
        pack = self.pack(pack_id)
        if parameters is not None:
            validate_parameters(pack.evaluator, parameters)
        references = sorted(
            {name for modes in pack.queries.values() for names in modes.values() for name in names}
        )
        queries = [self.queries[name] for name in references]
        digest = digest_json(
            {
                "manifest": pack.model_dump(mode="json"),
                "queries": [query.model_dump(mode="json") for query in queries],
            }
        )
        return PackProvenance(
            id=pack.id,
            version=pack.version,
            digest=digest,
            parameters=parameters if parameters is not None else pack.parameters,
            queries=queries,
        )


def load_catalog(root: Path | None = None) -> Catalog:
    assets = root if root is not None else files(__package__)
    definitions = QueryCatalog.model_validate(
        _catalog_yaml(assets.joinpath("queries.yaml").read_text(encoding="utf-8"))
    )
    queries = {
        name: QueryAsset(
            id=name,
            version=definition.version,
            unit=definition.unit,
            kind=definition.kind,
            delta=definition.delta,
            expression=assets.joinpath("queries", definition.file)
            .read_text(encoding="utf-8")
            .strip(),
        )
        for name, definition in definitions.queries.items()
    }
    inventory = Inventory.model_validate(
        _catalog_yaml(assets.joinpath("inventory.yaml").read_text(encoding="utf-8"))
    ).rules
    if len({item.id for item in inventory}) != len(inventory):
        raise ValueError("Rule inventory contains duplicate IDs")
    manifests: dict[str, PackManifest] = {}
    for file in sorted(assets.joinpath("packs").iterdir(), key=lambda item: item.name):
        if not file.name.endswith(".yaml"):
            continue
        pack = PackManifest.model_validate(_catalog_yaml(file.read_text(encoding="utf-8")))
        if pack.id in manifests:
            raise ValueError("Catalog contains duplicate pack IDs")
        if pack.id not in {item.id for item in inventory}:
            raise ValueError("Pack is absent from the rule inventory")
        for modes in pack.queries.values():
            for kind, references in modes.items():
                expected = "container" if kind == "unresolved_container" else kind
                if any(
                    name not in queries or queries[name].kind != expected for name in references
                ):
                    raise ValueError("Pack references unknown or incompatible queries")
        manifests[pack.id] = pack
    missing = {item.id for item in inventory} - manifests.keys()
    if missing:
        raise ValueError(f"Rule inventory has missing packs: {', '.join(sorted(missing))}")
    sources: dict[str, SourceDefinition] = {}
    for file in sorted(assets.joinpath("sources").iterdir(), key=lambda item: item.name):
        if file.name.endswith(".yaml"):
            source = SourceDefinition.model_validate(
                _catalog_yaml(file.read_text(encoding="utf-8"))
            )
            if source.id in sources or any(name not in queries for name in source.query_ids):
                raise ValueError("Duplicate source profile or unknown source query reference")
            sources[source.id] = source
    if not sources:
        raise ValueError("Catalog has no source profiles")
    financial_sources: dict[str, FinancialSourceDefinition] = {}
    for file in sorted(assets.joinpath("cost_sources").iterdir(), key=lambda item: item.name):
        if file.name.endswith(".yaml"):
            financial_source = FinancialSourceDefinition.model_validate(
                _catalog_yaml(file.read_text(encoding="utf-8"))
            )
            if financial_source.id in financial_sources:
                raise ValueError("Duplicate financial source profile")
            financial_sources[financial_source.id] = financial_source
    if not financial_sources:
        raise ValueError("Catalog has no financial source profiles")
    return Catalog(
        manifests=manifests,
        queries=queries,
        inventory=inventory,
        sources=sources,
        financial_sources=financial_sources,
    )


def render_pack_queries(
    catalog: Catalog,
    pack_id: str,
    profile: OnboardingConfig,
    source_name: str,
    entities: list[MetricEntity],
    mode: AssessmentMode,
    *,
    step_seconds: int = 300,
) -> list[RenderedQuery]:
    from aks_fleet_efficiency.collectors.metric_queries import metric_labels, render_query
    from aks_fleet_efficiency.models import MetricEntity

    pack = catalog.pack(pack_id)
    if pack.evidence_kind == "inventory":
        raise ValueError(
            "Inventory pack has no PromQL; inspect scoped metadata requirements with catalog show"
        )
    if mode not in {"baseline", "guarded"}:
        raise ValueError("Select baseline or guarded assessment mode")
    sources = [source for source in profile.metric_sources if source.name == source_name]
    if len(sources) != 1 or sources[0].type not in pack.sources:
        raise ValueError("Select exactly one declared, supported metric source")
    source = sources[0]
    definition = catalog.source(source.catalog_profile)
    if source.type not in definition.transports:
        raise ValueError("Unsupported source transport for declared profile")
    allowed = {
        target.resource_id for target in profile.clusters if target.metric_source == source_name
    }
    if not entities or len(entities) > 10000 or not 1 <= step_seconds <= 300:
        raise ValueError("Provide bounded entities and a supported metric step")
    entities = [MetricEntity.model_validate(entity.model_dump()) for entity in entities]
    if len({entity.model_dump_json() for entity in entities}) != len(entities):
        raise ValueError("Query export entities must be distinct")
    result: list[RenderedQuery] = []
    for entity in entities:
        if entity.cluster_resource_id not in allowed:
            raise ValueError("Query export exceeds the approved source/cluster scope")
        if entity.kind == "unresolved_container":
            if mode == "guarded":
                raise ValueError("Name-only source cannot support guarded proposals")
            if definition.identity != "name-only":
                raise ValueError(
                    "Unresolved identity requires an explicit name-only source profile"
                )
        elif definition.identity == "name-only":
            raise ValueError("Name-only source cannot attest historical UIDs")
        if entity.kind not in {
            "container",
            "workload_container",
            "unresolved_container",
            "node",
            "workload",
            "hpa",
        }:
            raise ValueError("Pack requires an explicitly supported historical entity")
        if entity.kind == "container":
            references = pack.queries[mode].get("container", [])
        elif entity.kind == "workload_container":
            references = pack.queries[mode].get("workload_container", [])
        elif entity.kind == "node":
            references = pack.queries[mode].get("node", [])
        elif entity.kind == "workload":
            references = pack.queries[mode].get("workload", [])
        elif entity.kind == "hpa":
            references = pack.queries[mode].get("hpa", [])
        else:
            references = pack.queries[mode].get("unresolved_container", [])
        if not references:
            raise ValueError("Pack does not support the requested entity kind")
        for name in references:
            asset = catalog.queries[name]
            labels = metric_labels(entity, source, name)
            expression = render_query(asset.expression, labels, step_seconds)
            result.append(
                RenderedQuery(
                    metric=name,
                    version=asset.version,
                    source=source_name,
                    expression=expression,
                    expression_digest=sha256(expression.encode()).hexdigest(),
                    entity_digest=digest_json(entity.model_dump(mode="json")),
                    step_seconds=step_seconds,
                )
            )
    return sorted(result, key=lambda query: (query.entity_digest, query.metric))


def render_query_bundle(
    catalog: Catalog,
    pack_ids: list[str],
    profile: OnboardingConfig,
    source_name: str,
    entities: list[MetricEntity],
    mode: AssessmentMode,
    *,
    step_seconds: int = 300,
) -> tuple[list[PackProvenance], list[RenderedQuery]]:
    if (
        not pack_ids
        or len(pack_ids) > len(catalog.manifests)
        or len(set(pack_ids)) != len(pack_ids)
    ):
        raise ValueError("Select distinct implemented packs")
    if not entities or len(entities) > 10000:
        raise ValueError("Provide bounded explicit entities")
    packs = [catalog.pack(name) for name in sorted(pack_ids)]
    if any(pack.evidence_kind == "inventory" for pack in packs):
        raise ValueError("Inventory packs have no query export")
    kinds = {kind for pack in packs for kind in pack.queries[mode]}
    if any(entity.kind not in kinds for entity in entities):
        raise ValueError("Every entity must match a selected pack")
    provenance = []
    queries: dict[tuple[str, str, str], RenderedQuery] = {}
    for pack in packs:
        selected = [entity for entity in entities if entity.kind in pack.queries[mode]]
        if not selected:
            raise ValueError("Every selected pack requires a matching entity")
        locked = catalog.provenance(pack.id, profile.analysis.pack_parameters.get(pack.id))
        if (
            profile.analysis.pack_locks
            and profile.analysis.pack_locks.get(pack.id) != locked.digest
        ):
            raise ValueError("Export pack lock differs from installed assets")
        provenance.append(locked)
        for query in render_pack_queries(
            catalog, pack.id, profile, source_name, selected, mode, step_seconds=step_seconds
        ):
            key = (query.source, query.entity_digest, query.metric)
            if key in queries and queries[key] != query:
                raise ValueError("Conflicting query definitions in bundle")
            queries[key] = query
    return provenance, [queries[key] for key in sorted(queries)]
