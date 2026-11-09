from __future__ import annotations

import json
import shutil
import socket
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aks_fleet_efficiency import history
from aks_fleet_efficiency.artifacts import read_model, write_assessment_artifacts
from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import load_onboarding_config
from aks_fleet_efficiency.history import HistoryRun, HistoryStore, HistoryTrend
from aks_fleet_efficiency.rules.engine import analyze

ROOT = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000000"
LATER = datetime.fromisoformat("2026-10-29T13:00:00Z")


def write_run(
    tmp_path: Path,
    name: str,
    *,
    change: Callable[[dict[str, Any]], None] | None = None,
    baseline: bool = False,
    as_of: datetime = LATER,
) -> Path:
    payload = json.loads((ROOT / "examples/fixtures/pool-assessment.json").read_text())
    if change is not None:
        change(payload)
    profile = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml")
    if baseline:
        profile.analysis.mode = "baseline"
    fragments = AssessmentFragments.model_validate(payload)
    assessment = assess_fragments(fragments, profile, as_of=as_of)
    directory = tmp_path / name
    write_assessment_artifacts(directory, fragments, assessment, profile.analysis)
    return directory


@pytest.fixture
def artifacts(tmp_path: Path) -> Path:
    profile = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml")
    fragments = read_model(ROOT / "examples/fixtures/pool-assessment.json", AssessmentFragments)
    assessment = assess_fragments(
        fragments, profile, as_of=datetime.fromisoformat("2026-10-29T12:00:00Z")
    )
    directory = tmp_path / "artifacts"
    write_assessment_artifacts(directory, fragments, assessment, profile.analysis)
    return directory


