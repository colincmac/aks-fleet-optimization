import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "deploy/grafana/aks-cluster-efficiency.json"
SCALING_DASHBOARD = ROOT / "deploy/grafana/aks-rightsizing-scaling-review.json"


def test_cluster_dashboard_binds_all_panels_to_the_selectable_prometheus_source() -> None:
    dashboard = json.loads(DASHBOARD.read_bytes())
    source = next(
        variable for variable in dashboard["templating"]["list"] if variable["name"] == "datasource"
    )
    assert (source["type"], source["query"]) == ("datasource", "prometheus")
    for panel in (panel for panel in dashboard["panels"] if panel["type"] == "timeseries"):
        assert panel["datasource"] == {"type": "prometheus", "uid": "${datasource}"}
        assert all(
            target["range"] and target["datasource"] == panel["datasource"]
            for target in panel["targets"]
        )


def test_cluster_dashboard_keeps_grafana_discovery_cascaded() -> None:
    dashboard = json.loads(DASHBOARD.read_bytes())
    variables = {variable["name"]: variable for variable in dashboard["templating"]["list"]}
    assert variables["cluster"]["query"] == 'label_values(up{job="cadvisor"}, cluster)'
    assert 'cluster="$cluster"' in variables["namespace"]["query"]
    assert 'namespace="$namespace"' in variables["pod"]["query"]
    assert 'cluster="$cluster"' in variables["pod"]["query"]


def test_cluster_dashboard_queries_exclude_other_scopes_and_preserve_missing_data(
    tmp_path: Path,
) -> None:
    dashboard = json.loads(DASHBOARD.read_bytes())
    cases = []
    panels = {
        panel["title"]: panel for panel in dashboard["panels"] if panel["type"] == "timeseries"
    }
    for title, expected_values in {
        "CPU": {"A": 8, "B": 6, "C": 9},
        "Memory": {"A": 512, "D": 328},
        "Namespace CPU": {"A": 5},
        "Namespace memory": {"B": 228},
        "Pod CPU": {"A": 2},
        "Pod memory": {"B": 128},
    }.items():
        panel = panels[title]
        for query in panel["targets"]:
            expression = (
                query["expr"]
                .replace("$cluster", "pilot")
                .replace("$namespace", "app")
                .replace("$pod", "api")
            )
            expected = expected_values.get(query["refId"])
            cases.append(
                {
                    "expr": expression,
                    "eval_time": "5m",
                    "exp_samples": []
                    if expected is None
                    else [{"labels": "{}", "value": expected}],
                }
            )
            for selection in ('cluster="pilot"', 'namespace="app"', 'pod="api"'):
                if selection in expression:
                    cases.append(
                        {
                            "expr": expression.replace(selection, selection.split('"')[0] + '""'),
                            "eval_time": "5m",
                            "exp_samples": [],
                        }
                    )
    fixture = {
        "evaluation_interval": "1m",
        "tests": [
            {
                "interval": "1m",
                "input_series": [
                    {"series": series, "values": f"{value}+0x5"}
                    for series, value in (
                        (
                            'kube_node_status_capacity{cluster="pilot",resource="cpu",unit="core"}',
                            8,
                        ),
                        (
                            'kube_node_status_capacity{cluster="other",resource="cpu",unit="core"}',
                            99,
                        ),
                        ('kube_node_status_capacity{resource="cpu",unit="core"}', 99),
                        (
                            'kube_node_status_allocatable{cluster="pilot",resource="cpu",unit="core"}',
                            6,
                        ),
                        (
                            'kube_pod_container_resource_requests{cluster="pilot",'
                            'namespace="app",pod="api",container="api",resource="cpu",unit="core"}',
                            2,
                        ),
                        (
                            'kube_pod_container_resource_requests{cluster="pilot",'
                            'namespace="app",pod="worker",container="app",resource="cpu",unit="core"}',
                            3,
                        ),
                        (
                            'kube_pod_container_resource_requests{cluster="pilot",'
                            'namespace="other",pod="api",container="api",resource="cpu",unit="core"}',
                            4,
                        ),
                        (
                            'container_cpu_usage_seconds_total{cluster="other",'
                            'namespace="app",pod="api",container="api"}',
                            10,
                        ),
                        (
                            'kube_node_status_capacity{cluster="pilot",resource="memory",unit="byte"}',
                            512,
                        ),
                        (
                            'container_memory_working_set_bytes{cluster="pilot",'
                            'namespace="app",pod="api",container="api"}',
                            128,
                        ),
                        (
                            'container_memory_working_set_bytes{cluster="pilot",'
                            'namespace="app",pod="api",container="POD"}',
                            99,
                        ),
                        (
                            'container_memory_working_set_bytes{cluster="pilot",'
                            'namespace="app",pod="worker",container="app"}',
                            100,
                        ),
                        (
                            'container_memory_working_set_bytes{cluster="pilot",'
                            'namespace="other",pod="api",container="api"}',
                            100,
                        ),
                        (
                            'container_memory_working_set_bytes{cluster="other",'
                            'namespace="app",pod="api",container="api"}',
                            100,
                        ),
                    )
                ],
                "promql_expr_test": cases,
            }
        ],
    }
    _evaluate_dashboard(tmp_path, fixture)


