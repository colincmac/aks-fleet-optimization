from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import yaml
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from aks_fleet_efficiency.catalog.models import (
    AssessmentMode,
    Component,
    ComponentVersion,
    Digest,
    PackId,
    PackParameters,
    SourceProfileId,
    validate_parameters,
)


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    minimum_coverage_ratio: float = Field(default=0.85, ge=0, le=1)
    minimum_observation_days: int = Field(default=30, ge=1)
    maximum_evidence_age_hours: float = Field(default=24, gt=0)
    maximum_metric_step_seconds: int = Field(default=300, gt=0)
    minimum_replicas_for_autoscaling_review: int = Field(default=2, ge=1)


class AdvisorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AssessmentMode = "baseline"
    packs: Annotated[list[PackId], Field(min_length=1)] | None = None
    pack_parameters: dict[PackId, PackParameters] = Field(default_factory=dict)
    pack_locks: dict[PackId, Digest] = Field(default_factory=dict)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    excluded_namespaces: list[str] = Field(
        default_factory=lambda: ["kube-system", "gatekeeper-system"]
    )
    environment_risk: dict[str, str] = Field(
        default_factory=lambda: {"production": "high", "nonproduction": "medium"}
    )
    enable_estimated_savings: bool = False

    @model_validator(mode="after")
    def validate_pack_selection(self) -> AdvisorConfig:
        from aks_fleet_efficiency.catalog import load_catalog

        catalog = load_catalog()
        if self.packs is not None and len(set(self.packs)) != len(self.packs):
            raise ValueError("pack selection must be distinct")
        selected = set(self.packs if self.packs is not None else catalog.manifests)
        for name in selected | set(self.pack_parameters) | set(self.pack_locks):
            catalog.pack(name)
        for name, parameters in self.pack_parameters.items():
            validate_parameters(catalog.pack(name).evaluator, parameters)
        if not set(self.pack_parameters) <= selected or not set(self.pack_locks) <= selected:
            raise ValueError("pack parameters and locks must belong to selected packs")
        if self.pack_locks and self.pack_locks != {
            name: catalog.provenance(name).digest for name in selected
        }:
            raise ValueError("Assessment pack lock does not match installed pack/query assets")
        return self


def load_config(path: Path | None) -> AdvisorConfig:
    if path is None:
        return AdvisorConfig()
    with path.open(encoding="utf-8") as handle:
        return AdvisorConfig.model_validate(yaml.safe_load(handle) or {})


ProfileName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")]
LabelName = Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")]
DeclaredValue = Annotated[str, Field(min_length=1, pattern=r"\S")]


def _cluster_subscription(resource_id: str) -> UUID:
    match = re.fullmatch(
        r"/subscriptions/([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})/"
        r"resourceGroups/[^/]+/providers/Microsoft.ContainerService/managedClusters/[^/]+",
        resource_id,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError("an exact AKS managed-cluster resource ID is required")
    return UUID(match.group(1))


class OnboardingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)


class AssessmentScope(OnboardingModel):
    tenant_id: UUID
    subscription_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_allowlist(self) -> AssessmentScope:
        if len(set(self.subscription_ids)) != len(self.subscription_ids):
            raise ValueError("subscription allowlist must not contain duplicates")
        return self


