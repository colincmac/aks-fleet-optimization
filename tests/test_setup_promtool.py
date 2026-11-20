from __future__ import annotations

import hashlib
import importlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

VERSION = "9.8.7-rc.1"
REVISION = "a" * 40


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("setup_promtool")
    monkeypatch.setattr(module, "ROOT", tmp_path, raising=False)
    (tmp_path / "eng").mkdir()
    (tmp_path / "eng" / "promtool-lock.json").write_text("original lock\n")
    return module


def release_files() -> dict[str, bytes]:
    files = {
        f"https://api.github.com/repos/prometheus/prometheus/commits/v{VERSION}": json.dumps(
            {"sha": REVISION}
        ).encode()
    }
    base = f"https://github.com/prometheus/prometheus/releases/download/v{VERSION}"
    checksums = []
    for key in ("windows-amd64", "linux-amd64"):
        suffix = ".exe" if key.startswith("windows") else ""
        member = f"prometheus-{VERSION}.{key}/promtool{suffix}"
        binary = f"synthetic {key} binary".encode()
        buffer = io.BytesIO()
        extension = "zip" if suffix else "tar.gz"
        if suffix:
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(member, binary)
        else:
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                info = tarfile.TarInfo(member)
                info.size = len(binary)
                archive.addfile(info, io.BytesIO(binary))
        name = f"prometheus-{VERSION}.{key}.{extension}"
        content = buffer.getvalue()
        files[f"{base}/{name}"] = content
        checksums.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
    files[f"{base}/sha256sums.txt"] = "".join(checksums).encode()
    return files


