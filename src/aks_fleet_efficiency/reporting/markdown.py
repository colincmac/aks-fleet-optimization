from __future__ import annotations

import re
from html import escape

from aks_fleet_efficiency.assessment import OfflineAssessment
from aks_fleet_efficiency.models import AnalysisReport, ReadinessReport


def _text(value: object) -> str:
    cleaned = (
        escape(str(value), quote=True).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    )
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", cleaned)


def _code(value: object) -> str:
    raw = str(value)
    if any(character in raw for character in "<>&`[]()\r\n\t"):
        return _text(raw)
    cleaned = escape(raw, quote=True)
    return f"`{cleaned}`"


def render_assessment_markdown(result: OfflineAssessment) -> str:
    lines = [
        "# AKS Fleet Assessment",
        "",
        f"Status: {_text(result.status)}",
        f"Assessment scope: {_code(result.assessment_scope)}",
        f"Input digest: {_code(result.input_digest)}",
        f"Profile digest: {_code(result.profile_digest)}",
        "",
        "CPU and memory proposals require separate owner approval; "
        "no changes or cash savings are authorized.",
        "Replica-envelope statistics describe a conservative per-replica upper envelope, "
        "not workload-total percentiles. Missing or unsupported evidence remains explicit.",
        "",
        "## Normalization Gaps",
        "",
    ]
    lines.extend(f"- {_code(issue.scope)}: {_code(issue.code)}" for issue in result.issues)
    if not result.issues:
        lines.append("No normalization gaps in the supported scope.")
    manifest = result.snapshot.collection_manifest
    if manifest is not None:
        lines.extend(
            [
                "",
                "## Source Receipts",
                "",
                "Eligibility requires a complete, fresh matching receipt; "
                "completed scope alone is insufficient.",
                "",
            ]
        )
        for receipt in manifest.source_results:
            observed = (
                receipt.source_observed_at.isoformat() if receipt.source_observed_at else "unknown"
            )
            for scope in receipt.requested_scope:
                lines.append(
                    f"- {_code(receipt.collector)} / {_code(scope)}: {_code(receipt.status)}; "
                    f"completed: {_code(scope in receipt.completed_scope)}; "
                    f"pages complete: {_code(receipt.pagination_complete)}; "
                    f"source observed: {_code(observed)}"
                )
            lines.extend(
                f"- Failure: {_code(error.scope)} / {_code(error.code)}" for error in receipt.errors
            )
            lines.extend(f"- Missing field: {_code(field)}" for field in receipt.missing_fields)
    lines.extend(["", render_markdown(result.report)])
    if result.baseline_measurements:
        lines.extend(
            [
                "",
                "## Unresolved baseline measurements",
                "",
                "Names identify source series only, not historical workload or Pod identities.",
            ]
        )
        for observation in result.baseline_measurements:
            lines.append(
                f"- {_code(observation.entity.namespace)} / {_code(observation.entity.pod)} / "
                f"{_code(observation.entity.container)}: {_code(observation.metric)} "
                f"P95 {_text(observation.p95)} {_text(observation.quality.unit)}; "
                f"coverage {_text(observation.quality.window.coverage_ratio)}; "
                f"issues {_text(', '.join(observation.issues) or 'none observed')}."
            )
    return "\n".join(lines)


def render_readiness_markdown(report: ReadinessReport) -> str:
    lines = [
        "# AKS Fleet Readiness Report",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        f"Mode: {_text(report.mode)}",
        f"Status: {_text(report.status)}",
        f"Subscriptions requested: {report.requested_subscriptions}",
        f"Explicit cluster targets: {report.requested_clusters}",
        f"Configuration digest: {_code(report.configuration_digest)}",
        "",
        "## Checks",
        "",
    ]
    for check in report.checks:
        lines.append(
            f"- **{_text(check.status)}** {_code(check.code)} / {_code(check.scope)}: "
            f"{_text(check.message)}"
        )
    lines.extend(
        [
            "",
            "Offline readiness does not authenticate, query endpoints, grant access, "
            "or authorize changes. "
            "Declared retention and mappings are not proof of available historical series.",
            "",
        ]
    )
    return "\n".join(lines)


