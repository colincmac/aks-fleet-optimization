"""Publish approved saved advisor assessments for the read-only Headlamp dashboard."""

import argparse
from pathlib import Path
from uuid import UUID

from aks_fleet_efficiency.reporting.headlamp import publish


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, action="append", required=True)
    parser.add_argument("--tenant", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        publish(args.bundle, args.tenant, args.output)
    except OSError, ValueError:
        parser.exit(
            1,
            "Assessment feed not published. "
            "Check approved scope, bundle integrity, replay, and output limits.\n",
        )


if __name__ == "__main__":
    main()
