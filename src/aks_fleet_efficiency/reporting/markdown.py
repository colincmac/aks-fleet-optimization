from __future__ import annotations

import re
from html import escape

from aks_fleet_efficiency.assessment import OfflineAssessment
from aks_fleet_efficiency.fleet import FleetInsightReport, FleetResourceEnvelope
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
    analysis = render_markdown(result.report)
    if result.baseline_measurements:
        analysis = analysis.rstrip("\n")
        lines.extend(
            [
                "",
                "## Unresolved baseline measurements",
                "",
                "Source-series coverage below is the fraction of expected evaluation points "
                "returned for each series. The report's metric coverage describes the assessment "
                "window, not these individual series. Names do not establish historical Pod or "
                "workload identity, so even full series coverage cannot justify a new request.",
                "",
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
    lines.extend(["", analysis])
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


def _inventory_text(value: object) -> str:
    return "unknown" if value is None else _text(value)


def _resource_lines(envelope: FleetResourceEnvelope) -> list[str]:
    lines = [f"- Resource scope: {_text(envelope.scope_notice)}"]
    for field, label in [
        ("node_capacity", "Current Node capacity"),
        ("allocatable", "Current allocatable"),
        ("requested", "Included nonterminal Pod requests"),
        ("observed_usage", "Aligned observed usage"),
    ]:
        amount = getattr(envelope, field)
        lines.append(
            f"- {label}: {_inventory_text(amount.cpu_mcpu)} mCPU; "
            f"{_inventory_text(amount.memory_mib)} MiB ({_text(amount.status)}; "
            f"gaps: {_text(amount.reason_codes)})"
        )
    times = [time.isoformat() for time in envelope.observation_times]
    lines.append(f"- Resource observation times: {_text(times)}")
    return lines


def render_fleet_markdown(report: FleetInsightReport) -> str:
    lines = [
        "# AKS Fleet Optimization Insights",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        f"Tenant: {_code(report.tenant_id)}",
        f"Comparable assessments: {'yes' if report.comparable else 'no'}",
        "",
        "## Summary",
        "",
        f"- Clusters: {report.summary.clusters}",
        f"- Peer groups: {report.summary.peer_groups}",
        f"- Recommendations: {report.summary.recommendations}",
        f"- High or critical: {report.summary.high_or_critical}",
        f"- Blocked findings: {report.summary.blocked_recommendations}",
        "- Estimated monthly savings: not calculated",
    ]
    if report.comparability_reasons:
        lines.extend(["", "## Comparability gaps", ""])
        lines.extend(f"- {_code(reason)}" for reason in report.comparability_reasons)
    lines.extend(
        [
            "",
            "## Peer groups",
            "",
            "Counts describe admitted observations, not demand, placement or live cluster health. "
            "Partial and unknown inventory remain explicit; "
            "non-comparable groups are not rankings.",
        ]
    )
    for group in report.peer_groups:
        lines.extend(
            [
                "",
                f"### {_text(group.peer_group)}",
                "",
                f"- Clusters: {group.clusters}",
                f"- Comparable within group: {'yes' if group.comparable else 'no'}",
                f"- Comparability gaps: {_text(group.comparability_reasons)}",
                f"- Finding categories: {_text(group.category_counts)}",
                f"- Rule counts: {_text(group.rule_counts)}",
                f"- Blocker counts: {_text(group.blocked_reason_counts)}",
                f"- Observed pool objects: {_inventory_text(group.supply_pool_counts)}",
                f"- ARM pool market counts: {_inventory_text(group.arm_pool_market_counts)}",
                f"- Observed workload owners: {_inventory_text(group.workload_counts)}",
                f"- Review declarations: {_inventory_text(group.review_owner_status_counts)}",
                f"- Inventory status counts: {_text(group.inventory_status_counts)}",
                *_resource_lines(group.resource_envelope),
            ]
        )
        if group.historical_usage is not None:
            usage = group.historical_usage
            lines.extend(
                [
                    "- Historical supplied-data source admission: unverified",
                    f"- Historical window: {_text(usage.window_start)} "
                    f"to {_text(usage.window_end)}",
                    f"- Historical CPU P95 mCPU: {_inventory_text(usage.cpu_p95_mcpu)}",
                    "- Historical Node working-set P99 MiB: "
                    f"{_inventory_text(usage.memory_p99_working_set_mib)}",
                    f"- Historical CPU gaps: {_text(usage.cpu_gaps)}",
                    f"- Historical memory gaps: {_text(usage.memory_gaps)}",
                ]
            )
    lines.extend(["", "## Clusters", ""])
    for cluster in report.clusters:
        lines.extend(
            [
                f"### {_text(cluster.cluster_name)}",
                "",
                f"- Resource ID: {_code(cluster.cluster_resource_id)}",
                f"- Cluster fingerprint: {_code(cluster.cluster_uid)}",
                f"- Peer group: {_code(cluster.peer_group)}",
                f"- Assessment status: {_code(cluster.assessment_status)}",
                f"- Original assessment time: {_code(cluster.generated_at.isoformat())}",
                f"- Excluded namespaces: {_text(cluster.excluded_namespaces)}",
                f"- Recommendations: {cluster.recommendations}",
                f"- Blocked findings: {cluster.blocked_recommendations}",
                f"- Source capability statuses: {_text(cluster.source_status_counts)}",
                f"- Supply inventory status: {_code(cluster.supply_inventory.status)}",
                f"- Observed pool objects: {_inventory_text(cluster.supply_inventory.pool_counts)}",
                f"- Supply gaps: {_text(cluster.supply_inventory.reason_codes)}",
                "- ARM pool market status: "
                f"{_code(cluster.supply_inventory.arm_pool_market.status)}",
                "- ARM pool market counts: "
                f"{_inventory_text(cluster.supply_inventory.arm_pool_market.pool_counts)}",
                "- ARM pool market gaps: "
                f"{_text(cluster.supply_inventory.arm_pool_market.reason_codes)}",
                f"- Market scope: {_text(cluster.supply_inventory.arm_pool_market.unit)}",
                f"- Workload inventory status: {_code(cluster.workload_inventory.status)}",
                "- Observed workload owners: "
                f"{_inventory_text(cluster.workload_inventory.workload_counts)}",
                f"- Listed Pods: {_inventory_text(cluster.workload_inventory.observed_pods)}",
                f"- Unresolved Pods: {_inventory_text(cluster.workload_inventory.unresolved_pods)}",
                f"- Workload gaps: {_text(cluster.workload_inventory.reason_codes)}",
                f"- Finding categories: {_text(cluster.category_counts)}",
                f"- Rule counts: {_text(cluster.rule_counts)}",
                f"- Blocker counts: {_text(cluster.blocked_reason_counts)}",
                *_resource_lines(cluster.resource_envelope),
                "",
            ]
        )
        if cluster.historical_usage is not None:
            history = cluster.historical_usage
            lines.extend(
                [
                    "#### Supplied historical usage (source unverified)",
                    "",
                    f"- Window: {_text(history.window_start)} to {_text(history.window_end)}",
                    f"- CPU P95 mCPU: {_inventory_text(history.cpu_p95_mcpu)}",
                    "- Node working-set P99 MiB: "
                    f"{_inventory_text(history.memory_p99_working_set_mib)}",
                    f"- CPU gaps: {_text(history.cpu_gaps)}",
                    f"- Memory gaps: {_text(history.memory_gaps)}",
                    "",
                ]
            )
        if cluster.external_context is not None:
            context = cluster.external_context
            lines.extend(["#### Supplemental routing and market context (source unverified)", ""])
            for owner in context.business_owners:
                lines.append(
                    f"- Namespace UID {_code(owner.namespace_uid)}; workload UID "
                    f"{_code(owner.workload_uid)}; business routing {_code(owner.status)}; "
                    f"owner reference {_inventory_text(owner.owner_ref)}; "
                    f"gaps {_text(owner.reason_codes)}"
                )
            if context.market_history is not None:
                market = context.market_history
                lines.append(
                    f"- Historical market window {_text(market.window_start)} to "
                    f"{_text(market.window_end)}; sampled points {len(market.points)}; "
                    f"unknown points {sum(point.market_counts is None for point in market.points)}"
                )
                lines.append(f"- Separate source fallback gaps: {_text(market.fallback_gaps)}")
            lines.append("")
        lines.extend(["#### Namespace workload distribution", ""])
        namespaces = cluster.workload_inventory.namespace_distribution
        if namespaces is None:
            lines.append("Unknown: workload inventory prerequisites were not met.")
        elif not namespaces:
            lines.append("No included listed Pods.")
        else:
            for namespace in namespaces:
                lines.append(
                    f"- {_text(namespace.namespace)} / UID "
                    f"{_inventory_text(namespace.namespace_uid)}: "
                    f"owners {_inventory_text(namespace.workload_counts)}; "
                    f"listed Pods {namespace.observed_pods}; "
                    f"unresolved Pods {namespace.unresolved_pods}"
                )
        lines.extend(
            [
                "",
                "#### Review declarations",
                "",
                "Current review declarations only; not business ownership or change approval.",
                "",
            ]
        )
        investigations = cluster.workload_inventory.workload_investigations
        if investigations is None:
            lines.append("Unknown: workload inventory prerequisites were not met.")
        elif not investigations:
            lines.append("No resolved included workload identities; see unresolved Pod counts.")
        else:
            for item in investigations:
                lines.append(
                    f"- {_text(item.workload_kind)} {_text(item.workload_name)} "
                    f"in {_text(item.namespace)} / Namespace UID {_code(item.namespace_uid)} / "
                    f"workload UID {_code(item.workload_uid)}: "
                    f"{_code(item.review_owner_status)}; gaps {_text(item.reason_codes)}"
                )
                lines.append(
                    f"- Observed supply: {_inventory_text(item.observed_supply.pod_counts)} "
                    f"({_text(item.observed_supply.status)}; "
                    f"gaps {_text(item.observed_supply.reason_codes)}); "
                    f"{_text(item.observed_supply.unit)}"
                )
        lines.append("")
    lines.extend(
        [
            "No fleet efficiency score or savings estimate is calculated.",
            "Clusters with incompatible windows, modes, configurations or pack definitions "
            "remain explicitly non-comparable.",
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
        f"- Snapshot ARM node-pool records: {summary.node_pools_analyzed}",
        f"- Snapshot vertical-workload records: {summary.workloads_analyzed}",
        f"- Recommendations: {summary.recommendations}",
        f"- High or critical: {summary.high_or_critical}",
        f"- Blocked findings: {summary.blocked_recommendations}",
    ]
    for pack_id, count in sorted(summary.pack_subject_counts.items()):
        lines.append(f"- {_code(pack_id)} subjects evaluated: {count}")
    lines.append(
        "Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, "
        "and are not additive workload counts or evidence of complete inventory."
    )
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
