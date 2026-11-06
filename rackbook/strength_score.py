"""
strength_score.py — Bodyweight-adjusted strength for the progress chart. Pure functions, no I/O.

DOTS is a bodyweight-dependent multiplier: score = lift_kg * 500 / (a + b*BW + c*BW^2 + d*BW^3 + e*BW^4),
BW in kg, with separate coefficients per sex. It is built for a squat+bench+deadlift total; applied to a
single lift's e1RM it is only meaningful as a trend against your own history, not against published tables.
"""
from datetime import date, timedelta
from typing import Literal

Sex = Literal["male", "female"]

_DOTS_COEFFS: dict[str, tuple[float, float, float, float, float]] = {
    "male": (-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093),
    "female": (-57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.0000010706),
}


def dots_coefficient(bodyweight_kg: float, sex: Sex = "male") -> float:
    """The DOTS multiplier for a bodyweight. Raises ValueError for a non-positive bodyweight or unknown sex."""
    if bodyweight_kg <= 0:
        raise ValueError("bodyweight_kg must be positive")
    try:
        a, b, c, d, e = _DOTS_COEFFS[sex]
    except KeyError:
        raise ValueError(f"sex must be 'male' or 'female', got {sex!r}") from None
    bw = bodyweight_kg
    return 500 / (a + b * bw + c * bw**2 + d * bw**3 + e * bw**4)


def dots_score(lift_kg: float, bodyweight_kg: float, sex: Sex = "male") -> float:
    return lift_kg * dots_coefficient(bodyweight_kg, sex)


def smooth_body_weight(measurements: list[dict], window_days: int = 7) -> list[dict]:
    """Trailing average of weight_kg over the last `window_days` calendar days (the day itself included).
    Days missing from the window are simply not counted, so gaps never drag the average toward zero.
    Takes rows with 'date' (YYYY-MM-DD) and 'weight_kg'; returns {'date', 'weight_kg'} oldest first."""
    points = sorted(
        ((date.fromisoformat(m["date"]), m["weight_kg"]) for m in measurements),
        key=lambda p: p[0],
    )
    smoothed = []
    for day, _ in points:
        start = day - timedelta(days=window_days - 1)
        window = [w for d, w in points if start <= d <= day]
        smoothed.append({"date": day.isoformat(), "weight_kg": sum(window) / len(window)})
    return smoothed


def weight_on(smoothed: list[dict], on: str, max_age_days: int = 14) -> float | None:
    """Smoothed bodyweight to use for a lift performed on `on` (YYYY-MM-DD): the latest reading on or
    before that date, so a missing day falls back to the most recent known weight. None if there is no
    reading, or the latest is more than `max_age_days` old (a months-old weight would give a made-up score)."""
    best = None
    for row in smoothed:
        if row["date"] <= on:
            best = row
        else:
            break
    if best is None:
        return None
    if (date.fromisoformat(on) - date.fromisoformat(best["date"])).days > max_age_days:
        return None
    return best["weight_kg"]
