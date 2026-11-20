import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import yaml
from pytest import MonkeyPatch
from typer.testing import CliRunner

from aks_fleet_efficiency import cli
from aks_fleet_efficiency.models import AzureInventorySnapshot, KubernetesMetadataSnapshot

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "history-example"
PUBLISHER = ROOT / "scripts/publish_headlamp_assessments.py"
FIXTURE = (
    ROOT
    / "plugins/headlamp-fleet-efficiency/preview-public/assessment-preview"
    / "assessments.json"
)
TENANT = "00000000-0000-0000-0000-000000000000"


def _publish(
    output: Path, *bundles: Path, tenant: str = TENANT
) -> subprocess.CompletedProcess[str]:
    arguments = [sys.executable, str(PUBLISHER), "--tenant", tenant, "--output", str(output)]
    for bundle in bundles:
        arguments.extend(("--bundle", str(bundle)))
    return subprocess.run(arguments, capture_output=True, text=True, timeout=30, check=False)


def test_headlamp_publication_matches_synthetic_preview(tmp_path: Path) -> None:
    output = tmp_path / "assessments.json"
    result = _publish(output, BUNDLE)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == FIXTURE.read_bytes()
    cluster = json.loads(output.read_bytes())["clusters"][0]
    assert cluster["status"] == "partial"
    assert cluster["namespaces"][0]["workloads"][0]["uid"] == "workload-uid"
    assert {item["state"] for item in cluster["findings"]} == {"finding", "blocked"}
    assert b"synthetic-owner" not in output.read_bytes()
    assert b"estimated_monthly_savings" not in output.read_bytes()


def test_bad_publication_does_not_replace_last_good_feed(tmp_path: Path) -> None:
    output = tmp_path / "assessments.json"
    assert _publish(output, BUNDLE).returncode == 0
    original = output.read_bytes()
    invalid = tmp_path / "tampered"
    shutil.copytree(BUNDLE, invalid)
    with (invalid / "assessment.json").open("ab") as handle:
        handle.write(b" ")
    results = (
        _publish(output, invalid),
        _publish(output, BUNDLE, BUNDLE),
        _publish(output, BUNDLE, tenant="00000000-0000-0000-0000-000000000001"),
        _publish(invalid / "assessments.json", invalid),
    )
    assert all(result.returncode == 1 for result in results)
    assert output.read_bytes() == original
    assert not (invalid / "assessments.json").exists()


def _batch(tmp_path: Path) -> tuple[list[str], Path, Path]:
    archive = tmp_path / "runs"
    archive.mkdir()
    feed = tmp_path / "assessments.json"
    profile = tmp_path / "batch.json"
    targets = []
    for index in range(2):
        name = f"aks-synthetic-{index}"
        config = tmp_path / f"cluster-{index}.yaml"
        fragments = tmp_path / f"cluster-{index}.json"
        config.write_text(
            (ROOT / "examples/cpu-pack-config.yaml")
            .read_text(encoding="utf-8")
            .replace("aks-synthetic", name),
            encoding="utf-8",
        )
        fragments.write_text(
            (ROOT / "examples/fixtures/history-assessment.json")
            .read_text(encoding="utf-8")
            .replace("aks-synthetic", name)
            .replace("synthetic-cluster-uid", f"synthetic-cluster-{index}"),
            encoding="utf-8",
        )
        targets.append(
            {
                "config": config.name,
                "fragments": fragments.name,
                "cluster_uid": f"synthetic-cluster-{index}",
            }
        )
    profile.write_text(json.dumps({"tenant_id": TENANT, "targets": targets}), encoding="utf-8")
    return (
        ["assess-batch", "--batch", str(profile), "--artifacts", str(archive), "--feed", str(feed)],
        archive,
        feed,
    )


