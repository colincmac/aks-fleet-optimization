from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml
from verify import REPLAY_TIME, ROOT, _assessment_arguments

from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
from aks_fleet_efficiency.collection import CollectionPlan
from aks_fleet_efficiency.collectors.fixture import FixtureCollector
from aks_fleet_efficiency.config import load_config, load_onboarding_config
from aks_fleet_efficiency.models import (
    HPA_REPLICA_METRICS,
    KubernetesObjectMetadata,
    MemoryLimitPolicy,
    MemorySafetyPolicy,
    MetricEntity,
    ReplicaSafetyPolicy,
)
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown, render_markdown
from aks_fleet_efficiency.rules.autoscalers import replica_configuration_digest
from aks_fleet_efficiency.rules.engine import analyze
from aks_fleet_efficiency.rules.memory import memory_limit_configuration_digest


def _generate_memory_fixture(examples: Path) -> None:
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/history-assessment.json").read_bytes()
    )
    pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
    pod.spec["containers"] = [
        {
            "name": "api",
            "resources": {
                "requests": {"cpu": "1", "memory": "512Mi"},
                "limits": {"memory": "1Gi"},
            },
        }
    ]
    pod.status["qosClass"] = "Burstable"
    fragments.workload_assessments[0].safety_policy.memory["api"] = MemorySafetyPolicy(
        allow_request_reduction=True,
        minimum_request_mib=128,
        maximum_reduction_ratio=0.5,
        headroom_factor=1.25,
        evidence_reference="synthetic-review/memory",
        startup_peak_mib=240,
        failover_peak_mib=250,
        eviction_events=0,
        qos_class="Burstable",
    )
    metrics = fragments.metrics[0]
    request = next(item for item in metrics.observations if item.metric == "cpu_request")
    for metric, amount in [("memory_request", 512.0), ("memory_limit", 1024.0)]:
        item = request.model_copy(deep=True)
        item.metric = metric
        item.minimum = item.p50 = item.p95 = item.p99 = item.maximum = amount
        item.quality.unit = "MiB"
        item.quality.minimum = item.quality.maximum = amount
        metrics.observations.append(item)
    memory = next(item for item in metrics.observations if item.metric == "cpu_usage").model_copy(
        deep=True
    )
    memory.metric = "memory_usage"
    memory.minimum, memory.p50, memory.p95, memory.p99, memory.maximum = 64, 128, 160, 192, 200
    memory.quality.unit = "MiB"
    memory.quality.minimum, memory.quality.maximum = 64, 200
    restart = next(item for item in metrics.observations if item.metric == "oom_events").model_copy(
        deep=True
    )
    restart.metric = "restarts"
    metrics.observations.extend([memory, restart])
    (examples / "fixtures/memory-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def _generate_autoscaler_fixture(examples: Path) -> None:
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/history-assessment.json").read_bytes()
    )
    metadata = fragments.kubernetes[0]
    key = "autoscaling.k8s.io/v1/verticalpodautoscalers"
    metadata.api_availability[key] = "available"
    metadata.resource_versions[key] = "synthetic-vpa-version"
    metadata.resources.extend(
        [
            KubernetesObjectMetadata(
                api_version="autoscaling/v2",
                kind="HorizontalPodAutoscaler",
                name="synthetic-hpa",
                namespace="synthetic",
                uid="synthetic-hpa-uid",
                spec={
                    "scaleTargetRef": {
                        "apiVersion": "apps/v1",
                        "kind": "StatefulSet",
                        "name": "synthetic",
                    },
                    "minReplicas": 1,
                    "maxReplicas": 5,
                    "metrics": [
                        {
                            "type": "Resource",
                            "resource": {
                                "name": "cpu",
                                "target": {"type": "Utilization", "averageUtilization": 75},
                            },
                        }
                    ],
                },
            ),
            KubernetesObjectMetadata(
                api_version="autoscaling.k8s.io/v1",
                kind="VerticalPodAutoscaler",
                name="synthetic-vpa",
                namespace="synthetic",
                uid="synthetic-vpa-uid",
                spec={
                    "targetRef": {
                        "apiVersion": "apps/v1",
                        "kind": "StatefulSet",
                        "name": "synthetic",
                    },
                    "updatePolicy": {"updateMode": "Recreate"},
                    "resourcePolicy": {
                        "containerPolicies": [
                            {
                                "containerName": "*",
                                "mode": "Auto",
                                "controlledResources": ["cpu", "memory"],
                                "controlledValues": "RequestsOnly",
                            }
                        ]
                    },
                },
            ),
        ]
    )
    (examples / "fixtures/autoscalers-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def _generate_hpa_history_fixture(examples: Path) -> None:
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/autoscalers-assessment.json").read_bytes()
    )
    metadata = fragments.kubernetes[0]
    hpa = next(item for item in metadata.resources if item.kind == "HorizontalPodAutoscaler")
    hpa.status = {"currentReplicas": 1, "desiredReplicas": 1}
    metadata.resources = [
        item for item in metadata.resources if item.kind != "VerticalPodAutoscaler"
    ]
    vpa_key = "autoscaling.k8s.io/v1/verticalpodautoscalers"
    metadata.api_availability[vpa_key] = "absent"
    metadata.resource_versions.pop(vpa_key, None)
    binding = fragments.workload_assessments[0]
    binding.hpa_uid = hpa.uid
    binding.history_reference = "synthetic-approved-hpa-history/reference"
    metrics = fragments.metrics[0]
    presence = next(item for item in metrics.observations if item.metric == "hpa_present")
    presence.minimum = presence.p50 = presence.p95 = presence.p99 = presence.maximum = 1.0
    presence.quality.minimum = presence.quality.maximum = 1.0
    template = next(item for item in metrics.observations if item.metric == "desired_replicas")
    entity = MetricEntity(
        kind="hpa",
        cluster_resource_id=binding.cluster_resource_id,
        namespace=binding.namespace,
        workload_kind=binding.workload_kind,
        workload=binding.workload,
        workload_uid=binding.workload_uid,
        hpa_uid=binding.hpa_uid,
    )
    for metric, count in zip(HPA_REPLICA_METRICS, [1.0, 5.0, 1.0, 1.0], strict=True):
        item = template.model_copy(deep=True)
        item.entity = entity
        item.metric = metric
        item.minimum = item.p50 = item.p95 = item.p99 = item.maximum = count
        item.quality.minimum = item.quality.maximum = count
        metrics.observations.append(item)
    (examples / "fixtures/hpa-history-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def _generate_completion_fixtures(examples: Path) -> None:
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/autoscalers-assessment.json").read_bytes()
    )
    metadata = fragments.kubernetes[0]
    vpa = next(item for item in metadata.resources if item.kind == "VerticalPodAutoscaler")
    policies = vpa.spec["resourcePolicy"]
    if not isinstance(policies, dict) or not isinstance(policies["containerPolicies"], list):
        raise ValueError("synthetic VPA policies must be explicit")
    policy = policies["containerPolicies"][0]
    if not isinstance(policy, dict):
        raise ValueError("synthetic VPA container policy must be explicit")
    policy.update(
        minAllowed={"cpu": "100m", "memory": "128Mi"}, maxAllowed={"cpu": "1", "memory": "1Gi"}
    )
    vpa.status = {
        "recommendation": {
            "containerRecommendations": [
                {
                    "containerName": "api",
                    "target": {"cpu": "500m", "memory": "512Mi"},
                    "lowerBound": {"cpu": "200m", "memory": "256Mi"},
                    "upperBound": {"cpu": "800m", "memory": "768Mi"},
                    "uncappedTarget": {"cpu": "1200m", "memory": "512Mi"},
                }
            ]
        }
    }
    (examples / "fixtures/vpa-bounds-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    hpa = next(item for item in metadata.resources if item.kind == "HorizontalPodAutoscaler")
    hpa.owner_references = [
        {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "controller": True,
            "uid": "synthetic-keda-uid",
            "name": "synthetic-keda",
        }
    ]
    metadata.api_availability["keda.sh/v1alpha1/scaledobjects"] = "available"
    metadata.resource_versions["keda.sh/v1alpha1/scaledobjects"] = "synthetic-keda-version"
    metadata.resources.append(
        KubernetesObjectMetadata(
            api_version="keda.sh/v1alpha1",
            kind="ScaledObject",
            name="synthetic-keda",
            namespace="synthetic",
            uid="synthetic-keda-uid",
            spec={
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "StatefulSet",
                    "name": "synthetic",
                },
                "minReplicaCount": 0,
                "maxReplicaCount": 5,
                "pollingInterval": 30,
                "cooldownPeriod": 300,
                "triggers": [{"type": "prometheus", "metricType": "AverageValue"}],
            },
            status={"hpaName": "synthetic-hpa"},
        )
    )
    (examples / "fixtures/keda-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/hpa-history-assessment.json").read_bytes()
    )
    metadata = fragments.kubernetes[0]
    workload = next(item for item in metadata.resources if item.kind == "StatefulSet")
    workload.kind = "Deployment"
    workload.spec["replicas"] = 2
    workload.status = {"replicas": 2, "availableReplicas": 2}
    metadata.api_availability["apps/v1/deployments"] = "available"
    metadata.resource_versions["apps/v1/deployments"] = "synthetic-deployment-version"
    pod = next(item for item in metadata.resources if item.kind == "Pod")
    pod.owner_references[0]["kind"] = "Deployment"
    extra = pod.model_copy(deep=True)
    extra.uid, extra.name = "synthetic-extra-pod-uid", "synthetic-extra-pod"
    metadata.resources.append(extra)
    metadata.workload_bindings[extra.uid] = workload.uid
    hpa = next(item for item in metadata.resources if item.kind == "HorizontalPodAutoscaler")
    hpa.spec["scaleTargetRef"] = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "name": workload.name,
    }
    hpa.spec["minReplicas"] = 2
    hpa.status = {"currentReplicas": 2, "desiredReplicas": 2}
    binding = fragments.workload_assessments[0]
    binding.workload_kind = "Deployment"
    binding.pod_uids.append(extra.uid)
    binding.safety_policy.replicas = ReplicaSafetyPolicy(
        allow_floor_reduction=True,
        hpa_uid=hpa.uid,
        minimum_available_replicas=1,
        tested_replicas=1,
        maximum_reduction_ratio=0.5,
        failover_reserve_replicas=0,
        maximum_unavailable_replicas=0,
        peak_load_reviewed=True,
        startup_reviewed=True,
        throughput_reviewed=True,
        zone_failure_reviewed=True,
        reliability_reviewed=True,
        oom_events=0,
        restart_events=0,
        eviction_events=0,
        evidence_reference="synthetic-owner-reviewed-replica-canary",
    )
    metrics = fragments.metrics[0]
    for item in metrics.observations:
        item.entity = MetricEntity.model_validate(
            {**item.entity.model_dump(), "workload_kind": "Deployment"}
        )
        if item.metric in {
            "desired_replicas",
            "available_replicas",
            "hpa_min_replicas",
            "hpa_desired_replicas",
            "hpa_current_replicas",
        }:
            item.minimum = item.p50 = item.p95 = item.p99 = item.maximum = 2.0
            item.quality.minimum = item.quality.maximum = 2.0
    observed = next(
        item for item in metrics.observations if item.metric == "desired_replicas"
    ).model_copy(deep=True)
    observed.metric = "observed_replicas"
    metrics.observations.append(observed)
    result = assess_fragments(
        fragments,
        load_onboarding_config(examples / "pool-assessment-config.yaml"),
        as_of=datetime.fromisoformat(REPLAY_TIME),
    )
    binding.safety_policy.replicas.configuration_digest = replica_configuration_digest(
        result.snapshot.clusters[0].workloads[0]
    )
    (examples / "fixtures/replica-floor-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def _generate_memory_completion(examples: Path) -> None:
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/memory-assessment.json").read_bytes()
    )
    fragments.kubernetes[0].api_availability["v1/limitranges"] = "available"
    fragments.kubernetes[0].resource_versions["v1/limitranges"] = "synthetic-limits-version"
    metrics = fragments.metrics[0]
    eviction = next(
        item for item in metrics.observations if item.metric == "oom_events"
    ).model_copy(deep=True)
    eviction.metric = "evictions"
    eviction.entity = next(
        item for item in metrics.observations if item.metric == "desired_replicas"
    ).entity
    metrics.observations.append(eviction)
    envelope = fragments.model_copy(deep=True)
    metadata = envelope.kubernetes[0]
    workload = next(item for item in metadata.resources if item.kind == "StatefulSet")
    workload.spec["replicas"] = 2
    pod = next(item for item in metadata.resources if item.kind == "Pod")
    extra = pod.model_copy(deep=True)
    extra.uid, extra.name = "synthetic-memory-extra-pod", "synthetic-memory-extra"
    metadata.resources.append(extra)
    metadata.workload_bindings[extra.uid] = workload.uid
    binding = envelope.workload_assessments[0]
    binding.pod_uids.extend([extra.uid, "synthetic-deleted-memory-pod"])
    keys = {
        "cpu_usage": ["replica_cpu_envelope"],
        "cpu_request": ["replica_cpu_request_min", "replica_cpu_request_max"],
        "cpu_throttling": ["replica_cpu_throttling"],
        "oom_events": ["replica_oom_events"],
        "memory_usage": ["replica_memory_envelope"],
        "memory_request": ["replica_memory_request_min", "replica_memory_request_max"],
        "memory_limit": ["replica_memory_limit_min", "replica_memory_limit_max"],
        "restarts": ["replica_restarts"],
    }
    observations = []
    for original in envelope.metrics[0].observations:
        for name in keys.get(original.metric, [original.metric]):
            item = original.model_copy(deep=True)
            item.metric = name
            if item.entity.kind == "container":
                item.entity = MetricEntity.model_validate(
                    {
                        **item.entity.model_dump(),
                        "kind": "workload_container",
                        "pod_uid": None,
                        "membership_digest": binding.membership_digest,
                    }
                )
            elif name in {"desired_replicas", "available_replicas"}:
                item.minimum = item.p50 = item.p95 = item.p99 = item.maximum = 2.0
                item.quality.minimum = item.quality.maximum = 2.0
            observations.append(item)
    observed = next(item for item in observations if item.metric == "desired_replicas").model_copy(
        deep=True
    )
    observed.metric = "observed_replicas"
    observations.append(observed)
    envelope.metrics[0].observations = observations
    (examples / "fixtures/memory-envelope-assessment.json").write_text(
        envelope.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    limit_fragments = fragments.model_copy(deep=True)
    total = next(
        item for item in limit_fragments.metrics[0].observations if item.metric == "memory_usage"
    ).model_copy(deep=True)
    total.metric = "memory_total_usage"
    total.minimum, total.p50, total.p95, total.p99, total.maximum = 128, 256, 320, 384, 400
    total.quality.minimum, total.quality.maximum = 128, 400
    limit_fragments.metrics[0].observations.append(total)
    safety = limit_fragments.workload_assessments[0].safety_policy
    safety.memory["api"].allow_request_reduction = False
    limit_policy = MemoryLimitPolicy(
        allow_limit_reduction=True,
        minimum_limit_mib=512,
        maximum_reduction_ratio=0.5,
        headroom_factor=1.25,
        startup_total_peak_mib=448,
        failover_total_peak_mib=480,
        allocator_cache_reviewed=True,
        evidence_reference="synthetic-total-memory-review",
    )
    safety.memory_limits["api"] = limit_policy
    result = assess_fragments(
        limit_fragments,
        load_onboarding_config(examples / "pool-assessment-config.yaml"),
        as_of=datetime.fromisoformat(REPLAY_TIME),
    )
    limit_policy.configuration_digest = memory_limit_configuration_digest(
        result.snapshot.clusters[0].workloads[0]
    )
    (examples / "fixtures/memory-limit-assessment.json").write_text(
        limit_fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
    pod.spec["initContainers"] = [
        {
            "name": "sidecar-a",
            "restartPolicy": "Always",
            "resources": {"requests": {"memory": "128Mi"}},
        },
        {"name": "initialize", "resources": {"requests": {"memory": "1Gi"}}},
        {
            "name": "sidecar-b",
            "restartPolicy": "Always",
            "resources": {"requests": {"memory": "64Mi"}},
        },
    ]
    pod.spec["overhead"] = {"memory": "32Mi"}
    pod.status["containerStatuses"] = [
        {
            "name": "api",
            "lastState": {
                "terminated": {
                    "reason": "Error",
                    "exitCode": 137,
                    "finishedAt": "2026-10-28T23:55:00Z",
                }
            },
        }
    ]
    eviction.maximum = eviction.total = eviction.quality.maximum = 2.0
    (examples / "fixtures/memory-context-assessment.json").write_text(
        fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def generate_examples() -> None:
    examples = ROOT / "examples"
    _generate_memory_fixture(examples)
    _generate_autoscaler_fixture(examples)
    _generate_hpa_history_fixture(examples)
    _generate_completion_fixtures(examples)
    _generate_memory_completion(examples)
    ordinary = AssessmentFragments.model_validate_json(
        (examples / "fixtures" / "history-assessment.json").read_bytes()
    )
    ordinary.workload_assessments = []
    source_profile = load_onboarding_config(examples / "ordinary-source-config.yaml")
    from aks_fleet_efficiency.catalog import load_catalog

    ordinary.metrics[0].source_profile = load_catalog().source("cadvisor-ksm")
    ordinary.metrics[0].observations = [
        item
        for item in ordinary.metrics[0].observations
        if item.metric in {"cpu_usage", "cpu_request"}
    ]
    for observation in ordinary.metrics[0].observations:
        observation.entity = MetricEntity(
            kind="unresolved_container",
            cluster_resource_id=observation.entity.cluster_resource_id,
            namespace="synthetic",
            pod="synthetic-pod",
            container="api",
        )
    (examples / "fixtures" / "ordinary-source-assessment.json").write_text(
        ordinary.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    source_profile.metric_sources[0].type = "azure-managed-prometheus"
    source_profile.metric_sources[0].authentication = "default-azure-credential"
    managed = source_profile.model_dump(mode="json")
    managed["metric_sources"][0]["endpoint"] = "https://synthetic.prometheus.monitor.azure.com"
    (examples / "managed-source-config.yaml").write_text(
        yaml.safe_dump(managed, sort_keys=False), encoding="utf-8"
    )
    (examples / "ordinary-source-entities.json").write_text(
        json.dumps([ordinary.metrics[0].observations[0].entity.model_dump(mode="json")], indent=2)
        + "\n",
        encoding="utf-8",
    )
    as_of = datetime.fromisoformat(REPLAY_TIME)
    review_fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures" / "history-assessment.json").read_bytes()
    )
    review_snapshot = assess_fragments(
        review_fragments,
        load_onboarding_config(examples / "pool-assessment-config.yaml"),
        as_of=as_of,
    ).snapshot
    review_snapshot.source_capabilities = []
    placement = review_fragments.model_copy(deep=True)
    pod = next(item for item in placement.kubernetes[0].resources if item.kind == "Pod")
    pod.spec.update(
        nodeSelector={"kubernetes.io/os": "linux"},
        affinity={
            "podAntiAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": [
                    {"topologyKey": "topology.kubernetes.io/zone"}
                ]
            }
        },
        topologySpreadConstraints=[
            {
                "maxSkew": 1,
                "topologyKey": "topology.kubernetes.io/zone",
                "whenUnsatisfiable": "DoNotSchedule",
            }
        ],
        tolerations=[{"key": "synthetic-dedicated", "operator": "Exists", "effect": "NoSchedule"}],
        volumes=[{"name": "synthetic-data", "persistentVolumeClaim": {"claimName": "synthetic"}}],
        priorityClassName="synthetic-priority",
    )
    from aks_fleet_efficiency.models import PoolIntentBinding

    inventory = placement.azure[0].clusters[0]
    placement.pool_intents = [
        PoolIntentBinding(
            cluster_resource_id=inventory.resource_id,
            pool_resource_id=inventory.node_pools[0].resource_id,
            owner="synthetic-owner",
            classification="intentionally-reserved",
            reference="synthetic-review/failover",
        )
    ]
    (examples / "fixtures" / "placement-assessment.json").write_text(
        placement.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    placement_snapshot = assess_fragments(
        placement,
        load_onboarding_config(examples / "pool-assessment-config.yaml"),
        as_of=as_of,
    ).snapshot
    placement_snapshot.source_capabilities = []
    from aks_fleet_efficiency.config import AdvisorConfig

    for case, pack_id in [
        ("scheduling-review", "AKS-SCHED-001"),
        ("capacity-review", "AKS-NP-002"),
    ]:
        (examples / "fixtures" / f"{case}-snapshot.json").write_text(
            placement_snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        report = analyze(placement_snapshot, AdvisorConfig(packs=[pack_id]), as_of=as_of)
        if len(report.recommendations) != 1:
            raise RuntimeError(f"Synthetic {case} must produce exactly one investigation")
        (examples / f"expected-{case}.md").write_text(
            render_markdown(report) + "\n", encoding="utf-8"
        )
    missing = review_snapshot.model_copy(deep=True)
    missing.clusters[0].workloads[0].containers[0].resources.request_cpu_mcores = None
    (examples / "fixtures" / "missing-request-snapshot.json").write_text(
        missing.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    risk = review_snapshot.model_copy(deep=True)
    resources = risk.clusters[0].workloads[0].containers[0].resources
    resources.usage_cpu_p95_mcores = 1100
    resources.usage_cpu_p99_mcores = 1200
    for name in ["usage_cpu_p95_mcores", "usage_cpu_p99_mcores"]:
        resources.metric_quality[name].maximum = 1500
    (examples / "fixtures" / "request-risk-snapshot.json").write_text(
        risk.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    fixed_fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures" / "replica-floor-assessment.json").read_bytes()
    )
    metadata = fixed_fragments.kubernetes[0]
    metadata.resources = [
        item for item in metadata.resources if item.kind != "HorizontalPodAutoscaler"
    ]
    hpa_api = "autoscaling/v2/horizontalpodautoscalers"
    metadata.api_availability[hpa_api] = "absent"
    metadata.resource_versions.pop(hpa_api, None)
    binding = fixed_fragments.workload_assessments[0]
    binding.hpa_uid = None
    binding.history_reference = "synthetic-fixed-replica-history/reference"
    binding.safety_policy.replicas = None
    fixed_fragments.metrics[0].observations = [
        item for item in fixed_fragments.metrics[0].observations if item.entity.kind != "hpa"
    ]
    presence = next(
        item for item in fixed_fragments.metrics[0].observations if item.metric == "hpa_present"
    )
    presence.minimum = presence.p50 = presence.p95 = presence.p99 = presence.maximum = 0
    presence.quality.minimum = presence.quality.maximum = 0
    (examples / "fixtures" / "fixed-replica-assessment.json").write_text(
        fixed_fragments.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    for case, base, pack_id in [
        ("fixed-replica-pack", "fixed-replica", "AKS-AS-001"),
        ("interaction-pack", "autoscalers", "AKS-AS-002"),
        ("hpa-pinning-pack", "hpa-history", "AKS-AS-003"),
        ("keda-pack", "keda", "AKS-AS-004"),
        ("hpa-floor-pack", "replica-floor", "AKS-AS-005"),
        ("hpa-change-pack", "hpa-history", "AKS-AS-006"),
        ("vpa-bounds-pack", "vpa-bounds", "AKS-AS-007"),
    ]:
        fragments = AssessmentFragments.model_validate_json(
            (examples / "fixtures" / f"{base}-assessment.json").read_bytes()
        )
        snapshot = assess_fragments(
            fragments,
            load_onboarding_config(examples / "pool-assessment-config.yaml"),
            as_of=as_of,
        ).snapshot
        snapshot.source_capabilities = []
        if case == "fixed-replica-pack":
            workload = snapshot.clusters[0].workloads[0]
            configuration = workload.autoscaler_configuration
            assert (
                configuration is not None
                and configuration.hpa_observed
                and configuration.keda_observed
                and not configuration.hpas
                and not configuration.kedas
            )
            workload.autoscaling.hpa = False
            workload.autoscaling.keda = False
        if case == "hpa-change-pack":
            hpa_history = snapshot.clusters[0].workloads[0].hpa_replica_history
            assert hpa_history is not None
            hpa_history.metrics["hpa_max_replicas"].minimum = 2
            hpa_history.metrics["hpa_max_replicas"].quality.minimum = 2
        (examples / "fixtures" / f"{case}-snapshot.json").write_text(
            snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        report = analyze(snapshot, AdvisorConfig(mode="guarded", packs=[pack_id]), as_of=as_of)
        if len(report.recommendations) != 1 or report.recommendations[0].rule_id != pack_id:
            raise RuntimeError(
                f"Synthetic {case} fixture must produce its selected {pack_id} finding"
            )
        (examples / f"expected-{case}.md").write_text(
            render_markdown(report) + "\n", encoding="utf-8"
        )
    floor_fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures" / "replica-floor-assessment.json").read_bytes()
    )
    (examples / "autoscaler-pack-entities.json").write_text(
        json.dumps(
            [
                item.entity.model_dump(mode="json")
                for item in floor_fragments.metrics[0].observations
                if item.metric in {"hpa_min_replicas", "desired_replicas"}
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for case, base, pack_id in [
        ("oom-pack", "memory", "AKS-MEM-001"),
        ("memory-safety-pack", "memory", "AKS-MEM-002"),
        ("memory-request-pack", "memory-envelope", "AKS-MEM-003"),
        ("pod-memory-pack", "memory-context", "AKS-MEM-004"),
        ("memory-limit-pack", "memory-limit", "AKS-MEM-005"),
        ("restart-pack", "memory", "AKS-REL-001"),
        ("termination-pack", "memory-context", "AKS-REL-002"),
        ("eviction-pack", "memory-context", "AKS-REL-003"),
    ]:
        fragments = AssessmentFragments.model_validate_json(
            (examples / "fixtures" / f"{base}-assessment.json").read_bytes()
        )
        snapshot = assess_fragments(
            fragments,
            load_onboarding_config(examples / "pool-assessment-config.yaml"),
            as_of=as_of,
        ).snapshot
        snapshot.source_capabilities = []
        resources = snapshot.clusters[0].workloads[0].containers[0].resources
        if case in {"oom-pack", "restart-pack"}:
            field = "memory_oom_events" if case == "oom-pack" else "restart_events"
            setattr(resources, field, 1)
            resources.metric_quality[field].maximum = 1
        (examples / "fixtures" / f"{case}-snapshot.json").write_text(
            snapshot.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        report = analyze(snapshot, AdvisorConfig(mode="guarded", packs=[pack_id]), as_of=as_of)
        (examples / f"expected-{case}.md").write_text(
            render_markdown(report) + "\n",
            encoding="utf-8",
        )
    for name, snapshot, pack_id in [
        ("missing-request", missing, "AKS-RQ-001"),
        ("request-risk", risk, "AKS-RQ-003"),
    ]:
        review = analyze(snapshot, AdvisorConfig(packs=[pack_id]), as_of=as_of)
        (examples / f"expected-{name}.md").write_text(
            render_markdown(review) + "\n", encoding="utf-8"
        )
    pool_fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures" / "pool-assessment.json").read_bytes()
    )
    pool_profile = load_onboarding_config(examples / "pool-assessment-config.yaml")
    pool_profile.analysis.packs = ["AKS-NP-001"]
    pool_profile.analysis.mode = "baseline"
    pool_review = assess_fragments(pool_fragments, pool_profile, as_of=as_of)
    (examples / "fixtures" / "pool-review-snapshot.json").write_text(
        pool_review.snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (examples / "expected-pool-review.md").write_text(
        render_markdown(pool_review.report) + "\n", encoding="utf-8"
    )
    (examples / "pool-pack-entities.json").write_text(
        json.dumps(
            [
                item.entity.model_dump(mode="json")
                for item in pool_fragments.metrics[0].observations
                if item.metric == "node_cpu_usage"
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = analyze(
        FixtureCollector(examples / "fixtures/fleet-snapshot.json").collect(),
        load_config(examples / "advisor-config.yaml"),
        as_of=as_of,
    )
    (examples / "expected-report.md").write_text(
        render_markdown(report).rstrip("\n") + "\n", encoding="utf-8"
    )
    for case in [
        "positive",
        "partial",
        "workload",
        "history",
        "scoped",
        "azure",
        "replicas",
        "memory",
        "autoscalers",
        "hpa-history",
        "keda",
        "replica-floor",
        "vpa-bounds",
        "memory-envelope",
        "memory-limit",
        "memory-context",
        "cpu-pack-baseline",
        "cpu-pack-guarded",
        "source-ordinary",
        "source-managed",
    ]:
        arguments = _assessment_arguments(case, "markdown")
        fragments = AssessmentFragments.model_validate_json(Path(arguments[2]).read_bytes())
        profile = load_onboarding_config(Path(arguments[4]))
        if case in {"cpu-pack-baseline", "cpu-pack-guarded"}:
            profile.analysis.mode = "guarded" if case.endswith("guarded") else "baseline"
        result = assess_fragments(fragments, profile, as_of=as_of)
        name = (
            f"expected-pool-{case}.md" if case in {"positive", "partial"} else f"expected-{case}.md"
        )
        (examples / name).write_text(render_assessment_markdown(result) + "\n", encoding="utf-8")
    history = AssessmentFragments.model_validate_json(
        (examples / "fixtures/history-assessment.json").read_bytes()
    )
    (examples / "cpu-pack-entities.json").write_text(
        json.dumps([history.metrics[0].observations[0].entity.model_dump(mode="json")], indent=2)
        + "\n",
        encoding="utf-8",
    )
    fragments = AssessmentFragments.model_validate_json(
        (examples / "fixtures/workload-assessment.json").read_bytes()
    )
    metadata = fragments.kubernetes[0]
    (examples / "fixtures/kubernetes-export.json").write_text(
        metadata.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    plan = CollectionPlan.model_validate(
        {
            "window_start": fragments.window_start,
            "window_end": fragments.window_end,
            "clusters": [
                {
                    "resource_id": metadata.cluster_resource_id,
                    "expected_cluster_uid": metadata.cluster_uid,
                    "metadata_export": "fixtures/kubernetes-export.json",
                }
            ],
        }
    )
    (examples / "collection-plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    generate_examples()
