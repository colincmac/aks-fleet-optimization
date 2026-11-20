from __future__ import annotations


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def observation_days(start_timestamp: float, end_timestamp: float) -> float:
    return max(0.0, (end_timestamp - start_timestamp) / 86_400)


def potential_request_reduction(
    request: float | None,
    usage_p95: float | None,
    *,
    safety_factor: float = 1.25,
) -> float | None:
    if request is None or usage_p95 is None or request <= 0:
        return None
    target = usage_p95 * safety_factor
    return max(0.0, request - target)
