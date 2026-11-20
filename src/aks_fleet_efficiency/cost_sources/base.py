from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.catalog.models import FinancialSourceDefinition


class ProjectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, hide_input_in_errors=True, frozen=True
    )


def projection_profile(
    profile_id: str, producer_version: str, projection_format: str
) -> FinancialSourceDefinition:
    profile = load_catalog().financial_source(profile_id)
    if profile.projection_format != projection_format:
        raise ValueError("financial projection format does not match the selected profile")
    if not profile.supports_producer_version(producer_version):
        raise ValueError("financial producer version is not characterized for the selected profile")
    return profile
