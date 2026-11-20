from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from validate_promql import ROOT, PlatformPin, ToolPin, binary_path, tool_pin, verify_tool

MAXIMUM_BYTES = 300 * 1024 * 1024
RELEASES = "https://github.com/prometheus/prometheus/releases"


def _download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise RuntimeError("Tool download requires HTTPS")
    with urllib.request.urlopen(url, timeout=120) as response:
        if not response.url.startswith("https://"):
            raise RuntimeError("Tool download must remain HTTPS")
        content: bytes = response.read(MAXIMUM_BYTES + 1)
    if len(content) > MAXIMUM_BYTES:
        raise RuntimeError("Tool download exceeds size bounds")
    return content


def _release_binary(version: str, key: str, archive_name: str, archive_sha256: str) -> bytes:
    content = _download(f"{RELEASES}/download/v{version}/{archive_name}")
    if hashlib.sha256(content).hexdigest() != archive_sha256:
        raise RuntimeError("promtool archive exceeds bounds or checksum differs from pin")
    suffix = ".exe" if key.startswith("windows") else ""
    member = f"prometheus-{version}.{key}/promtool{suffix}"
    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            zip_info = archive.getinfo(member)
            if zip_info.is_dir() or zip_info.file_size > MAXIMUM_BYTES:
                raise RuntimeError("Invalid tool archive member")
            binary = archive.read(member)
    else:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            tar_info = archive.getmember(member)
            if not tar_info.isfile() or tar_info.size > MAXIMUM_BYTES:
                raise RuntimeError("Invalid tool archive member")
            handle = archive.extractfile(tar_info)
            if handle is None:
                raise RuntimeError("Tool archive lacks the exact expected binary")
            with handle:
                binary = handle.read(MAXIMUM_BYTES + 1)
    if len(binary) > MAXIMUM_BYTES:
        raise RuntimeError("Tool binary exceeds size bounds")
    return binary


def update_lock(version: str) -> Path:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9]+(?:[.-][a-zA-Z0-9]+)*)?", version):
        raise ValueError("Provide an exact release version without a leading v, such as 3.16.0")
    commit = json.loads(
        _download(f"https://api.github.com/repos/prometheus/prometheus/commits/v{version}")
    )
    revision = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise RuntimeError("Release tag did not resolve to an exact Git revision")
    checksums = _download(f"{RELEASES}/download/v{version}/sha256sums.txt").decode("utf-8")
    platforms: dict[str, PlatformPin] = {}
    for key, extension in (("windows-amd64", "zip"), ("linux-amd64", "tar.gz")):
        name = f"prometheus-{version}.{key}.{extension}"
        matches = re.findall(
            rf"^([a-f0-9]{{64}})[ \t]+\*?{re.escape(name)}\r?$", checksums, re.MULTILINE
        )
        if len(matches) != 1:
            raise RuntimeError(f"Release checksums must contain exactly one entry for {name}")
        binary = _release_binary(version, key, name, matches[0])
        platforms[key] = PlatformPin(
            archive=name,
            archive_sha256=matches[0],
            binary_sha256=hashlib.sha256(binary).hexdigest(),
        )
    pin = ToolPin(
        version=version,
        revision=revision,
        release=f"{RELEASES}/tag/v{version}",
        platforms=platforms,
    )
    target = ROOT / "eng" / "promtool-lock.json"
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_text(pin.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def install(*, download: bool, replace: bool = False) -> Path:
    target = binary_path()
    if replace and not download:
        raise RuntimeError("Replacing a tool requires explicit --download")
    if target.exists() and not replace:
        return verify_tool(target)[0]
    if not download:
        raise RuntimeError("Tool setup requires explicit --download; verification never downloads")
    pin, key = tool_pin()
    artifact = pin.platforms[key]
    binary = _release_binary(pin.version, key, artifact.archive, artifact.archive_sha256)
    if hashlib.sha256(binary).hexdigest() != artifact.binary_sha256:
        raise RuntimeError("promtool binary checksum differs from pin")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target.parent, suffix=target.suffix, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_bytes(binary)
        if not key.startswith("windows"):
            temporary.chmod(0o755)
        verify_tool(temporary)
        if replace:
            temporary.replace(target)
        else:
            with target.open("xb") as handle:
                handle.write(binary)
            if not key.startswith("windows"):
                target.chmod(0o755)
    finally:
        temporary.unlink(missing_ok=True)
    return target.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install promtool or update its Prometheus release pin."
    )
    parser.add_argument("--download", action="store_true", help="Allow public GitHub downloads.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--update-lock",
        metavar="VERSION",
        help="Regenerate Windows/Linux pins from an exact Prometheus release; do not install.",
    )
    actions.add_argument(
        "--replace",
        action="store_true",
        help="Replace the local binary after verifying the new pin.",
    )
    arguments = parser.parse_args()
    if (arguments.update_lock is not None or arguments.replace) and not arguments.download:
        parser.error("--update-lock and --replace require explicit --download")
    if arguments.update_lock is not None:
        print(f"Updated Prometheus/promtool lock: {update_lock(arguments.update_lock)}")
    else:
        target = install(download=arguments.download, replace=arguments.replace)
        print(f"Verified pinned tool: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
