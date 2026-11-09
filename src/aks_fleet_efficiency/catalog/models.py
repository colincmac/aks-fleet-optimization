from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssessmentMode = Literal["baseline", "guarded"]
PackId = Annotated[str, Field(pattern=r"^AKS-[A-Z]+-[0-9]{3}$")]
Version = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
QueryId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
EntityKind = Literal[
    "container", "workload_container", "unresolved_container", "node", "workload", "hpa"
]
EvaluatorId = Literal[
    "cpu-request-review",
    "missing-cpu-request",
    "cpu-request-risk",
    "node-pool-review",
    "scheduling-review",
    "capacity-review",
    "oom-investigation",
    "memory-safety-review",
    "memory-request-proposal",
    "pod-memory-accounting",
    "memory-limit-proposal",
    "restart-investigation",
    "termination-context",
    "eviction-investigation",
    "fixed-replica-review",
    "autoscaler-interaction",
    "hpa-pinning",
    "controller-responsibility",
    "hpa-floor-proposal",
    "hpa-change-review",
    "vpa-bounds-review",
]
SourceKind = Literal["prometheus", "azure-managed-prometheus"]
SourceProfileId = Literal["identity-enriched", "cadvisor-ksm"]
Component = Literal["prometheus", "kube-state-metrics", "cadvisor", "kubernetes"]
ComponentVersion = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.]+)?$")]
SummaryCode = Literal[
    "default", "multiple-controllers", "keda-chain", "cpu-memory-only", "zero-minimum"
]


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)


class PackParameters(CatalogModel):
    review_ratio: float | None = Field(default=None, strict=True)


def validate_parameters(evaluator: EvaluatorId, parameters: PackParameters) -> None:
    ratio = parameters.review_ratio
    if evaluator not in {"cpu-request-review", "cpu-request-risk", "node-pool-review"}:
        if ratio is not None:
            raise ValueError(
                "This pack has no ratio parameter; proposal bounds belong to owner policy"
            )
    elif ratio is None:
        raise ValueError("A metric review pack requires an explicit review ratio")
    elif evaluator == "cpu-request-review" and not 0 < ratio < 1:
        raise ValueError("CPU reduction review ratio must be between zero and one")
    elif evaluator == "cpu-request-risk" and ratio <= 0:
        raise ValueError("CPU request-risk review ratio must be positive")
    elif evaluator == "node-pool-review" and not 0 <= ratio < 1:
        raise ValueError("Pool review ratio must be at least zero and below one")


