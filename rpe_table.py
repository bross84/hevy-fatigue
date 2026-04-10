from datetime import date as date_type, timedelta
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from database import RPEChart, WorkoutLog

# ---------------------------------------------------------------------------
# Default RPE table — {rpe: [pct_1rep, pct_2reps, ..., pct_30reps]}
# Percentages stored as decimals (0.93 = 93% of 1RM)
# None = this rpe/rep combination is not defined
# ---------------------------------------------------------------------------
RPE_TABLE = {
    10.0: [1.00, 0.96, 0.93, 0.91, 0.88, 0.85, 0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21],
     9.5: [0.98, 0.95, 0.92, 0.89, 0.87, 0.84, 0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20],
     9.0: [0.96, 0.93, 0.91, 0.88, 0.85, 0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19],
     8.5: [0.95, 0.92, 0.89, 0.87, 0.84, 0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17],
     8.0: [0.93, 0.91, 0.88, 0.85, 0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16],
     7.5: [0.92, 0.89, 0.87, 0.84, 0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15],
     7.0: [0.91, 0.88, 0.85, 0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13],
     6.5: [0.89, 0.87, 0.84, 0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12],
     6.0: [0.88, 0.85, 0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11],
     5.5: [0.87, 0.84, 0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12, 0.10],
     5.0: [0.85, 0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11, None],
     4.5: [0.84, 0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12, 0.10, None],
     4.0: [0.83, 0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11, None, None],
     3.5: [0.81, 0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12, 0.10, None, None],
     3.0: [0.80, 0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11, None, None, None],
     2.5: [0.79, 0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12, 0.10, None, None, None],
     2.0: [0.77, 0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11, None, None, None, None],
     1.5: [0.76, 0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12, 0.10, None, None, None, None],
     1.0: [0.75, 0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11, None, None, None, None, None],
     0.5: [0.73, 0.71, 0.68, 0.65, 0.63, 0.60, 0.57, 0.55, 0.52, 0.49, 0.47, 0.44, 0.41, 0.39, 0.36, 0.33, 0.31, 0.28, 0.25, 0.23, 0.20, 0.17, 0.15, 0.12, 0.10, None, None, None, None, None],
     0.0: [0.72, 0.69, 0.67, 0.64, 0.61, 0.59, 0.56, 0.53, 0.51, 0.48, 0.45, 0.43, 0.40, 0.37, 0.35, 0.32, 0.29, 0.27, 0.24, 0.21, 0.19, 0.16, 0.13, 0.11, None, None, None, None, None, None],
}

# ---------------------------------------------------------------------------
# Seed DB
# ---------------------------------------------------------------------------
def seed_rpe_table(db):
    """Populate the rpe_chart table with the default general table if empty."""
    if db.query(RPEChart).count() > 0:
        return

    for rpe, pcts in RPE_TABLE.items():
        for rep_idx, pct in enumerate(pcts):
            if pct is not None:
                stmt = sqlite_insert(RPEChart).values(
                    movement_pattern='general',
                    rpe=rpe,
                    reps=rep_idx + 1,
                    percentage=pct
                ).on_conflict_do_nothing()
                db.execute(stmt)
    db.commit()
    print("✅ RPE table seeded.")

# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------
def lookup_percentage(rpe, reps):
    """
    Look up intensity percentage from the in-memory RPE table.
    RPE is rounded to nearest 0.5. Returns None if not found.
    """
    if rpe is None or reps is None or reps < 1:
        return None

    rounded_rpe = round(rpe * 2) / 2  # snap to nearest 0.5
    rounded_rpe = max(0.0, min(10.0, rounded_rpe))

    row = RPE_TABLE.get(rounded_rpe)
    if row is None or reps > len(row):
        return None

    return row[reps - 1]  # list is 0-indexed; reps=1 → index 0

