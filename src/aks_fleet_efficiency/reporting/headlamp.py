"""Publish approved saved advisor assessments for the read-only Headlamp dashboard."""

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from uuid import UUID

from aks_fleet_efficiency.assessment import OfflineAssessment
from aks_fleet_efficiency.history import read_assessment_artifacts
from aks_fleet_efficiency.models import BlockedRecommendation, Recommendation
from aks_fleet_efficiency.rules.engine import analyze

MAX_BYTES = 4 * 1024 * 1024
MAX_CLUSTERS = 32


def _comparisons(finding: Recommendation) -> list[dict[str, object]]:
    requests, proposed = finding.current_requests, finding.proposed_requests
    limits, proposed_limits = finding.current_limits, finding.proposed_limits
    dimensions = (
        (
            "CPU request",
            requests.cpu_mcores if requests else None,
            proposed.cpu_mcores if proposed else None,
            "mCPU",
        ),
        (
            "Memory request",
            requests.memory_mib if requests else None,
            proposed.memory_mib if proposed else None,
            "MiB",
        ),
        (
            "Memory limit",
            limits.memory_mib if limits else None,
            proposed_limits.memory_mib if proposed_limits else None,
            "MiB",
        ),
        ("HPA minimum", finding.current_replica_floor, finding.proposed_replica_floor, "replicas"),
    )
    return [
        {"dimension": dimension, "current": current, "proposed": target, "unit": unit}
        for dimension, current, target, unit in dimensions
        if target is not None
    ]


def _finding(finding: Recommendation | BlockedRecommendation) -> dict[str, object]:
    scope = {
        "id": finding.id,
        "rule": finding.rule_id,
        "version": finding.rule_version,
        "namespace": finding.namespace,
        "workload": finding.workload,
    }
    if isinstance(finding, BlockedRecommendation):
        return {**scope, "state": "blocked", "reasons": finding.reason_codes}
    return {
        **scope,
        "state": "finding",
        "title": finding.title,
        "summary": finding.summary,
        "category": finding.category,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "evidence": [
            {"metric": item.metric, "value": item.value, "unit": item.unit}
            for item in finding.evidence
        ],
        "comparisons": _comparisons(finding),
        "checks": list(dict.fromkeys([*finding.prerequisites, *finding.validation_steps])),
        "risks": finding.risks,
    }


def _project(assessment: OfflineAssessment, tenant: UUID) -> dict[str, object]:
    manifest = assessment.snapshot.collection_manifest
    report = assessment.report
    if (
        manifest is None
        or UUID(manifest.tenant_id) != tenant
        or len(assessment.snapshot.clusters) != 1
    ):
        raise ValueError("requires one cluster and the approved tenant")
    cluster = assessment.snapshot.clusters[0]
    if not cluster.uid or report.observation_window.end > report.generated_at:
        raise ValueError("missing fingerprint or invalid report clock")
    findings: list[Recommendation | BlockedRecommendation] = list(report.recommendations)
    findings.extend(report.blocked_recommendations)
    if any(finding.resource_id != cluster.resource_id for finding in findings):
        raise ValueError("finding outside the assessment cluster")

    namespaces: dict[str, list[dict[str, str]]] = defaultdict(list)
    unbound = 0
    seen_uids: set[str] = set()
    for workload in sorted(
        cluster.workloads, key=lambda item: (item.namespace, item.name, item.uid or "")
    ):
        rows = namespaces[workload.namespace]
        if not workload.uid:
            unbound += 1
            continue
        if workload.uid in seen_uids:
            raise ValueError("duplicate workload identity")
        seen_uids.add(workload.uid)
        rows.append({"uid": workload.uid, "name": workload.name, "kind": workload.kind})
    return {
        "id": cluster.resource_id,
        "uid": cluster.uid,
        "name": cluster.name,
        "status": assessment.status,
        "mode": report.mode,
        "evaluatedAt": report.generated_at.isoformat(),
        "windowStart": report.observation_window.start.isoformat(),
        "windowEnd": report.observation_window.end.isoformat(),
        "namespaces": [{"name": name, "workloads": rows} for name, rows in namespaces.items()],
        "unboundWorkloads": unbound,
        "issues": sorted({issue.code for issue in assessment.issues}),
        "findings": [_finding(finding) for finding in findings],
    }


def publish(directories: list[Path], tenant: UUID, output: Path) -> None:
    target = output.resolve()
    if output.is_symlink() or any(target.is_relative_to(path.resolve()) for path in directories):
        raise ValueError("feed output must be separate from original bundles and not a symlink")
    replace_feed_file(target, render_feed(directories, tenant))


def render_feed(
    directories: list[Path],
    tenant: UUID,
    *,
    retained: dict[str, dict[str, object]] | None = None,
    failed: list[str] | None = None,
) -> bytes:
    if not 1 <= len(directories) <= MAX_CLUSTERS:
        raise ValueError("requires 1 to 32 original bundle directories")
    records: dict[str, object] = dict(retained or {})
    remaining = MAX_BYTES - 64 - len(json.dumps(records, ensure_ascii=False).encode())
    for directory in directories:
        assessment, config = read_assessment_artifacts(directory)
        projection = _project(assessment, tenant)
        if (
            analyze(assessment.snapshot, config, as_of=assessment.report.generated_at)
            != assessment.report
        ):
            raise ValueError("assessment report does not match deterministic replay")
        cluster_id = assessment.snapshot.clusters[0].resource_id
        if cluster_id in records:
            raise ValueError("select only one assessment per exact cluster ID")
        remaining -= len(json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode())
        if remaining < 0:
            raise ValueError("assessment feed exceeds the size limit")
        records[cluster_id] = projection
    feed: dict[str, object] = {
        "schemaVersion": "1",
        "clusters": [records[key] for key in sorted(records)],
    }
    if failed:
        feed["failedClusters"] = sorted(failed)
    if len(records) > MAX_CLUSTERS:
        raise ValueError("assessment feed exceeds the cluster limit")
    payload = (
        json.dumps(feed, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode()
    if len(payload) > MAX_BYTES:
        raise ValueError("assessment feed exceeds the size limit")
    return payload


def replace_feed_file(target: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".pending-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
