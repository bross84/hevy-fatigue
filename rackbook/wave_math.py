JOKER_BAND = 0.05
ROUND_TO_KG = 2.5


def _round_weight(kg: float) -> float:
    return round(kg / ROUND_TO_KG) * ROUND_TO_KG


def round_weight(kg: float) -> float:
    return _round_weight(kg)


def epley(weight_kg: float, reps: int) -> float:
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30)


def joker_qualifies(joker_e1rm: float, amrap_e1rm: float) -> bool:
    return abs(joker_e1rm - amrap_e1rm) / amrap_e1rm <= JOKER_BAND


def working_weight(training_max_kg: float, week_number: int, wave_params: dict) -> float:
    pct = wave_params["percentages"][week_number - 1]
    return _round_weight(training_max_kg * pct)


def bbb_weight(e1rm_kg: float, week_number: int, wave_params: dict) -> float:
    pct = wave_params["bbb_percentages"][week_number - 1]
    return _round_weight(e1rm_kg * pct)


def joker_weight(previous_weight_kg: float, jump_pct: float) -> float:
    """Compute Joker set weight from previous set weight and jump percentage."""
    return _round_weight(previous_weight_kg * (1 + jump_pct))


def session_e1rm(amrap_e1rm: float, joker_sets: list[tuple[float, float]]) -> float:
    """
    Compute final session e1RM from an AMRAP anchor and a list of Joker sets.
    joker_sets: list of (weight_kg, reps) — only sets with RPE logged should be passed in.
    Jokers outside the ±5% band are excluded. Result is averaged with the AMRAP anchor.
    """
    qualifying = []
    for weight_kg, reps in joker_sets:
        j_e1rm = epley(weight_kg, reps)
        if joker_qualifies(j_e1rm, amrap_e1rm):
            qualifying.append(j_e1rm)

    all_values = [amrap_e1rm] + qualifying
    return sum(all_values) / len(all_values)