def test_import_is_immutable_and_idempotent(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    first = store.import_assessment(artifacts)
    original = {path.name: path.read_bytes() for path in store.directory.iterdir()}
    assert store.import_assessment(artifacts) == first
    assert {path.name: path.read_bytes() for path in store.directory.iterdir()} == original
    assert len(store.list_runs()) == 1
    assert first.savings is None


def test_corrupt_artifact_never_creates_store(artifacts: Path, tmp_path: Path) -> None:
    assessment = artifacts / "assessment.json"
    payload = json.loads(assessment.read_text(encoding="utf-8"))
    payload["status"] = "partial"
    assessment.write_text(json.dumps(payload), encoding="utf-8")
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    with pytest.raises(ValueError, match="integrity"):
        store.import_assessment(artifacts)
    assert not store.directory.exists()


def test_runs_survive_restart_and_sort_by_evaluation_time(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    later = store.import_assessment(write_run(tmp_path, "later"))
    earlier = store.import_assessment(artifacts)
    reopened = HistoryStore(store.directory, tenant_id=TENANT)
    assert reopened.list_runs() == [earlier, later]
    trend = reopened.compare(earlier.run_id, later.run_id)
    assert trend.comparable
    assert any(item.state == "persistent" for item in trend.findings)
    assert set(item.state for item in trend.findings) <= {"persistent", "blocked"}
    assert trend.savings is None
    assert HistoryTrend.model_validate_json(trend.model_dump_json()) == trend
    for item in trend.findings:
        if item.state == "persistent":
            assert item.first_observed_at == earlier.generated_at
            assert item.last_observed_at == later.generated_at


def test_missing_metrics_block_instead_of_resolving(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    earlier = store.import_assessment(artifacts)
    later = store.import_assessment(
        write_run(tmp_path, "missing", change=lambda payload: payload.update(metrics=[]))
    )
    trend = store.compare(earlier.run_id, later.run_id)
    assert later.status == "partial"
    assert trend.comparable
    pools = [item for item in trend.findings if item.rule_id == "AKS-NP-001"]
    assert {item.state for item in pools} == {"not_observed"}
    prior = next(item for item in pools if item.state == "not_observed")
    assert prior.last_observed_at == earlier.generated_at


def test_stale_replay_records_blocked_not_resolution(artifacts: Path, tmp_path: Path) -> None:
    assessment = read_model(artifacts / "assessment.json", OfflineAssessment)
    fragments = read_model(artifacts / "fragments.json", AssessmentFragments)
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    assessment.report = analyze(assessment.snapshot, config, as_of=LATER + timedelta(days=2))
    stale = tmp_path / "stale"
    write_assessment_artifacts(stale, fragments, assessment, config)
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    earlier = store.import_assessment(artifacts)
    later = store.import_assessment(stale)
    trend = store.compare(earlier.run_id, later.run_id)
    pool = next(item for item in trend.findings if item.rule_id == "AKS-NP-001")
    assert trend.comparable
    assert pool.state == "blocked"
    assert pool.last_observed_at == earlier.generated_at


def test_absent_signal_is_not_observed_never_resolved(artifacts: Path, tmp_path: Path) -> None:
    def high_usage(payload: dict[str, Any]) -> None:
        for observation in payload["metrics"][0]["observations"]:
            if observation["metric"] in {"pool_cpu_usage", "node_cpu_usage"}:
                for field in ["minimum", "p50", "p95", "p99", "maximum"]:
                    observation[field] = 100000
                observation["quality"].update(minimum=100000, maximum=100000)

    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    earlier = store.import_assessment(artifacts)
    later = store.import_assessment(write_run(tmp_path, "high", change=high_usage))
    trend = store.compare(earlier.run_id, later.run_id)
    pool = next(item for item in trend.findings if item.rule_id == "AKS-NP-001")
    assert pool.state == "not_observed"
    assert pool.last_observed_at == earlier.generated_at


def test_configuration_change_is_not_comparable(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    earlier = store.import_assessment(artifacts)
    later = store.import_assessment(write_run(tmp_path, "baseline", baseline=True))
    trend = store.compare(earlier.run_id, later.run_id)
    assert not trend.comparable
    assert {item.state for item in trend.findings} == {"not_comparable"}


@pytest.mark.parametrize("operation", ["import", "list", "compare"])
def test_wrong_tenant_fails_closed(artifacts: Path, tmp_path: Path, operation: str) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    run = store.import_assessment(artifacts)
    other = HistoryStore(store.directory, tenant_id="11111111-1111-1111-1111-111111111111")
    with pytest.raises(ValueError, match="tenant"):
        if operation == "import":
            other.import_assessment(artifacts)
        elif operation == "list":
            other.list_runs()
        else:
            other.compare(run.run_id, run.run_id)
    assert store.list_runs() == [run]


@pytest.mark.parametrize("run_id", ["../escape", "a" * 63, "A" * 64, "f" * 64])
def test_invalid_or_missing_run_ids_do_not_escape(
    artifacts: Path, tmp_path: Path, run_id: str
) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    run = store.import_assessment(artifacts)
    with pytest.raises(ValueError):
        store.compare(run.run_id, run_id)


def test_tampered_stored_record_is_not_skipped(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    run = store.import_assessment(artifacts)
    path = store.directory / f"{run.run_id}.json"
    payload = json.loads(path.read_text())
    payload["payloads"]["report.md"] += "corrupt"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity"):
        store.list_runs()
    with pytest.raises(ValueError, match="integrity"):
        store.import_assessment(artifacts)


@pytest.mark.parametrize("reverse", [False, True])
def test_time_order_is_explicit(artifacts: Path, tmp_path: Path, reverse: bool) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    earlier = store.import_assessment(artifacts)
    later = store.import_assessment(write_run(tmp_path, "later"))
    with pytest.raises(ValueError, match="ordered"):
        store.compare(later.run_id if reverse else earlier.run_id, earlier.run_id)


@pytest.mark.parametrize("name", ["../escape", "extra.json", "snapshot.json"])
def test_manifest_file_allowlist(artifacts: Path, tmp_path: Path, name: str) -> None:
    path = artifacts / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"][name] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="integrity"):
        HistoryStore(tmp_path / "history", tenant_id=TENANT).import_assessment(artifacts)


def test_rehashed_forged_report_fails_replay(artifacts: Path, tmp_path: Path) -> None:
    path = artifacts / "assessment.json"
    payload = json.loads(path.read_text())
    payload["report"]["recommendations"][0]["summary"] = "forged"
    encoded = json.dumps(payload).encode()
    path.write_bytes(encoded)
    manifest_path = artifacts / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["assessment.json"] = sha256(encoded).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="replay"):
        HistoryStore(tmp_path / "history", tenant_id=TENANT).import_assessment(artifacts)


def test_bounded_inputs_and_store(
    artifacts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    monkeypatch.setattr(history, "MAXIMUM_ARTIFACT_BYTES", 8)
    with pytest.raises(ValueError, match="byte limit"):
        store.import_assessment(artifacts)
    assert not store.directory.exists()
    monkeypatch.undo()
    run = store.import_assessment(artifacts)
    monkeypatch.setattr(history, "MAXIMUM_RUNS", 1)
    assert store.import_assessment(artifacts) == run
    later = write_run(tmp_path, "later")
    with pytest.raises(ValueError, match="limits"):
        store.import_assessment(later)
    assert store.list_runs() == [run]
    monkeypatch.setattr(history, "MAXIMUM_STORE_BYTES", 1)
    with pytest.raises(ValueError, match="limits"):
        store.list_runs()


def test_empty_list_is_read_only_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", denied)
    store = HistoryStore(tmp_path / "missing", tenant_id=TENANT)
    assert store.list_runs() == []
    assert not store.directory.exists()


def test_cli_import_list_compare_and_redaction(artifacts: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    options = ["--store", str(tmp_path / "history"), "--tenant", TENANT]
    first = runner.invoke(app, ["history", "import", "--artifacts", str(artifacts), *options])
    assert first.exit_code == 0, first.output
    earlier = HistoryRun.model_validate_json(first.stdout)
    later_directory = write_run(tmp_path, "later")
    second = runner.invoke(
        app, ["history", "import", "--artifacts", str(later_directory), *options]
    )
    assert second.exit_code == 0, second.output
    later = HistoryRun.model_validate_json(second.stdout)
    listing = runner.invoke(app, ["history", "list", *options])
    assert listing.exit_code == 0, listing.output
    assert [item["run_id"] for item in json.loads(listing.stdout)] == [earlier.run_id, later.run_id]
    comparison = runner.invoke(
        app,
        ["history", "compare", *options, "--previous", earlier.run_id, "--current", later.run_id],
    )
    assert comparison.exit_code == 0, comparison.output
    assert HistoryTrend.model_validate_json(comparison.stdout).comparable
    invalid = runner.invoke(
        app,
        [
            "history",
            "compare",
            *options,
            "--previous",
            "SENSITIVE-INVALID",
            "--current",
            later.run_id,
        ],
    )
    assert invalid.exit_code == 2
    assert "SENSITIVE-INVALID" not in invalid.output


def test_restored_store_retains_original_artifacts(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    run = store.import_assessment(artifacts)
    restored = tmp_path / "restored"
    shutil.copytree(store.directory, restored)
    shutil.rmtree(store.directory)
    assert HistoryStore(restored, tenant_id=TENANT).list_runs() == [run]
    archive = json.loads((restored / f"{run.run_id}.json").read_text())
    for name, text in archive["payloads"].items():
        assert text.encode() == (artifacts / name).read_bytes()


def test_failed_publication_leaves_no_visible_run(
    artifacts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    real_link = history.os.link

    def failed(source: Path, destination: Path) -> None:
        if destination.name != "store.json":
            raise OSError("synthetic publication failure")
        real_link(source, destination)

    monkeypatch.setattr(history.os, "link", failed)
    with pytest.raises(OSError):
        store.import_assessment(artifacts)
    assert store.list_runs() == []
    assert [item.name for item in store.directory.iterdir()] == ["store.json"]
    monkeypatch.undo()
    assert len(store.import_assessment(artifacts).run_id) == 64


def test_unsupported_store_schema_is_rejected(artifacts: Path, tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    store.import_assessment(artifacts)
    identity = store.directory / "store.json"
    payload = json.loads(identity.read_text())
    payload["schema_version"] = "99.0"
    identity.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        store.list_runs()


def test_history_schema_contracts() -> None:
    for name, model in [("history-run", HistoryRun), ("history-trend", HistoryTrend)]:
        assert (
            json.loads((ROOT / f"schemas/{name}.schema.json").read_text())
            == model.model_json_schema()
        )


@pytest.mark.parametrize("source", ["azure", "kubernetes", "metrics", "retained-metadata"])
def test_original_fragment_tenants_cannot_be_resealed(
    artifacts: Path, tmp_path: Path, source: str
) -> None:
    fragments = read_model(artifacts / "fragments.json", AssessmentFragments)
    assessment = read_model(artifacts / "assessment.json", OfflineAssessment)
    foreign = "11111111-1111-1111-1111-111111111111"
    if source == "azure":
        fragments.azure[0].tenant_id = foreign
    elif source == "kubernetes":
        fragments.kubernetes[0].tenant_id = foreign
    elif source == "metrics":
        fragments.metrics[0].tenant_id = foreign
    else:
        assessment.metadata_evidence[0].tenant_id = foreign
    assessment.input_digest = sha256(
        json.dumps(
            fragments.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    resealed = tmp_path / "resealed"
    config = load_onboarding_config(ROOT / "examples/pool-assessment-config.yaml").analysis
    write_assessment_artifacts(resealed, fragments, assessment, config)
    store = HistoryStore(tmp_path / "history", tenant_id=TENANT)
    with pytest.raises(ValueError, match="tenant"):
        store.import_assessment(resealed)
    assert not store.directory.exists()