class PackManifest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    id: PackId
    version: Version
    family: Literal["cpu", "node-pool", "memory", "reliability", "autoscaler", "scheduling"]
    evaluator: EvaluatorId
    evidence_kind: Literal["metrics", "inventory"] = "metrics"
    title: Text
    purpose: Text
    sources: list[SourceKind]
    parameters: PackParameters
    queries: dict[AssessmentMode, dict[EntityKind, list[QueryId]]]
    required_evidence: dict[AssessmentMode, list[Text]]
    limitations: list[Text] = Field(min_length=1)
    prerequisites: list[Text] = Field(min_length=1)
    risks: list[Text] = Field(min_length=1)
    validation: list[Text] = Field(min_length=1)
    rollback: list[Text] = Field(min_length=1)
    baseline_rollback: list[Text] = Field(default_factory=list)
    summary_variants: dict[SummaryCode, Text] = Field(default_factory=dict)
    actions: dict[AssessmentMode, list[Text]]
    baseline_summary: Text
    guarded_summary: Text

    @model_validator(mode="after")
    def validate_modes(self) -> PackManifest:
        validate_parameters(self.evaluator, self.parameters)
        expected_summaries = (
            {"multiple-controllers", "keda-chain", "cpu-memory-only", "zero-minimum"}
            if self.evaluator == "controller-responsibility"
            else set()
        )
        if set(self.summary_variants) != expected_summaries:
            raise ValueError("Pack summary variants must match its closed evaluator")
        if self.evaluator == "cpu-request-review" and not self.baseline_rollback:
            raise ValueError("CPU review requires explicit baseline rollback guidance")
        bindings = {
            "cpu-request-review": ("AKS-RQ-002", "cpu", "metrics"),
            "missing-cpu-request": ("AKS-RQ-001", "cpu", "inventory"),
            "cpu-request-risk": ("AKS-RQ-003", "cpu", "metrics"),
            "node-pool-review": ("AKS-NP-001", "node-pool", "metrics"),
            "scheduling-review": ("AKS-SCHED-001", "scheduling", "inventory"),
            "capacity-review": ("AKS-NP-002", "node-pool", "inventory"),
            "oom-investigation": ("AKS-MEM-001", "memory", "metrics"),
            "memory-safety-review": ("AKS-MEM-002", "memory", "metrics"),
            "memory-request-proposal": ("AKS-MEM-003", "memory", "metrics"),
            "pod-memory-accounting": ("AKS-MEM-004", "memory", "inventory"),
            "memory-limit-proposal": ("AKS-MEM-005", "memory", "metrics"),
            "restart-investigation": ("AKS-REL-001", "reliability", "metrics"),
            "termination-context": ("AKS-REL-002", "reliability", "inventory"),
            "eviction-investigation": ("AKS-REL-003", "reliability", "metrics"),
            "fixed-replica-review": ("AKS-AS-001", "autoscaler", "inventory"),
            "autoscaler-interaction": ("AKS-AS-002", "autoscaler", "inventory"),
            "hpa-pinning": ("AKS-AS-003", "autoscaler", "metrics"),
            "controller-responsibility": ("AKS-AS-004", "autoscaler", "inventory"),
            "hpa-floor-proposal": ("AKS-AS-005", "autoscaler", "metrics"),
            "hpa-change-review": ("AKS-AS-006", "autoscaler", "metrics"),
            "vpa-bounds-review": ("AKS-AS-007", "autoscaler", "inventory"),
        }
        if (self.id, self.family, self.evidence_kind) != bindings[self.evaluator]:
            raise ValueError("Pack ID/family/evidence must match its closed evaluator")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("pack source types must be distinct")
        if set(self.queries) != {"baseline", "guarded"} or set(self.required_evidence) != {
            "baseline",
            "guarded",
        }:
            raise ValueError("pack requires both baseline and guarded evidence definitions")
        for mode, definitions in self.queries.items():
            expected = (
                set()
                if self.evidence_kind == "inventory"
                else {"node"}
                if self.evaluator == "node-pool-review"
                else {"container", "workload_container"}
            )
            if self.evaluator == "cpu-request-review" and mode == "baseline":
                expected.add("unresolved_container")
            if self.evaluator in {"memory-safety-review", "memory-request-proposal"}:
                expected = {"container", "workload_container", "workload"}
            elif self.evaluator == "memory-limit-proposal":
                expected = {"container", "workload"}
            elif self.evaluator == "eviction-investigation":
                expected = {"workload"}
            elif self.evaluator in {"hpa-pinning", "hpa-change-review"}:
                expected = {"hpa"}
            elif self.evaluator == "hpa-floor-proposal":
                expected = {"hpa", "workload"}
            if set(definitions) != expected:
                raise ValueError("Pack requires its evaluator-specific query entity definitions")
            for references in definitions.values():
                if not references or len(set(references)) != len(references):
                    raise ValueError("pack query references must be nonempty and distinct")
        if any(not fields for fields in self.required_evidence.values()):
            raise ValueError("pack requires nonempty evidence definitions")
        if set(self.actions) != {"baseline", "guarded"} or any(
            not items for items in self.actions.values()
        ):
            raise ValueError("Pack requires nonempty operator actions for both modes")
        if (self.evidence_kind == "metrics") != bool(self.sources):
            raise ValueError("Only metric packs declare Prometheus transports")
        return self


class QueryFile(CatalogModel):
    file: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*\.promql$")]
    version: Version
    unit: Literal["mCPU", "MiB", "ratio", "events", "pods", "boolean"]
    kind: EntityKind = "container"
    delta: bool = False


class QueryAsset(CatalogModel):
    id: QueryId
    version: Version
    unit: Literal["mCPU", "MiB", "ratio", "events", "pods", "boolean"]
    kind: EntityKind
    delta: bool
    expression: Text

    @model_validator(mode="after")
    def validate_template(self) -> QueryAsset:
        if "__scope__" not in self.expression:
            raise ValueError("query requires approved scope insertion")
        if "__step__" in self.expression and not self.delta:
            raise ValueError("step substitution belongs only to interval counters")
        return self


class QueryCatalog(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    queries: dict[QueryId, QueryFile] = Field(min_length=1)


class RuleInventory(CatalogModel):
    id: PackId
    boundary: Text


class Inventory(CatalogModel):
    rules: list[RuleInventory] = Field(min_length=1)


class PackProvenance(CatalogModel):
    id: PackId
    version: Version
    digest: Digest
    parameters: PackParameters
    queries: list[QueryAsset]


class RenderedQuery(CatalogModel):
    metric: QueryId
    version: Version
    source: Text
    expression: Text
    expression_digest: Digest
    entity_digest: Digest
    step_seconds: int = Field(gt=0, le=300)


class QueryExportManifest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: AssessmentMode
    pack: PackProvenance
    queries: list[RenderedQuery] = Field(min_length=1)
    source_profile: SourceDefinition
    notice: Literal["Query export does not attest source history or authorize a change."] = (
        "Query export does not attest source history or authorize a change."
    )


class SourceDefinition(CatalogModel):
    id: SourceProfileId
    version: Version
    identity: Literal["historical", "name-only"]
    transports: list[SourceKind] = Field(min_length=1)
    labels: dict[str, str]
    query_ids: list[QueryId] = Field(min_length=1)
    characterized_versions: dict[Component, list[ComponentVersion]]
    characterization: Literal["synthetic"]
    joins: Literal["none"]
    limitations: list[Text] = Field(min_length=1)
