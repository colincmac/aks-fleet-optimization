from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.collectors.metric_queries import render_query

ROOT = Path(__file__).resolve().parents[1]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class PlatformPin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive: str
    archive_sha256: Digest
    binary_sha256: Digest


class ToolPin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    revision: str
    release: str
    platforms: dict[str, PlatformPin]


def tool_pin() -> tuple[ToolPin, str]:
    pin = ToolPin.model_validate(json.loads((ROOT / "eng" / "promtool-lock.json").read_text()))
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Pinned promtool supports only Windows/Linux amd64")
    system = platform.system().lower()
    key = f"{system}-amd64"
    if key not in pin.platforms:
        raise RuntimeError("Pinned promtool supports only Windows/Linux amd64")
    return pin, key


def binary_path() -> Path:
    return ROOT / "eng" / ("promtool.exe" if platform.system() == "Windows" else "promtool")


def verify_tool(path: Path | None = None) -> tuple[Path, ToolPin]:
    pin, key = tool_pin()
    if path is None:
        candidate = binary_path()
        installed = shutil.which("promtool")
        path = candidate if candidate.is_file() else Path(installed) if installed else candidate
    if not path.is_file():
        raise RuntimeError(
            "Required pinned promtool is missing; run scripts/setup_promtool.py --download"
        )
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != pin.platforms[key].binary_sha256:
        raise RuntimeError(
            "promtool checksum differs from the approved platform pin; no execution attempted"
        )
    result = subprocess.run(
        [str(path.resolve()), "--version"], check=True, capture_output=True, text=True, timeout=30
    )
    if f"version {pin.version} " not in result.stdout or pin.revision not in result.stdout:
        raise RuntimeError("promtool version/revision differs from the approved pin")
    return path.resolve(), pin


def _series(metric: str, labels: dict[str, str]) -> str:
    selector = ",".join(f"{key}={json.dumps(value)}" for key, value in sorted(labels.items()))
    return f"{metric}{{{selector}}}"


def _case(
    name: str, expression: str, inputs: list[dict[str, str]], outputs: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "name": name,
        "interval": "1m",
        "input_series": inputs,
        "promql_expr_test": [{"expr": expression, "eval_time": "5m", "exp_samples": outputs}],
    }


