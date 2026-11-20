from __future__ import annotations

from pathlib import Path

from aks_fleet_efficiency.models import FleetSnapshot


class FixtureCollector:
    def __init__(self, path: Path) -> None:
        self.path = path

    def collect(self) -> FleetSnapshot:
        return FleetSnapshot.model_validate_json(self.path.read_text(encoding="utf-8"))
