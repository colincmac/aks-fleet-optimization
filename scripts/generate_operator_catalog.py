from __future__ import annotations

import argparse
from pathlib import Path

from aks_fleet_efficiency.operator import generated_operator_assets

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate/check manifest-derived operator assets.")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    matches = True
    for path, content in generated_operator_assets(ROOT).items():
        if arguments.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                print(f"Operator asset missing or stale: {path}")
                matches = False
        else:
            path.write_text(content, encoding="utf-8")
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
