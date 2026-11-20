import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

DEMO = Path(__file__).resolve().parents[1] / "deploy" / "aks-fleet-demo"


def _render(cluster: str) -> dict[tuple[str, str], Any]:
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        pytest.skip("kubectl is required to render the existing demo overlays")
    result = subprocess.run(
        [kubectl, "kustomize", str(DEMO / cluster)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return {
        (item["kind"], item["metadata"]["name"]): item for item in yaml.safe_load_all(result.stdout)
    }


@pytest.mark.parametrize(
    ("cluster", "name", "target", "maximum"),
    [
        ("cluster-a", "cpu-pulse", "cpu-pulse", 2),
        ("cluster-b", "startup-fixed", "startup-profile", 1),
    ],
)
def test_default_profiles_render_live_hpa_without_requiring_optional_features(
    cluster: str, name: str, target: str, maximum: int
) -> None:
    manifests = _render(cluster)
    hpa = manifests["HorizontalPodAutoscaler", name]["spec"]
    assert hpa["minReplicas"] == 1
    assert hpa["maxReplicas"] == maximum
    assert hpa["scaleTargetRef"]["name"] == target
    pod = manifests["Deployment", target]["spec"]["template"]["spec"]
    assert pod["containers"][0]["resources"]["requests"]["cpu"]
    assert {
        "VerticalPodAutoscaler",
        "ScaledObject",
        "PersistentVolumeClaim",
        "Job",
        "NodePool",
        "AKSNodeClass",
    }.isdisjoint(kind for kind, _ in manifests)
    assert ("Deployment", "fault-once") not in manifests


def test_cluster_b_contrasts_the_same_idle_workload_without_changing_its_identity() -> None:
    a = _render("cluster-a")
    b = _render("cluster-b")
    before = a["Deployment", "idle-fixed"]["spec"]
    after = b["Deployment", "idle-fixed"]["spec"]
    assert before["selector"] == after["selector"]
    assert before["replicas"] == after["replicas"] == 2
    original = before["template"]["spec"]["containers"][0]
    comparable = after["template"]["spec"]["containers"][0]
    assert original["resources"]["requests"]["cpu"] == "200m"
    assert comparable["resources"]["requests"]["cpu"] == "100m"
    assert "readinessProbe" not in original and "readinessProbe" in comparable
    assert "topologySpreadConstraints" in after["template"]["spec"]
    assert a["PodDisruptionBudget", "idle-fixed"]["spec"]["maxUnavailable"] == 0
    assert b["PodDisruptionBudget", "idle-fixed"]["spec"]["maxUnavailable"] == 1


def test_nap_workload_is_off_by_default_and_bounded_when_started() -> None:
    job = yaml.safe_load(
        (DEMO / "cluster-a" / "51-nap-provisioning.yaml").read_text(encoding="utf-8")
    )
    assert job["kind"] == "Job"
    spec = job["spec"]
    assert spec["suspend"] is True
    assert spec["parallelism"] == spec["completions"] == 1
    assert spec["backoffLimit"] == 0
    assert 0 < spec["activeDeadlineSeconds"] <= 600
    pod = spec["template"]["spec"]
    assert pod["nodeSelector"]["karpenter.sh/nodepool"] == "replace-with-approved-nap-pool"
    assert pod["automountServiceAccountToken"] is False
    assert pod["restartPolicy"] == "Never"
    container = pod["containers"][0]
    assert container["resources"]["limits"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True


def test_pending_scheduler_sample_keeps_its_gate_and_requires_no_node_changes() -> None:
    job = yaml.safe_load(
        (DEMO / "cluster-a" / "50-placement-gate.yaml").read_text(encoding="utf-8")
    )
    pod = job["spec"]["template"]["spec"]
    assert job["kind"] == "Job"
    assert pod["schedulingGates"]
    assert pod["automountServiceAccountToken"] is False
    assert "nodeName" not in pod