# ---------------------------------------------------------------------------
# Fallback: Wendler formula
# ---------------------------------------------------------------------------
def wendler_e1rm(weight, reps):
    """
    Estimate 1RM using the Wendler formula: weight x reps x 0.0333 + weight
    Used as a fallback when RPE is not logged.
    Does not adjust for RPE — assumes working set effort.
    """
    return weight * reps * 0.0333 + weight

# ---------------------------------------------------------------------------
# History-based: best e1RM for an exercise over the last N weeks
# ---------------------------------------------------------------------------
def get_best_e1rm(exercise_title, db, weeks=12):
    """
    Return the highest recorded e1RM for a given exercise
    within the last N weeks. Returns None if no history exists.
    """
    since = date_type.today() - timedelta(weeks=weeks)
    return db.query(func.max(WorkoutLog.estimated_1rm)).filter(
        WorkoutLog.exercise_title == exercise_title,
        WorkoutLog.date >= since,
        WorkoutLog.estimated_1rm.isnot(None)
    ).scalar()

# ---------------------------------------------------------------------------
# Primary e1RM calculation — full fallback hierarchy
# ---------------------------------------------------------------------------
def calculate_e1rm(weight, reps, rpe=None, exercise_title=None, db=None):
    """
    Calculate e1RM using the fallback hierarchy:
      1. RPE table lookup  (most accurate — requires RPE)
      2. History inference (uses best known e1RM from last 12 weeks)
      3. Wendler formula   (always available)
    """
    if not weight or not reps or reps <= 0:
        return None

    # Priority 1: RPE table
    if rpe is not None:
        pct = lookup_percentage(rpe, reps)
        if pct and pct > 0:
            return round(weight / pct, 2)

    # Priority 2: History
    if exercise_title and db:
        known_e1rm = get_best_e1rm(exercise_title, db)
        if known_e1rm:
            return round(known_e1rm, 2)

    # Priority 3: Brzycki
    result = wendler_e1rm(weight, reps)
    return round(result, 2) if result else None

# ---------------------------------------------------------------------------
# Intensity percentage helper — shared by both stress functions
# ---------------------------------------------------------------------------
def get_intensity_pct(weight, reps, rpe=None, exercise_title=None, db=None):
    """
    Return intensity as a fraction of e1RM (0.0 – 1.0) using fallback hierarchy:
      1. RPE table lookup  — direct percentage, most accurate
      2. History inference — weight / best known e1RM from last 12 weeks
      3. Wendler formula   — always available
    Returns None if intensity cannot be determined.
    """
    if not weight or not reps or reps <= 0:
        return None

    # Priority 1: RPE table — returns the pct directly, no e1RM needed
    if rpe is not None:
        pct = lookup_percentage(rpe, reps)
        if pct and pct > 0:
            return pct

    # Priority 2: History
    e1rm = None
    if exercise_title and db:
        e1rm = get_best_e1rm(exercise_title, db)

    # Priority 3: Wendler
    if e1rm is None:
        e1rm = wendler_e1rm(weight, reps)

    if e1rm and e1rm > 0:
        return weight / e1rm

    return None

# ---------------------------------------------------------------------------
# Central and peripheral stress for a single set — used by main.py
# ---------------------------------------------------------------------------
def get_set_central_stress(weight, reps, rpe=None, exercise_title=None, db=None):
    """
    Central stress (CNS fatigue) for one set: pct² × reps
    Squaring the intensity heavily weights high-RPE, near-max efforts.
    """
    pct = get_intensity_pct(weight, reps, rpe, exercise_title, db)
    return (pct ** 2) * reps if pct else 0

def get_set_peripheral_stress(weight, reps, rpe=None, exercise_title=None, db=None):
    """
    Peripheral stress (muscular fatigue) for one set: pct × reps
    Linear — scales with volume at intensity.
    """
    pct = get_intensity_pct(weight, reps, rpe, exercise_title, db)
    return pct * reps if pct else 0
