from __future__ import annotations

from aks_fleet_efficiency.analysis.efficiency import safe_ratio
from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    Evidence,
    NodePoolSnapshot,
    Recommendation,
    Severity,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment


def assess_pool_review(
    cluster: ClusterSnapshot,
    pool: NodePoolSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    review_ratio: float | None,
) -> RuleAssessment | None:
    if pool.nap_managed or pool.node_count == 0:
        return None
    if review_ratio is None:
        raise ValueError("Pool review ratio is required")
    ratio = safe_ratio(pool.usage_cpu_p95_mcores, pool.allocatable_cpu_mcores)
    if ratio is not None and ratio >= review_ratio:
        return None
    reasons = []
    if ratio is None:
        reasons.append(
            "missing_metric" if pool.usage_cpu_p95_mcores is None else "invalid_capacity"
        )
    if pool.resource_id != f"{cluster.resource_id}/agentPools/{pool.name}":
        reasons.append("missing_identity")
    quality = pool.metric_quality.get("usage_cpu_p95_mcores")
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} {pool.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            category="node-pool-efficiency",
            evidence=[
                Evidence(
                    metric="node_pool_cpu_p95_utilization",
                    value=round(ratio, 4) if ratio is not None else None,
                    unit="ratio",
                    source=quality.source if quality is not None else "unknown",
                ),
                Evidence(
                    metric="node_count", value=pool.node_count, unit="nodes", source="inventory"
                ),
            ],
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
            metadata={
                "node_pool": pool.name,
                "environment": cluster.environment,
                "review_ratio": review_ratio,
            },
        ),
        metrics={"usage_cpu_p95_mcores": (pool.usage_cpu_p95_mcores, "mCPU")},
        reasons=reasons,
        has_signal=ratio is not None and ratio < review_ratio,
    )


POOL_EVALUATORS = {"node-pool-review": assess_pool_review}
