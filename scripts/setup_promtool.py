from __future__ import annotations

import argparse
import hashlib
import io
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from validate_promql import binary_path, tool_pin, verify_tool

MAXIMUM_BYTES = 300 * 1024 * 1024


def install(*, download: bool) -> Path:
    target = binary_path()
    if target.exists():
        return verify_tool(target)[0]
    if not download:
        raise RuntimeError("Tool setup requires explicit --download; verification never downloads")
    pin, key = tool_pin()
    artifact = pin.platforms[key]
    url = f"https://github.com/prometheus/prometheus/releases/download/v{pin.version}/{artifact.archive}"
    with urllib.request.urlopen(url, timeout=120) as response:
        if not response.url.startswith("https://"):
            raise RuntimeError("Tool download must remain HTTPS")
        content = response.read(MAXIMUM_BYTES + 1)
    if (
        len(content) > MAXIMUM_BYTES
        or hashlib.sha256(content).hexdigest() != artifact.archive_sha256
    ):
        raise RuntimeError("promtool archive exceeds bounds or checksum differs from pin")
    suffix = ".exe" if key.startswith("windows") else ""
    member = f"prometheus-{pin.version}.{key}/promtool{suffix}"
    if artifact.archive.endswith(".zip"):
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
    if hashlib.sha256(binary).hexdigest() != artifact.binary_sha256:
        raise RuntimeError("promtool binary checksum differs from pin")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(binary)
    if not suffix:
        target.chmod(0o755)
    return verify_tool(target)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicitly install the checksum-pinned promtool.")
    parser.add_argument("--download", action="store_true")
    arguments = parser.parse_args()
    print(f"Verified pinned tool: {install(download=arguments.download)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
