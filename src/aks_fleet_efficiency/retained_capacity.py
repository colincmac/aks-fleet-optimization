from __future__ import annotations

import html
import re
from pathlib import Path
from uuid import UUID

from aks_fleet_efficiency.history import MAXIMUM_ARTIFACT_BYTES, _read_verified_archive, _summary

_CAPACITY_PACKS = (
    ("AKS-NP-001", "Fixed-pool utilization"),
    ("AKS-NP-002", "Pool management and declared intent"),
    ("AKS-NP-003", "NAP policy and placement context"),
    ("AKS-NP-004", "Observed DaemonSet reservations"),
    ("AKS-SCHED-001", "Current placement restrictions"),
    ("AKS-SCHED-002", "Probe, topology and disruption-budget context"),
)


def _escape(value: str) -> str:
    single_line = " ".join(value.split())
    return re.sub(r"([\\`*_\[\]{}()#!|>])", r"\\\1", html.escape(single_line, quote=False))


def render_retained_capacity_review(directory: Path, *, tenant_id: UUID) -> str:
    archive, assessment, configuration = _read_verified_archive(directory, tenant_id=tenant_id)
    clusters = assessment.snapshot.clusters
    if len(clusters) != 1:
        raise ValueError("Retained capacity review requires one exact cluster and fingerprint")
    cluster = clusters[0]
    fingerprint = cluster.uid
    if fingerprint is None:
        raise ValueError("Retained capacity review requires one exact cluster and fingerprint")
    report = assessment.report
    run = _summary(archive, assessment, configuration)
    pack_versions = {pack.id: pack.version for pack in report.pack_provenance}
    lines = [
        "# Retained Capacity Review",
        "",
        f"Assessment run: `{run.run_id}` ({run.status}).",
        f"Original evaluation: {run.generated_at.isoformat()}.",
        f"Original window: {run.window_start.isoformat()} to {run.window_end.isoformat()}.",
        f"Cluster: {_escape(cluster.resource_id)}.",
        f"Cluster fingerprint: {_escape(fingerprint)}.",
        "",
        "| Pack | Evidence area | Version | Evaluated subjects | Result |",
        "| --- | --- | --- | ---: | --- |",
    ]
    details = []
    for pack_id, label in _CAPACITY_PACKS:
        version = pack_versions.get(pack_id)
        if version is None:
            lines.append(f"| {pack_id} | {label} | n/a | n/a | not selected |")
            continue
        subjects = report.summary.pack_subject_counts[pack_id]
        findings = sorted(
            (item for item in report.recommendations if item.rule_id == pack_id),
            key=lambda item: item.id,
        )
        blocked = sorted(
            (item for item in report.blocked_recommendations if item.rule_id == pack_id),
            key=lambda item: item.id,
        )
        if findings or blocked:
            result = f"{len(findings)} investigation(s), {len(blocked)} blocked"
        else:
            result = "no finding at original evaluation" if subjects else "no subjects evaluated"
        lines.append(f"| {pack_id} | {label} | {version} | {subjects} | {result} |")
        for finding in findings:
            details.append(f"- {pack_id} / {_escape(finding.id)}: {_escape(finding.summary)}")
        for item in blocked:
            reasons = ", ".join(_escape(reason) for reason in sorted(item.reason_codes))
            details.append(
                f"- {pack_id} / {_escape(item.id)}: missing or blocked evidence: {reasons}."
            )
    lines.extend(["", "## Investigations And Gaps", ""])
    lines.extend(details or ["No investigation or blocker was reported by the selected packs."])
    lines.extend(
        [
            "",
            "Use the finding IDs to open the original report for quantities and citations.",
            "Current restrictions and declared reserve do not establish historical causes.",
            "Missing evidence or no finding does not establish spare capacity or a healthy pool.",
            "",
            "- Scheduler fit: blocked",
            "- Disruption feasibility: not determined",
            "- Removable nodes: not calculated",
            "- Savings: not calculated",
        ]
    )
    result = "\n".join(lines) + "\n"
    if len(result.encode("utf-8")) > MAXIMUM_ARTIFACT_BYTES:
        raise ValueError("Retained capacity review exceeds its output budget")
    return result