def test_batch_publishes_all_targets_and_preserves_feed_on_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, archive, feed = _batch(tmp_path)
    clock = datetime(2026, 10, 29, 12, tzinfo=UTC)
    monkeypatch.setattr(cli, "datetime", Mock(now=lambda _zone: clock))
    runner = CliRunner()
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 3, result.output
    before = feed.read_bytes()
    status = feed.with_name("assessments-status.json")
    assert json.loads(status.read_bytes()) == {
        "schemaVersion": "1",
        "attemptedAt": clock.isoformat(),
        "outcome": "partial",
        "staleAfterHours": 26,
    }
    assert [item["name"] for item in json.loads(before)["clusters"]] == [
        "aks-synthetic-0",
        "aks-synthetic-1",
    ]
    run = next(archive.iterdir())
    assert len(list(run.glob("*/manifest.json"))) == 2
    assert _publish(tmp_path / "republished.json", *sorted(run.iterdir())).returncode == 0
    assert (tmp_path / "republished.json").read_bytes() == before

    clock += timedelta(hours=1)
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 3, result.output
    before = feed.read_bytes()
    assert len(list(archive.iterdir())) == 2
    assert json.loads(status.read_bytes())["attemptedAt"] == clock.isoformat()

    clock += timedelta(days=2)
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2, result.output
    assert "stale" in result.output
    assert feed.read_bytes() == before
    assert json.loads(status.read_bytes()) == {
        "schemaVersion": "1",
        "attemptedAt": clock.isoformat(),
        "outcome": "failed",
        "staleAfterHours": 26,
    }


