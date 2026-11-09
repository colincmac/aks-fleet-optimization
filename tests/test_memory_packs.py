from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_rules import AS_OF, eligible_snapshot, memory_proposal_payload

from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.config import AdvisorConfig, load_onboarding_config
from aks_fleet_efficiency.models import FleetSnapshot
from aks_fleet_efficiency.rules.engine import analyze

MEMORY = [f"AKS-MEM-{index:03}" for index in range(1, 6)]
RELIABILITY = [f"AKS-REL-{index:03}" for index in range(1, 4)]


def test_eight_memory_reliability_packs_are_registered_with_complete_cards() -> None:
    catalog = load_catalog()
    assert len(catalog.manifests) == 21
    for name in [*MEMORY, *RELIABILITY]:
        pack = catalog.pack(name)
        assert pack.version == "2.0.0"
        assert pack.family in {"memory", "reliability"}
        assert pack.title and pack.purpose and pack.limitations
        assert pack.required_evidence and pack.risks and pack.validation and pack.rollback
        assert pack.parameters.review_ratio is None
        with pytest.raises(ValidationError):
            AdvisorConfig(packs=[name], pack_parameters={name: {"review_ratio": 0.2}})
    for name in ["AKS-MEM-004", "AKS-REL-002"]:
        assert catalog.pack(name).evidence_kind == "inventory"
        assert catalog.provenance(name).queries == []


@pytest.mark.parametrize(
    ("case", "pack_id", "expected"),
    [
        ("memory", "AKS-MEM-003", 313),
        ("memory-envelope", "AKS-MEM-003", 313),
        ("memory-limit", "AKS-MEM-005", 600),
        ("memory-context", "AKS-MEM-004", 1184),
    ],
)
def test_selected_memory_pack_preserves_exact_evidence_and_native_replay(
    case: str, pack_id: str, expected: float
) -> None:
    fragments = AssessmentFragments.model_validate_json(
        Path(f"examples/fixtures/{case}-assessment.json").read_bytes()
    )
    profile = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    profile.analysis = AdvisorConfig(mode="guarded", packs=[pack_id])
    result = assess_fragments(fragments, profile, as_of=AS_OF)
    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    assert finding.rule_id == pack_id
    assert finding.rule_version == "2.0.0"
    assert finding.estimated_monthly_savings is None
    if pack_id == "AKS-MEM-003":
        assert finding.proposed_requests.memory_mib == expected
        assert finding.proposed_requests.cpu_mcores is None
        assert finding.proposed_limits is None
    elif pack_id == "AKS-MEM-005":
        assert finding.proposed_limits.memory_mib == expected
        assert finding.proposed_requests is None
    else:
        assert any(
            item.metric == "effective_pod_memory_request" and item.value == expected
            for item in finding.evidence
        )
    assert analyze(result.snapshot, profile.analysis, as_of=AS_OF) == result.report


@pytest.mark.parametrize("pack_id", ["AKS-MEM-003", "AKS-MEM-005"])
def test_memory_numeric_packs_remain_blocked_in_baseline(pack_id: str) -> None:
    case = "memory" if pack_id == "AKS-MEM-003" else "memory-limit"
    fragments = AssessmentFragments.model_validate_json(
        Path(f"examples/fixtures/{case}-assessment.json").read_bytes()
    )
    profile = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    profile.analysis = AdvisorConfig(packs=[pack_id])
    result = assess_fragments(fragments, profile, as_of=AS_OF)
    assert not result.report.recommendations
    assert any(
        "guarded_mode_required" in item.reason_codes
        for item in result.report.blocked_recommendations
    )


@pytest.mark.parametrize("pack_id", ["AKS-MEM-001", "AKS-REL-001"])
def test_reliability_investigation_survives_missing_cpu_and_active_controllers(
    pack_id: str,
) -> None:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    workload.autoscaling.hpa = True
    resources = workload.containers[0].resources
    resources.usage_cpu_p95_mcores = None
    resources.usage_cpu_p99_mcores = None
    field = "memory_oom_events" if pack_id == "AKS-MEM-001" else "restart_events"
    setattr(resources, field, 1)
    resources.metric_quality[field].maximum = 1
    report = analyze(snapshot, AdvisorConfig(packs=[pack_id]), as_of=AS_OF)
    assert len(report.recommendations) == 1
    assert report.recommendations[0].rule_id == pack_id
    assert report.recommendations[0].proposed_requests is None


@pytest.mark.parametrize("defect", ["owner", "coverage", "oom", "opt-in", "identity"])
def test_request_pack_retains_existing_proposal_vetoes(defect: str) -> None:
    payload = memory_proposal_payload()
    workload = payload["clusters"][0]["workloads"][0]
    resources = workload["containers"][0]["resources"]
    if defect == "owner":
        workload["safety_policy"] = None
    elif defect == "coverage":
        resources["metric_quality"]["usage_memory_p99_mib"]["window"]["coverage_ratio"] = 0.5
    elif defect == "oom":
        resources["memory_oom_events"] = 1
    elif defect == "opt-in":
        workload["safety_policy"]["memory"][workload["containers"][0]["name"]][
            "allow_request_reduction"
        ] = False
    else:
        workload["uid"] = None
    result = analyze(
        FleetSnapshot.model_validate(payload),
        AdvisorConfig(mode="guarded", packs=["AKS-MEM-003"]),
        as_of=AS_OF,
    )
    assert not result.recommendations
    assert result.blocked_recommendations


def test_last_termination_and_eviction_reviews_stay_independent_and_noncausal() -> None:
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/memory-context-assessment.json").read_bytes()
    )
    profile = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    profile.analysis = AdvisorConfig(packs=["AKS-REL-002", "AKS-REL-003"])
    result = assess_fragments(fragments, profile, as_of=AS_OF)
    assert {item.rule_id for item in result.report.recommendations} == {
        "AKS-REL-002",
        "AKS-REL-003",
    }
    assert all(
        item.proposed_requests is None and item.proposed_limits is None
        for item in result.report.recommendations
    )
    assert all("cause" in item.summary for item in result.report.recommendations)
