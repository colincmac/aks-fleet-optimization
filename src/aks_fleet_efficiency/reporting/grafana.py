"""Static Grafana dashboard projection for retained fleet evidence."""

import json
from collections import Counter
from hashlib import sha256

from pydantic import JsonValue

from aks_fleet_efficiency.fleet import FleetGapDimension, FleetResourceEnvelope
from aks_fleet_efficiency.history import (
    MAXIMUM_DRIFT_BYTES,
    FleetCheckEvidence,
    FleetDriftMatrix,
    FleetDriftObservation,
    FleetDriftRow,
)


def _literal(value: str) -> str:
    # Encode Markdown and Grafana interpolation syntax as text, not markup.
    return "".join(
        char if char.isascii() and (char.isalnum() or char in " -") else f"&#{ord(char)};"
        for char in " ".join(value.split())
        if char.isprintable()
    )


def _amount(value: float | None) -> str:
    return "Unknown" if value is None else format(value, ".8g")


def _gap(value: FleetGapDimension) -> str:
    return f"Unknown ({value.reason})" if value.reason else _amount(value.value)


def _resources(envelope: FleetResourceEnvelope) -> list[str]:
    result = [
        "| Quantity | CPU (mCPU) | Memory (MiB) |",
        "| --- | ---: | ---: |",
        f"| C: Node capacity | {_amount(envelope.node_capacity.cpu_mcpu)} | "
        f"{_amount(envelope.node_capacity.memory_mib)} |",
        f"| A: Node allocatable | {_amount(envelope.allocatable.cpu_mcpu)} | "
        f"{_amount(envelope.allocatable.memory_mib)} |",
        f"| R: Effective Pod requests | {_amount(envelope.requested.cpu_mcpu)} | "
        f"{_amount(envelope.requested.memory_mib)} |",
    ]
    gaps = envelope.current_gaps
    if gaps is not None:
        for label, pair in (
            ("C - A", gaps.capacity_minus_allocatable),
            ("A - R", gaps.allocatable_minus_requests),
        ):
            result.append(f"| {label} | {_gap(pair.cpu)} | {_gap(pair.memory)} |")
        unavailable = f"Unknown ({gaps.requests_minus_usage})"
        result.append(f"| R - U | {unavailable} | {unavailable} |")
    else:
        result.append("| Resource gaps | Unknown | Unknown |")
    return result


def _checks(evidence: FleetCheckEvidence | None) -> str:
    if evidence is None:
        return "Check coverage: Unknown (no per-pack evidence in this projection)."
    lines = [
        "Check coverage: Unknown (the original report does not retain an expected subject roster).",
        "",
        "Examined subjects include blocked and no-finding evaluations. Some blockers identify "
        "missing inventory before any subjects can be examined.",
        "",
        "| Selected pack | Version | Examined subjects | Qualified findings | "
        "Blocked records | High or critical |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {pack.pack_id} | {pack.version} | {pack.examined_subjects} | {pack.qualified_findings} "
        f"| {pack.blocked_records} | {pack.high_or_critical_findings} |"
        for pack in evidence.packs
    )
    return "\n".join(lines)


def _observation(entry: FleetDriftObservation, title: str) -> list[str]:
    run = entry.run
    clocks = ", ".join(item.isoformat() for item in entry.resources.observation_times)
    high_risk = entry.high_or_critical if entry.high_or_critical is not None else "Unknown"
    return [
        f"### {title}",
        "",
        f"- **Run:** `{run.run_id}`",
        f"- **Evaluated:** {run.generated_at.isoformat()} ({entry.age_seconds / 3600:.1f} h old "
        "at export)",
        f"- **Original window:** {run.window_start.isoformat()} to {run.window_end.isoformat()}",
        f"- **Assessment:** {run.status}; {run.recommendations} findings; "
        f"{run.blocked_recommendations} blocked records",
        f"- **High or critical findings:** {high_risk}",
        f"- **Metric coverage:** {entry.metric_coverage_ratio:.1%} "
        f"({entry.metric_sample_count} recorded samples; not check coverage)",
        f"- **Configuration digest:** `{run.configuration_digest}`",
        f"- **Inventory observed:** {clocks or 'Unknown'}",
        "",
        *_resources(entry.resources),
        "",
    ]


