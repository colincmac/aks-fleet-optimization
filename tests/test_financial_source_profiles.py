from __future__ import annotations

import pytest
from pydantic import ValidationError

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.catalog.models import FinancialSourceDefinition
from aks_fleet_efficiency.cost import FinancialProfileReference


def test_financial_source_profiles_are_versioned_and_distinct_from_metrics() -> None:
    catalog = load_catalog()
    expected = {
        "azure-cost-details-amortized",
        "azure-cost-details-actual",
        "finops-focus",
        "aks-cost-analysis",
        "opencost-allocation",
        "kubecost-allocation",
        "reviewed-allocation-shares",
    }
    assert set(catalog.financial_sources) == expected
    assert set(catalog.financial_sources).isdisjoint(catalog.sources)
    for profile_id in expected:
        profile = catalog.financial_source(profile_id)
        assert isinstance(profile, FinancialSourceDefinition)
        assert profile.version == "1.0.0"
        assert profile.limitations
        assert profile.characterization == "synthetic"


def test_unknown_financial_source_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown financial source catalog profile"):
        load_catalog().financial_source("unknown")


def test_financial_profiles_distinguish_version_roles_and_pricing_provenance() -> None:
    catalog = load_catalog()
    focus = catalog.financial_source("finops-focus")
    assert focus.producer_version_kind == "dataset"
    assert focus.specification_version == "1.2"
    assert focus.characterized_versions == {"azure-focus": ["1.2-preview"]}
    assert focus.pricing_provenance == "billing-ledger"
    assert catalog.financial_source("aks-cost-analysis").producer_version_kind == "projection"
    assert (
        catalog.financial_source("azure-cost-details-actual").producer_version_kind == "projection"
    )
    for profile_id in ["opencost-allocation", "kubecost-allocation"]:
        profile = catalog.financial_source(profile_id)
        assert profile.producer_version_kind == "product"
        assert profile.pricing_provenance == "reviewed"


@pytest.mark.parametrize("version", ["1.2-preview", "1.0r2", "2025-05-01"])
def test_financial_version_reference_preserves_native_labels(version: str) -> None:
    reference = FinancialProfileReference(
        id="finops-focus", version="1.0.0", producer_version=version
    )
    assert reference.producer_version == version


def test_profile_cannot_mix_independent_version_groups() -> None:
    payload = load_catalog().financial_source("finops-focus").model_dump(mode="json")
    payload["characterized_versions"]["unrelated-product"] = ["99.0.0"]
    with pytest.raises(ValidationError, match="one producer version group"):
        FinancialSourceDefinition.model_validate(payload)