def test_scaling_dashboard_distinguishes_bound_states_and_missing_samples(tmp_path: Path) -> None:
    dashboard = json.loads(SCALING_DASHBOARD.read_bytes())
    queries = {
        target["legendFormat"]: (
            target["expr"]
            .replace("$cluster", "pilot")
            .replace("$namespace", "app")
            .replace("$hpa", "api")
        )
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    labels = '{cluster="pilot",horizontalpodautoscaler="api",namespace="app"}'
    inputs = []
    for metric, values in {
        "status_desired_replicas": "2 4 5 5 5 5 6 2 2 -1 2.5 2",
        "status_current_replicas": "2 3 5 5 stale 6 6 2 2 2 2 2",
        "spec_min_replicas": "2 2 2 5 2 7 2 2 2 2 2 2",
        "spec_max_replicas": "5 5 5 5 5 4 5 5 5 5 5 5",
    }.items():
        name = f"kube_horizontalpodautoscaler_{metric}"
        inputs.extend(
            [
                {"series": name + labels, "values": values},
                {"series": name + labels.replace('"pilot"', '"other"'), "values": "99+0x6"},
                {"series": name + labels.replace('"app"', '"other"'), "values": "99+0x6"},
                {"series": name + labels.replace('"api"', '"other"'), "values": "99+0x6"},
            ]
        )
    for metric in ("status_desired_replicas", "status_current_replicas"):
        inputs.append(
            {
                "series": (
                    f'kube_horizontalpodautoscaler_{metric}{labels[:-1]},replica="duplicate"}}'
                ),
                "values": "_ _ _ _ _ _ _ 2 stale _ _ _",
            }
        )
    inputs.append(
        {
            "series": (
                f'kube_horizontalpodautoscaler_spec_max_replicas{labels[:-1]},replica="second"}}'
            ),
            "values": "_ _ _ _ _ _ _ _ _ _ _ 5",
        }
    )
    cases = []
    for label, expected in {
        "Desired": [2, 4, 5, 5, 5, 5, 6, None, 2, None, None, 2],
        "Current": [2, 3, 5, 5, None, 6, 6, None, 2, 2, 2, 2],
        "Minimum": [2, 2, 2, 5, 2, 7, 2, 2, 2, 2, 2, 2],
        "Maximum": [5, 5, 5, 5, 5, 4, 5, 5, 5, 5, 5, None],
        "Desired minus current": [0, 1, 0, 0, None, -1, 0, None, 0, None, None, 0],
        "Bound state": [1, 0, 2, 3, None, None, None, None, 1, None, None, None],
    }.items():
        for minute, value in enumerate(expected):
            cases.append(
                {
                    "expr": queries[label],
                    "eval_time": f"{minute}m",
                    "exp_samples": [] if value is None else [{"labels": labels, "value": value}],
                }
            )
        for selector in ('cluster="pilot"', 'namespace="app"', 'horizontalpodautoscaler="api"'):
            cases.append(
                {
                    "expr": queries[label].replace(selector, selector.split('"')[0] + '""'),
                    "eval_time": "1m",
                    "exp_samples": [],
                }
            )
    _evaluate_dashboard(
        tmp_path, {"tests": [{"interval": "1m", "input_series": inputs, "promql_expr_test": cases}]}
    )


def _evaluate_dashboard(tmp_path: Path, fixture: dict[str, object]) -> None:
    promtool = ROOT / "eng/promtool.exe"
    if not promtool.is_file():
        promtool = ROOT / "eng/promtool"
    if not promtool.is_file():
        pytest.skip("Install the repository-pinned promtool to evaluate dashboard expressions")
    path = tmp_path / "dashboard.test.yaml"
    path.write_text(yaml.safe_dump(fixture), encoding="utf-8")
    result = subprocess.run(
        [str(promtool), "test", "rules", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
