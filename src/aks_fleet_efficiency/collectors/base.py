from __future__ import annotations

from typing import Protocol

from aks_fleet_efficiency.models import FleetSnapshot


class SnapshotCollector(Protocol):
    """Collector boundary. Implementations must be read-only and return normalized data."""

    def collect(self) -> FleetSnapshot: ...