def test_update_lock_pins_both_platforms_without_executing_binaries(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = release_files()
    monkeypatch.setattr(setup, "_download", files.__getitem__, raising=False)
    monkeypatch.setattr(
        setup, "verify_tool", lambda *args: pytest.fail("Updater must not execute binaries")
    )
    setup.update_lock(VERSION)
    pin = setup.ToolPin.model_validate_json((setup.ROOT / "eng" / "promtool-lock.json").read_text())
    assert pin.version == VERSION
    assert pin.revision == REVISION
    assert pin.release == f"https://github.com/prometheus/prometheus/releases/tag/v{VERSION}"
    assert set(pin.platforms) == {"windows-amd64", "linux-amd64"}
    for key, artifact in pin.platforms.items():
        assert (
            artifact.archive_sha256
            == hashlib.sha256(
                files[
                    f"https://github.com/prometheus/prometheus/releases/download/v{VERSION}/"
                    f"{artifact.archive}"
                ]
            ).hexdigest()
        )
        assert (
            artifact.binary_sha256 == hashlib.sha256(f"synthetic {key} binary".encode()).hexdigest()
        )


@pytest.mark.parametrize("failure", ["checksum", "missing-checksum", "revision", "member"])
def test_update_failure_preserves_existing_lock(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    files = release_files()
    base = f"https://github.com/prometheus/prometheus/releases/download/v{VERSION}"
    if failure == "checksum":
        files[f"{base}/prometheus-{VERSION}.linux-amd64.tar.gz"] = b"corrupted"
    elif failure == "missing-checksum":
        files[f"{base}/sha256sums.txt"] = b""
    elif failure == "revision":
        files[f"https://api.github.com/repos/prometheus/prometheus/commits/v{VERSION}"] = (
            b'{"sha": "not-a-revision"}'
        )
    else:
        name = f"prometheus-{VERSION}.windows-amd64.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../promtool.exe", b"wrong member")
        files[f"{base}/{name}"] = buffer.getvalue()
        files[f"{base}/sha256sums.txt"] = (
            f"{hashlib.sha256(buffer.getvalue()).hexdigest()}  {name}\n".encode()
        )
    monkeypatch.setattr(setup, "_download", files.__getitem__, raising=False)
    with pytest.raises((RuntimeError, ValueError, KeyError)):
        setup.update_lock(VERSION)
    assert (setup.ROOT / "eng" / "promtool-lock.json").read_text() == "original lock\n"
    assert sorted(path.name for path in (setup.ROOT / "eng").iterdir()) == ["promtool-lock.json"]


@pytest.mark.parametrize("version", ["latest", "v3.16.0", "../3.16.0", "3.16.0?x", ""])
def test_update_rejects_invalid_versions_before_network(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    monkeypatch.setattr(
        setup,
        "_download",
        lambda url: pytest.fail("Invalid version reached network"),
        raising=False,
    )
    with pytest.raises(ValueError, match="version"):
        setup.update_lock(version)


@pytest.mark.parametrize("arguments", [["--update-lock", VERSION], ["--replace"]])
def test_network_and_replacement_require_download_opt_in(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["setup_promtool.py", *arguments])
    with pytest.raises(SystemExit) as error:
        setup.main()
    assert error.value.code == 2


def test_update_command_does_not_install(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = release_files()
    monkeypatch.setattr(setup, "_download", files.__getitem__)
    monkeypatch.setattr(
        setup, "install", lambda **kwargs: pytest.fail("Lock update must not install")
    )
    monkeypatch.setattr(sys, "argv", ["setup_promtool.py", "--update-lock", VERSION, "--download"])
    assert setup.main() == 0
    assert json.loads((setup.ROOT / "eng" / "promtool-lock.json").read_text())["version"] == VERSION


@pytest.mark.parametrize("failure", ["size", "redirect", "http"])
def test_download_enforces_https_and_size_bounds(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class Response(io.BytesIO):
        url = (
            "http://example.invalid/archive" if failure == "redirect" else "https://example.invalid"
        )

    monkeypatch.setattr(setup, "MAXIMUM_BYTES", 4)
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda *args, **kwargs: Response(b"12345"))
    url = "http://example.invalid" if failure == "http" else "https://example.invalid"
    with pytest.raises(RuntimeError, match=r"HTTPS|bounds"):
        setup._download(url)


def test_install_replaces_old_binary_only_after_verifying_download(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = release_files()
    monkeypatch.setattr(setup, "_download", files.__getitem__, raising=False)
    setup.update_lock(VERSION)
    pin = setup.ToolPin.model_validate_json((setup.ROOT / "eng" / "promtool-lock.json").read_text())
    target = setup.ROOT / "eng" / "promtool.exe"
    target.write_bytes(b"old binary")
    monkeypatch.setattr(setup, "binary_path", lambda: target)
    monkeypatch.setattr(setup, "tool_pin", lambda: (pin, "windows-amd64"))

    def verify(path: Path) -> tuple[Path, object]:
        if path.read_bytes() != b"synthetic windows-amd64 binary":
            raise RuntimeError("checksum mismatch")
        return path.resolve(), pin

    monkeypatch.setattr(setup, "verify_tool", verify)
    with pytest.raises(RuntimeError, match="checksum"):
        setup.install(download=True)
    assert target.read_bytes() == b"old binary"
    archive_url = (
        f"https://github.com/prometheus/prometheus/releases/download/v{VERSION}/"
        f"prometheus-{VERSION}.windows-amd64.zip"
    )
    archive = files[archive_url]
    files[archive_url] = b"corrupted"
    with pytest.raises(RuntimeError, match="checksum"):
        setup.install(download=True, replace=True)
    assert target.read_bytes() == b"old binary"
    files[archive_url] = archive

    def reject_revision(path: Path) -> None:
        raise RuntimeError("revision mismatch")

    monkeypatch.setattr(setup, "verify_tool", reject_revision)
    with pytest.raises(RuntimeError, match="revision"):
        setup.install(download=True, replace=True)
    assert target.read_bytes() == b"old binary"
    assert sorted(path.name for path in target.parent.iterdir()) == [
        "promtool-lock.json",
        "promtool.exe",
    ]
    monkeypatch.setattr(setup, "verify_tool", verify)
    assert setup.install(download=True, replace=True) == target.resolve()
    assert target.read_bytes() == b"synthetic windows-amd64 binary"