def render_markdown(report: AnalysisReport) -> str:
    summary = report.summary
    lines = [
        "# AKS Fleet Efficiency Advisor Report",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        f"Assessment mode: {_code(report.mode)}",
        f"Observation window: {report.observation_window.start.isoformat()} to "
        f"{report.observation_window.end.isoformat()}",
        "",
        "## Summary",
        "",
        f"- Clusters analyzed: {summary.clusters_analyzed}",
        f"- Node pools analyzed: {summary.node_pools_analyzed}",
        f"- Workloads analyzed: {summary.workloads_analyzed}",
        f"- Recommendations: {summary.recommendations}",
        f"- High or critical: {summary.high_or_critical}",
        f"- Blocked findings: {summary.blocked_recommendations}",
    ]
    if report.snapshot_digest:
        lines.append(f"- Snapshot digest: {_code(report.snapshot_digest)}")
    if report.configuration_digest:
        lines.append(f"- Configuration digest: {_code(report.configuration_digest)}")
    for pack in report.pack_provenance:
        lines.append(
            f"- Pack: {_code(pack.id)} v{_text(pack.version)}; digest: {_code(pack.digest)}"
            + (
                f"; review ratio: {_text(pack.parameters.review_ratio)}"
                if pack.parameters.review_ratio is not None
                else "; inventory-only"
            )
        )
    if report.source_capabilities:
        lines.extend(
            [
                "",
                "## Source capabilities",
                "",
                "Metric availability is not source attestation or safe-change approval.",
            ]
        )
        for capability in report.source_capabilities:
            lines.append(
                f"- {_code(capability.source)} / {_code(capability.pack_id)} / "
                f"{_code(capability.mode)}: {_code(capability.status)} "
                f"({_code(capability.source_profile.id)})."
            )
            for check in capability.checks:
                if check.status != "available":
                    lines.append(f"  - {_code(check.code)}: {_text(', '.join(check.reason_codes))}")
    if summary.data_quality_warnings:
        lines.extend(["", "## Data quality warnings", ""])
        lines.extend(f"- {_text(warning)}" for warning in summary.data_quality_warnings)
    lines.extend(["", "## Recommendations", ""])
    if not report.recommendations:
        lines.append("No recommendations were generated.")
    for index, rec in enumerate(report.recommendations, 1):
        lines.extend(
            [
                f"### {index}. {_text(rec.title)}",
                "",
                f"- **ID:** {_code(rec.id)}",
                f"- **Rule:** {_code(rec.rule_id)} v{_text(rec.rule_version)}",
                f"- **Severity / confidence:** {rec.severity.value} / {rec.confidence.value}",
                f"- **Cluster:** {_code(rec.cluster_name)}",
                f"- **Scope:** {_code(rec.namespace or '-')} / {_code(rec.workload or '-')}",
                f"- **Category:** {_text(rec.category)}",
                "",
                _text(rec.summary),
                "",
                "**Evidence**",
                "",
            ]
        )
        if rec.owner:
            lines.append(f"- **Owner:** {_text(rec.owner)}")
        if rec.current_limits is not None and rec.proposed_limits is not None:
            lines.append(
                f"- **Memory limit:** {_text(rec.current_limits.memory_mib)} to "
                f"{_text(rec.proposed_limits.memory_mib)} MiB; requests unchanged"
            )
        if rec.current_replica_floor is not None and rec.proposed_replica_floor is not None:
            lines.append(
                f"- **HPA minimum replicas:** {_text(rec.current_replica_floor)} to "
                f"{_text(rec.proposed_replica_floor)} pods; maximum and resource requests unchanged"
            )
        if rec.current_requests and rec.proposed_requests:
            for label, current, proposed, unit in [
                (
                    "CPU request",
                    rec.current_requests.cpu_mcores,
                    rec.proposed_requests.cpu_mcores,
                    "mCPU",
                ),
                (
                    "Memory request",
                    rec.current_requests.memory_mib,
                    rec.proposed_requests.memory_mib,
                    "MiB",
                ),
            ]:
                if current is not None and proposed is not None:
                    lines.append(
                        f"- **{label}:** {_text(current)} to {_text(proposed)} {unit} per replica"
                    )
        for item in rec.evidence:
            unit = f" {_text(item.unit)}" if item.unit else ""
            lines.append(
                f"- {_code(item.metric)} = {_code(item.value)}{unit} ({_text(item.source)})"
            )
        lines.extend(["", "**Prerequisites**", ""])
        lines.extend(f"- {_text(item)}" for item in rec.prerequisites)
        lines.extend(["", "**Proposed actions**", ""])
        lines.extend(f"- {_text(action)}" for action in rec.proposed_actions)
        lines.extend(["", "**Validation and safety**", ""])
        lines.extend(f"- {_text(step)}" for step in rec.validation_steps)
        lines.extend(f"- Risk: {_text(risk)}" for risk in rec.risks)
        lines.extend(["", "**Rollback**", ""])
        lines.extend(f"- {_text(step)}" for step in rec.rollback_steps)
        lines.append("")
    if report.blocked_recommendations:
        lines.extend(
            ["## Blocked findings", "", "These checks are not actionable recommendations.", ""]
        )
        for blocked_item in report.blocked_recommendations:
            lines.append(
                f"- {_code(blocked_item.rule_id)} / {_code(blocked_item.id)} / "
                f"{_code(blocked_item.cluster_name)} / {_code(blocked_item.namespace or '-')} / "
                f"{_code(blocked_item.workload or '-')}: "
                + ", ".join(_code(reason) for reason in blocked_item.reason_codes)
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "This report proposes investigations and controlled changes; it does not authorize or "
            "apply changes. Validate recommendations against workload SLOs, resilience "
            "requirements, business cycles, and representative load.",
            "",
        ]
    )
    return "\n".join(lines)