class MetricSourceProfile(OnboardingModel):
    name: ProfileName
    type: Literal["prometheus", "azure-managed-prometheus"]
    endpoint: AnyHttpUrl
    authentication: Literal["anonymous", "default-azure-credential", "bearer-environment"]
    catalog_profile: SourceProfileId = "identity-enriched"
    component_versions: dict[Component, ComponentVersion] = Field(default_factory=dict)
    token_environment_variable: Annotated[str, Field(pattern=r"^[A-Z_][A-Z0-9_]*$")] | None = None
    label_mapping: dict[
        Literal[
            "cluster_resource_id", "namespace", "workload", "workload_kind", "container", "pod"
        ],
        LabelName,
    ] = Field(default_factory=dict)
    declared_retention_days: int | None = Field(default=None, gt=0)
    declared_step_seconds: int | None = Field(default=None, gt=0)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or any(
            component is not None
            for component in [value.username, value.password, value.query, value.fragment]
        ):
            raise ValueError("use HTTPS without credentials, query parameters, or fragments")
        return value

    @model_validator(mode="after")
    def validate_authentication(self) -> MetricSourceProfile:
        if self.type == "azure-managed-prometheus":
            if self.authentication != "default-azure-credential":
                raise ValueError("managed Prometheus requires the Azure credential profile")
        elif self.authentication == "default-azure-credential":
            raise ValueError(
                "generic Prometheus requires an explicit supported authentication profile"
            )
        if (self.authentication == "bearer-environment") != (
            self.token_environment_variable is not None
        ):
            raise ValueError("bearer authentication requires an environment-variable name only")
        return self


class ClusterTarget(OnboardingModel):
    resource_id: str
    metric_source: ProfileName | None = None
    environment: DeclaredValue | None = None

    @property
    def subscription_id(self) -> UUID:
        return _cluster_subscription(self.resource_id)

    @field_validator("resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        _cluster_subscription(value)
        return value


class OwnershipMapping(OnboardingModel):
    cluster_resource_id: str
    namespace: Annotated[str, Field(max_length=63, pattern=r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")]
    owner: DeclaredValue
    policy_reference: DeclaredValue | None = None

    @field_validator("cluster_resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        _cluster_subscription(value)
        return value


class OnboardingConfig(OnboardingModel):
    schema_version: Literal["1.0"] = "1.0"
    scope: AssessmentScope
    metric_sources: list[MetricSourceProfile] = Field(default_factory=list)
    clusters: list[ClusterTarget] = Field(default_factory=list)
    ownership: list[OwnershipMapping] = Field(default_factory=list)
    report_directory: Path
    analysis: AdvisorConfig = Field(default_factory=AdvisorConfig)

    @field_validator("report_directory", mode="before")
    @classmethod
    def validate_report_directory(cls, value: object) -> object:
        if isinstance(value, str) and (not value.strip() or "://" in value):
            raise ValueError("report directory must be a nonempty local filesystem path")
        return value

    @model_validator(mode="after")
    def validate_references(self) -> OnboardingConfig:
        sources = {source.name for source in self.metric_sources}
        if len(sources) != len(self.metric_sources):
            raise ValueError("metric source names must be unique")
        clusters = {cluster.resource_id.casefold() for cluster in self.clusters}
        if len(clusters) != len(self.clusters):
            raise ValueError("cluster targets must be unique")
        for cluster in self.clusters:
            if _cluster_subscription(cluster.resource_id) not in self.scope.subscription_ids:
                raise ValueError("cluster target is outside the subscription allowlist")
            if cluster.metric_source is not None and cluster.metric_source not in sources:
                raise ValueError("cluster target references an unknown metric source")
        owners: set[tuple[str, str]] = set()
        for mapping in self.ownership:
            if (
                _cluster_subscription(mapping.cluster_resource_id)
                not in self.scope.subscription_ids
            ):
                raise ValueError("ownership mapping is outside the subscription allowlist")
            if clusters and mapping.cluster_resource_id not in {
                cluster.resource_id for cluster in self.clusters
            }:
                raise ValueError("ownership mapping is outside the exact cluster targets")
            key = (mapping.cluster_resource_id.casefold(), mapping.namespace)
            if key in owners:
                raise ValueError("ownership mapping is ambiguous")
            owners.add(key)
        return self


def load_onboarding_config(path: Path) -> OnboardingConfig:
    with path.open(encoding="utf-8") as handle:
        profile = OnboardingConfig.model_validate(yaml.safe_load(handle) or {})
    if not profile.report_directory.is_absolute():
        profile.report_directory = (path.parent / profile.report_directory).absolute()
    return profile