def test_batch_refuses_wrong_fingerprint_and_concurrent_writer(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, _, feed = _batch(tmp_path)
    monkeypatch.setattr(
        cli, "datetime", Mock(now=lambda _zone: datetime(2026, 10, 29, 12, tzinfo=UTC))
    )
    profile = tmp_path / "batch.json"
    profile.write_text(
        profile.read_text(encoding="utf-8").replace("synthetic-cluster-1", "other-cluster"),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2, result.output
    assert "fingerprint" in result.output
    assert not feed.exists()

    lock = feed.with_name(f".{feed.name}.lock")
    lock.mkdir()
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 1, result.output
    assert "locked" in result.output
    assert lock.is_dir()
    assert not feed.exists()
    assert json.loads(feed.with_name("assessments-status.json").read_bytes())["outcome"] == "failed"


def test_scheduled_slot_retries_and_rejects_late_jobs(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, archive, feed = _batch(tmp_path)
    clock = datetime(2026, 10, 29, 12, tzinfo=UTC)
    monkeypatch.setattr(cli, "datetime", Mock(wraps=datetime, now=lambda _zone: clock))
    runner = CliRunner()
    slot = [*args, "--slot", "2026-10-29T11:00:00Z"]
    result = runner.invoke(cli.app, slot)
    assert result.exit_code == 3, result.output
    before = feed.read_bytes()
    status = feed.with_name("assessments-status.json")
    status_before = status.read_bytes()
    status.unlink()
    clock += timedelta(hours=1)
    result = runner.invoke(cli.app, slot)
    assert result.exit_code == 3, result.output
    assert "already published" in result.output
    assert len(list(archive.iterdir())) == 1
    assert status.read_bytes() == status_before

    clock += timedelta(days=2)
    result = runner.invoke(cli.app, [*args, "--slot", "2026-10-31T11:00:00Z"])
    assert result.exit_code == 2, result.output
    failed = status.read_bytes()
    for rejected in (slot, args):
        result = runner.invoke(cli.app, rejected)
        assert result.exit_code == 2, result.output
        assert status.read_bytes() == failed
        assert feed.read_bytes() == before


def test_failed_slot_can_retry_after_input_producer_recovers(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, archive, feed = _batch(tmp_path)
    clock = datetime(2026, 10, 29, 12, tzinfo=UTC)
    monkeypatch.setattr(cli, "datetime", Mock(wraps=datetime, now=lambda _zone: clock))
    args.extend(("--slot", "2026-10-29T11:00:00Z"))
    fragments = tmp_path / "cluster-1.json"
    original = fragments.read_bytes()
    fragments.write_bytes(b"{}")
    runner = CliRunner()
    assert runner.invoke(cli.app, args).exit_code == 2
    assert not feed.exists()
    fragments.write_bytes(original)
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 3, result.output
    assert feed.exists()
    assert len(list(archive.iterdir())) == 2


def test_scheduled_input_window_distinguishes_fresh_inputs_from_producer_outage(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, archive, feed = _batch(tmp_path)
    batch_path = tmp_path / "batch.json"
    batch = json.loads(batch_path.read_bytes())
    batch["slot_input_window_minutes"] = 60
    batch["targets"] = batch["targets"][:1]
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    config = tmp_path / "cluster-0.yaml"
    profile = yaml.safe_load(config.read_bytes())
    profile["analysis"] = {"mode": "baseline", "packs": ["AKS-NP-002"]}
    config.write_text(json.dumps(profile), encoding="utf-8")
    incoming = tmp_path / "cluster-0.json"
    fixture = json.loads(incoming.read_bytes())
    fixture["metrics"] = []
    fixture["workload_assessments"] = []
    now = datetime(2026, 10, 29, 12, tzinfo=UTC)
    monkeypatch.setattr(cli, "datetime", Mock(wraps=datetime, now=lambda _zone: now))
    runner = CliRunner()

    def stage(
        observed_at: datetime,
        *,
        kube_observed_at: datetime | None = None,
        slot: datetime | None = None,
        expected: int = 0,
    ) -> None:
        prior = incoming.read_bytes() if incoming.exists() else None
        inventory = tmp_path / "azure.json"
        metadata = tmp_path / "metadata.json"
        for path, source, source_time in (
            (inventory, fixture["azure"][0], observed_at),
            (metadata, fixture["kubernetes"][0], kube_observed_at or observed_at),
        ):
            timestamp = source_time.isoformat()
            source["generated_at"] = timestamp
            receipt = source["collection"]
            receipt.update(
                started_at=timestamp, completed_at=timestamp, source_observed_at=timestamp
            )
            path.write_text(json.dumps(source), encoding="utf-8")
        result = runner.invoke(
            cli.app,
            [
                "stage-assessment-input",
                "--batch",
                str(batch_path),
                "--inventory",
                str(inventory),
                "--metadata",
                str(metadata),
                "--slot",
                (slot or now).isoformat(),
            ],
        )
        assert result.exit_code == expected, result.output
        if expected != 0:
            assert (incoming.read_bytes() if incoming.exists() else None) == prior
        else:
            staged = json.loads(incoming.read_bytes())
            assert AzureInventorySnapshot.model_validate(
                staged["azure"][0]
            ) == AzureInventorySnapshot.model_validate(fixture["azure"][0])
            assert KubernetesMetadataSnapshot.model_validate(
                staged["kubernetes"][0]
            ) == KubernetesMetadataSnapshot.model_validate(fixture["kubernetes"][0])
            assert staged["metrics"] == []

    def run(slot: datetime | None = None) -> int:
        result = runner.invoke(cli.app, [*args, "--slot", (slot or now).isoformat()])
        assert result.exit_code in {0, 3} or "input window" in result.output, result.output
        return result.exit_code

    incoming.unlink()
    stage(now - timedelta(hours=1), expected=2)  # The left edge is not part of this slot.
    assert not incoming.exists()
    assert runner.invoke(cli.app, [*args, "--slot", now.isoformat()]).exit_code == 2
    assert not feed.exists()
    stage(now - timedelta(minutes=15))
    assert run() in {0, 3}
    existing = set(archive.glob("*/cluster-01"))
    now += timedelta(hours=2)
    stage(now)
    assert run() in {0, 3}
    protected = feed.read_bytes()
    status = feed.with_name("assessments-status.json")
    attempted_at = json.loads(status.read_bytes())["attemptedAt"]
    (original,) = set(archive.glob("*/cluster-01")) - existing

    # The producer is down. Its previous inputs still pass the ordinary 24-hour age gate.
    now += timedelta(hours=2)
    assert run() == 2
    assert feed.read_bytes() == protected
    assert json.loads(status.read_bytes())["outcome"] == "failed"
    assert json.loads(status.read_bytes())["attemptedAt"] != attempted_at

    # Only Azure recovered; the independently stale Kubernetes clock still blocks publication.
    stage(now - timedelta(minutes=5), kube_observed_at=now - timedelta(hours=2), expected=2)
    assert run() == 2
    assert feed.read_bytes() == protected
    recovery_slot = now
    now += timedelta(minutes=10)  # A retry starts later, but the original slot cannot move.
    stage(now, slot=recovery_slot, expected=2)
    assert run(recovery_slot) == 2
    assert feed.read_bytes() == protected
    stage(recovery_slot - timedelta(minutes=5), slot=recovery_slot)
    assert run(recovery_slot) in {0, 3}
    assert feed.read_bytes() != protected
    assert _publish(tmp_path / "replayed.json", original).returncode == 0
    assert (tmp_path / "replayed.json").read_bytes() == protected
    stage(
        recovery_slot - timedelta(hours=2),
        slot=recovery_slot - timedelta(hours=2),
        expected=2,
    )
    fixture["kubernetes"][0]["cluster_uid"] = "unexpected-fingerprint"
    stage(recovery_slot, slot=recovery_slot, expected=2)


def test_slot_input_window_requires_a_slot_and_rejects_overlap(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, _, feed = _batch(tmp_path)
    profile = tmp_path / "batch.json"
    batch = json.loads(profile.read_bytes())
    batch["slot_input_window_minutes"] = 60
    profile.write_text(json.dumps(batch), encoding="utf-8")
    now = datetime(2026, 10, 29, 12, tzinfo=UTC)
    monkeypatch.setattr(cli, "datetime", Mock(wraps=datetime, now=lambda _zone: now))
    runner = CliRunner()
    assert runner.invoke(cli.app, args).exit_code == 2
    result = runner.invoke(cli.app, [*args, "--slot", now.isoformat()])
    assert result.exit_code == 2 and "input window" in result.output
    now += timedelta(minutes=30)
    result = runner.invoke(cli.app, [*args, "--slot", now.isoformat()])
    assert result.exit_code == 2 and "overlap" in result.output
    assert not feed.exists()


def test_opt_in_publishes_good_clusters_and_labels_missing_or_retained_evidence(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    args, _, feed = _batch(tmp_path)
    clock = datetime(2026, 10, 29, 12, tzinfo=UTC)
    monkeypatch.setattr(cli, "datetime", Mock(wraps=datetime, now=lambda _zone: clock))
    profile = tmp_path / "batch.json"
    profile.write_text(
        json.dumps(json.loads(profile.read_bytes()) | {"allow_mixed_age": True}),
        encoding="utf-8",
    )
    fragments = tmp_path / "cluster-1.json"
    original = fragments.read_bytes()
    fragments.write_bytes(b"{}")
    runner = CliRunner()

    def invoke() -> tuple[list[dict[str, object]], list[str]]:
        result = runner.invoke(cli.app, [*args, "--slot", clock.isoformat()])
        assert result.exit_code == 3, result.output
        data = json.loads(feed.read_bytes())
        return data["clusters"], data.get("failedClusters", [])

    current, missing = invoke()
    assert len(current) == 1
    assert missing[0].endswith("aks-synthetic-1")

    fragments.write_bytes(original)
    clock += timedelta(hours=1)
    prior, _ = invoke()
    fragments.write_bytes(b"{}")
    clock += timedelta(hours=1)
    current, failed = invoke()
    assert len(current) == 2
    assert current[1] == prior[1]
    assert current[0]["evaluatedAt"] != prior[0]["evaluatedAt"]
    assert failed == missing

    profile.write_text(
        profile.read_text(encoding="utf-8").replace("synthetic-cluster-1\"", "replacement-uid\""),
        encoding="utf-8",
    )
    clock += timedelta(hours=1)
    replaced, failed = invoke()
    assert len(replaced) == 1
    assert failed == missing
    before = feed.read_bytes()
    (tmp_path / "cluster-0.json").write_bytes(b"{}")
    clock += timedelta(hours=1)
    result = runner.invoke(cli.app, [*args, "--slot", clock.isoformat()])
    assert result.exit_code == 2, result.output
    assert feed.read_bytes() == before
