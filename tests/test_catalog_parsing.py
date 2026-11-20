from __future__ import annotations

import pytest

from aks_fleet_efficiency import catalog


def test_identical_yaml_is_parsed_once_but_returned_values_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = catalog.yaml.safe_load

    def load(text: str) -> object:
        nonlocal calls
        calls += 1
        return original(text)

    monkeypatch.setattr(catalog.yaml, "safe_load", load)
    text = "unique-parser-probe: [first, second]\n"
    first = catalog._catalog_yaml(text)
    assert isinstance(first, dict)
    first["unique-parser-probe"].append("mutated")
    second = catalog._catalog_yaml(text)
    assert second == {"unique-parser-probe": ["first", "second"]}
    assert calls == 1
    assert catalog._catalog_yaml(text.replace("second", "changed")) != second
    assert calls == 2


def test_catalog_models_do_not_share_mutable_state_across_loads() -> None:
    first = catalog.load_catalog()
    expected = first.pack("AKS-MEM-001").purpose
    first.pack("AKS-MEM-001").purpose = "mutated"
    first.pack("AKS-MEM-001").actions["baseline"].clear()
    second = catalog.load_catalog()
    assert second.pack("AKS-MEM-001").purpose == expected
    assert second.pack("AKS-MEM-001").actions["baseline"]


def test_duplicate_keys_still_fail_and_invalid_data_is_not_cached_as_success() -> None:
    for _ in range(2):
        with pytest.raises(ValueError, match="distinct"):
            catalog._catalog_yaml("repeat-parser-probe: first\nrepeat-parser-probe: second\n")