def _row_content(row: FleetDriftRow) -> str:
    lines = [
        f"**Cluster:** {_literal(row.cluster_resource_id)}",
        "",
        f"**Fingerprint:** {_literal(row.cluster_uid)}  ",
        f"**Peer group:** {_literal(row.peer_group)}",
        "",
        *_observation(row.latest, "Latest selected assessment"),
    ]
    if row.latest_comparison is not None and row.latest_comparison.comparable:
        states = Counter(item.state for item in row.latest_comparison.findings)
        details = ", ".join(f"{key}: {value}" for key, value in sorted(states.items()))
        lines += [
            f"**Comparable latest pair:** {sum(states.values())} comparison records. "
            f"{details or 'No records.'}",
            "",
        ]
    else:
        lines += ["**Latest comparison unavailable or not comparable.**", ""]
    if row.reason_codes:
        lines += [f"**Series limitations:** {', '.join(row.reason_codes)}", ""]
    if row.recurring_findings is None:
        lines += ["**Recurring findings:** Unknown.", ""]
    else:
        recurring = Counter(item.rule_id for item in row.recurring_findings)
        details = ", ".join(
            f"{_literal(rule)}: {total}" for rule, total in sorted(recurring.items())
        )
        lines += [f"**Recurring findings:** {sum(recurring.values())}. {details}", ""]
    if row.prior_comparable_resources is not None:
        lines.extend(_observation(row.prior_comparable_resources, "Comparable prior assessment"))
    return "\n".join(lines)


def fleet_grafana_dashboard(matrix: FleetDriftMatrix) -> str:
    def panel(index: int, title: str, content: str, *, y: int, height: int) -> JsonValue:
        return {
            "id": index,
            "title": title,
            "type": "text",
            "gridPos": {"x": 0, "y": y, "w": 24, "h": height},
            "options": {"mode": "markdown", "content": content},
        }

    overview = (
        f"Immutably replayed at **{matrix.evaluated_at.isoformat()}** (export evaluation clock), "
        f"with **{len(matrix.rows)}** selected cluster/fingerprint/peer rows.\n\n"
        "This is a fixed, protected snapshot. Grafana's time picker does not change it. "
        "Missing data stays unknown; not observed does not mean resolved. "
        "The resource rows are neither free capacity, safe reductions, nor financial savings.\n\n"
        "Run IDs identify retained originals; they are not public links. "
        "Do not share this dashboard or its JSON outside the approved assessment audience."
    )
    panels = [panel(1, "About this evidence", overview, y=0, height=6)]
    y = 6
    for index, row in enumerate(matrix.rows, start=1):
        height = 32 if row.prior_comparable_resources is not None else 20
        panel_id = 2 * index
        panels.append(
            panel(panel_id, f"Cluster evidence {index}", _row_content(row), y=y, height=height)
        )
        y += height
        checks = row.latest.check_evidence
        check_height = 6 + (len(checks.packs) if checks is not None else 0)
        panels.append(
            panel(
                panel_id + 1,
                f"Latest check evidence for cluster {index}",
                _checks(checks),
                y=y,
                height=check_height,
            )
        )
        y += check_height
    digest = sha256(matrix.model_dump_json().encode()).hexdigest()[:16]
    dashboard = json.dumps(
        {
            "uid": f"aks-advisor-evidence-{digest}",
            "title": f"AKS Advisor: Fleet Evidence ({matrix.evaluated_at.isoformat()})",
            "schemaVersion": 39,
            "version": 1,
            "timezone": "utc",
            "refresh": "",
            "timepicker": {"hidden": True},
            "panels": panels,
        }
    )
    if len(dashboard.encode()) > MAXIMUM_DRIFT_BYTES:
        raise ValueError("Grafana evidence dashboard exceeds the projection byte budget")
    return dashboard