def _query_cases() -> list[dict[str, object]]:
    catalog = load_catalog()
    cluster = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/"
        "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
    )
    identities = [
        {
            "azure_resource_id": cluster,
            "namespace": "synthetic",
            "pod": "synthetic-pod",
            "container": "api",
        },
        {
            "azure_resource_id": cluster,
            "namespace": "synthetic",
            "workload_kind": "Deployment",
            "workload": "synthetic",
            "workload_uid": "synthetic-workload-uid",
            "pod_uid": "synthetic-pod-uid",
            "container": "api",
        },
    ]
    cases: list[dict[str, object]] = []
    for index, labels in enumerate(identities):
        selector = _series("", labels)[1:-1]
        cpu = catalog.queries["cpu_usage"].expression.replace("__scope__", selector)
        request = catalog.queries["cpu_request"].expression.replace("__scope__", selector)
        counter = _series("container_cpu_usage_seconds_total", labels)
        cases.append(
            _case(
                f"cpu-rate-{index}",
                cpu,
                [{"series": counter, "values": "0+60x5"}],
                [{"labels": _series("", labels), "value": 1000}],
            )
        )
        cases.append(
            _case(
                f"cpu-reset-{index}",
                cpu,
                [{"series": counter, "values": "0 60 120 0 60 120"}],
                [{"labels": _series("", labels), "value": 750}],
            )
        )
        request_labels = labels | {"resource": "cpu", "unit": "core"}
        gauge = _series("kube_pod_container_resource_requests", request_labels)
        cases.append(
            _case(
                f"request-units-{index}",
                request,
                [{"series": gauge, "values": "1x5"}],
                [{"labels": _series("", request_labels), "value": 1000}],
            )
        )
        cases.append(_case(f"missing-{index}", request, [], []))
        cases.append(
            _case(
                f"stale-{index}",
                request,
                [{"series": gauge, "values": "1 1 1 stale _ _"}],
                [],
            )
        )
        cases.append(
            _case(
                f"foreign-{index}",
                request,
                [
                    {
                        "series": _series(
                            "kube_pod_container_resource_requests",
                            request_labels | {"namespace": "foreign"},
                        ),
                        "values": "1x5",
                    }
                ],
                [],
            )
        )
    labels = identities[1]
    selector = _series("", labels)[1:-1]
    oom = (
        catalog.queries["oom_events"]
        .expression.replace("__scope__", selector)
        .replace("__step__", "300")
    )
    cases.append(
        _case(
            "zero-events-observed",
            oom,
            [{"series": _series("container_oom_events_total", labels), "values": "0x5"}],
            [{"labels": _series("", labels), "value": 0}],
        )
    )
    cases.append(_case("missing-events-not-zero", oom, [], []))
    labels = labels | {"membership_digest": "a" * 64}
    labels.pop("pod_uid")
    inputs = [
        {"series": _series("aks_advisor:approved_roster_complete", labels), "values": "1x5"},
        {
            "series": _series(
                "aks_advisor:approved_member_cpu_mcores", labels | {"pod_uid": "live"}
            ),
            "values": "100x5",
        },
        {
            "series": _series(
                "aks_advisor:approved_member_cpu_mcores", labels | {"pod_uid": "deleted"}
            ),
            "values": "300x5",
        },
    ]
    expression = _series("aks_advisor:workload_container_cpu_max_mcores", labels)
    cases.append(
        _case(
            "approved-roster-max-before-statistics",
            expression,
            inputs,
            [{"labels": expression, "value": 300}],
        )
    )
    inputs = [dict(item) for item in inputs]
    inputs[0]["values"] = "0x5"
    cases.append(_case("partial-roster-not-zero", expression, inputs, []))
    hpa_labels = {
        "azure_resource_id": cluster,
        "namespace": "synthetic",
        "workload_kind": "Deployment",
        "workload": "synthetic",
        "workload_uid": "synthetic-workload-uid",
        "hpa_uid": "synthetic-hpa-one",
    }
    for query in [
        "hpa_min_replicas",
        "hpa_max_replicas",
        "hpa_desired_replicas",
        "hpa_current_replicas",
    ]:
        expression = catalog.queries[query].expression.replace(
            "__scope__", _series("", hpa_labels)[1:-1]
        )
        gauge = _series(f"aks_advisor:{query}", hpa_labels)
        cases.append(
            _case(
                f"{query}-distinct-controller",
                expression,
                [
                    {"series": gauge, "values": "2x5"},
                    {
                        "series": _series(
                            f"aks_advisor:{query}", hpa_labels | {"hpa_uid": "synthetic-hpa-two"}
                        ),
                        "values": "9x5",
                    },
                    {
                        "series": _series(
                            f"aks_advisor:{query}",
                            hpa_labels | {"workload_uid": "synthetic-reused-workload"},
                        ),
                        "values": "7x5",
                    },
                ],
                [{"labels": gauge, "value": 2}],
            )
        )
        cases.append(_case(f"{query}-missing-not-zero", expression, [], []))
        cases.append(
            _case(
                f"{query}-stale-not-current",
                expression,
                [{"series": gauge, "values": "2 2 2 stale _ _"}],
                [],
            )
        )
    return cases


def validate(output_dir: Path) -> None:
    tool, pin = verify_tool()
    catalog = load_catalog()
    output_dir.mkdir(parents=False, exist_ok=False)
    syntax = output_dir / "syntax.yaml"
    labels = {
        "azure_resource_id": "synthetic",
        "namespace": "synthetic",
        "workload_uid": "uid",
        "pod_uid": "uid",
    }
    syntax.write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "advisor-syntax",
                        "rules": [
                            {
                                "record": f"advisor_test:{name}",
                                "expr": render_query(definition.expression, labels, 300),
                            }
                            for name, definition in sorted(catalog.queries.items())
                        ],
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    recordings = sorted(
        (ROOT / "src" / "aks_fleet_efficiency" / "catalog" / "recordings").glob("*.yaml")
    )
    subprocess.run(
        [str(tool), "check", "rules", str(syntax), *(str(path) for path in recordings)],
        check=True,
        timeout=60,
    )
    cases = _query_cases()
    tests = output_dir / "tests.yaml"
    tests.write_text(
        yaml.safe_dump(
            {
                "rule_files": [str(path) for path in recordings],
                "evaluation_interval": "5m",
                "tests": cases,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    subprocess.run([str(tool), "test", "rules", str(tests)], check=True, timeout=60)
    (output_dir / "validation.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "tool_version": pin.version,
                "revision": pin.revision,
                "query_assets": len(catalog.queries),
                "source_profiles": len(catalog.sources),
                "recording_files": len(recordings),
                "expression_cases": len(cases),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Required offline checksum-pinned PromQL validation."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        validate(arguments.output_dir)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"PromQL validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
