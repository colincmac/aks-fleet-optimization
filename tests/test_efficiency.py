from aks_fleet_efficiency.analysis.efficiency import potential_request_reduction, safe_ratio


def test_safe_ratio() -> None:
    assert safe_ratio(20, 100) == 0.2
    assert safe_ratio(20, 0) is None
    assert safe_ratio(None, 100) is None


def test_potential_request_reduction_uses_headroom() -> None:
    assert potential_request_reduction(1000, 280, safety_factor=1.25) == 650
