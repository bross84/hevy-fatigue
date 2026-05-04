from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from database import ExerciseMapping

# ---------------------------------------------------------------------------
# Explicit pre-seeded mappings
# Handles edge cases where keyword rules would misclassify
# Format: { exercise_title_lowercase: (quad, posterior, push, pull, is_conditioning) }
# ---------------------------------------------------------------------------
EXPLICIT_MAPPINGS = {
    # Quad dominant — squat patterns
    "leg press":                    (1.0, 0.0, 0.0, 0.0, False),
    "hack squat":                   (1.0, 0.0, 0.0, 0.0, False),
    "leg extension":                (1.0, 0.0, 0.0, 0.0, False),
    "sissy squat":                  (1.0, 0.0, 0.0, 0.0, False),
    "safety bar squat":             (1.0, 0.0, 0.0, 0.0, False),
    "ssb squat":                    (1.0, 0.0, 0.0, 0.0, False),
    "box squat":                    (1.0, 0.0, 0.0, 0.0, False),  # auto default — user should review
    "front squat":                  (1.0, 0.0, 0.0, 0.0, False),
    "goblet squat":                 (1.0, 0.0, 0.0, 0.0, False),
    "bulgarian split squat":        (1.0, 0.0, 0.0, 0.0, False),
    "step up":                      (1.0, 0.0, 0.0, 0.0, False),

    # Posterior chain — hip hinge patterns
    "leg curl":                     (0.0, 1.0, 0.0, 0.0, False),
    "lying leg curl":               (0.0, 1.0, 0.0, 0.0, False),
    "seated leg curl":              (0.0, 1.0, 0.0, 0.0, False),
    "nordic curl":                  (0.0, 1.0, 0.0, 0.0, False),
    "pull through":                 (0.0, 1.0, 0.0, 0.0, False),
    "hip extension":                (0.0, 1.0, 0.0, 0.0, False),
    "back extension":               (0.0, 1.0, 0.0, 0.0, False),
    "reverse hyperextension":       (0.0, 1.0, 0.0, 0.0, False),
    "reverse hyper":                (0.0, 1.0, 0.0, 0.0, False),
    "glute bridge":                 (0.0, 1.0, 0.0, 0.0, False),
    "hip thrust":                   (0.0, 1.0, 0.0, 0.0, False),
    "kettlebell swing":             (0.0, 1.0, 0.0, 0.0, False),
    "kb swing":                     (0.0, 1.0, 0.0, 0.0, False),
    "good morning":                 (0.0, 1.0, 0.0, 0.0, False),
    "safety bar good morning":      (0.0, 1.0, 0.0, 0.0, False),
    "romanian deadlift":            (0.0, 1.0, 0.0, 0.0, False),
    "rdl":                          (0.0, 1.0, 0.0, 0.0, False),
    "stiff leg deadlift":           (0.0, 1.0, 0.0, 0.0, False),
    "straight leg deadlift":        (0.0, 1.0, 0.0, 0.0, False),
    "suitcase deadlift":            (0.0, 1.0, 0.0, 0.0, False),
    "trap bar deadlift":            (0.2, 0.8, 0.0, 0.0, False),
    "conventional deadlift":        (0.2, 0.8, 0.0, 0.0, False),
    "sumo deadlift":                (0.3, 0.7, 0.0, 0.0, False),
    "mid shin rack pull":           (0.1, 0.9, 0.0, 0.0, False),
    "rack pull":                    (0.1, 0.9, 0.0, 0.0, False),

    # Upper push
    "jm press":                     (0.0, 0.0, 1.0, 0.0, False),
    "floor press":                  (0.0, 0.0, 1.0, 0.0, False),
    "board press":                  (0.0, 0.0, 1.0, 0.0, False),
    "close grip bench press":       (0.0, 0.0, 1.0, 0.0, False),
    "pin press":                    (0.0, 0.0, 1.0, 0.0, False),
    "push up":                      (0.0, 0.0, 1.0, 0.0, False),
    "dip":                          (0.0, 0.0, 1.0, 0.0, False),
    "tricep pushdown":              (0.0, 0.0, 1.0, 0.0, False),
    "tricep extension":             (0.0, 0.0, 1.0, 0.0, False),
    "skull crusher":                (0.0, 0.0, 1.0, 0.0, False),
    "overhead tricep extension":    (0.0, 0.0, 1.0, 0.0, False),

    # Upper pull
    "pull up":                      (0.0, 0.0, 0.0, 1.0, False),
    "pullup":                       (0.0, 0.0, 0.0, 1.0, False),
    "chin up":                      (0.0, 0.0, 0.0, 1.0, False),
    "chinup":                       (0.0, 0.0, 0.0, 1.0, False),
    "lat pulldown":                 (0.0, 0.0, 0.0, 1.0, False),
    "face pull":                    (0.0, 0.0, 0.0, 1.0, False),
    "rear delt fly":                (0.0, 0.0, 0.0, 1.0, False),
    "rear delt raise":              (0.0, 0.0, 0.0, 1.0, False),
    "bicep curl":                   (0.0, 0.0, 0.0, 1.0, False),
    "hammer curl":                  (0.0, 0.0, 0.0, 1.0, False),
    "preacher curl":                (0.0, 0.0, 0.0, 1.0, False),
    "t-bar row":                    (0.0, 0.0, 0.0, 1.0, False),

    # Full-body mixed patterns
    "burpee":                       (0.30, 0.30, 0.20, 0.20, False),
    "burpees":                      (0.30, 0.30, 0.20, 0.20, False),
    "thruster":                     (0.30, 0.30, 0.20, 0.20, False),
    "barbell thruster":             (0.30, 0.30, 0.20, 0.20, False),
    "dumbbell thruster":            (0.30, 0.30, 0.20, 0.20, False),
    "box jump":                     (0.30, 0.30, 0.20, 0.20, False),
    "box jumps":                    (0.30, 0.30, 0.20, 0.20, False),

    # Conditioning — excluded from pattern stress calculations
    "rowing machine":               (0.0, 0.0, 0.0, 0.0, True),
    "assault bike":                 (0.0, 0.0, 0.0, 0.0, True),
    "air bike":                     (0.0, 0.0, 0.0, 0.0, True),
    "ski erg":                      (0.0, 0.0, 0.0, 0.0, True),
    "treadmill":                    (0.0, 0.0, 0.0, 0.0, True),
    "double under":                 (0.0, 0.0, 0.0, 0.0, True),
    "jump rope":                    (0.0, 0.0, 0.0, 0.0, True),
}

# ---------------------------------------------------------------------------
# Keyword rules — applied when no explicit mapping exists
# More specific patterns checked before general ones
# ---------------------------------------------------------------------------
QUAD_KEYWORDS    = ["squat", "lunge", "bulgarian", "step-up", "step up", "leg press",
                    "hack", "sissy", "leg extension"]

POSTERIOR_KEYWORDS = ["deadlift", "rdl", "romanian", "good morning", "hip thrust",
                      "glute", "hamstring", "leg curl", "back extension", "hyperextension",
                      "reverse hyper", "pull through", "nordic", "swing", "suitcase",
                      "rack pull"]

PUSH_KEYWORDS    = ["bench", "overhead press", "ohp", "incline press", "decline press",
                    "shoulder press", "military press", "dip", "tricep", "fly", "flye",
                    "chest press", "push up", "pushup", "floor press", "board press",
                    "pin press", "jm press"]

PULL_KEYWORDS    = ["row", "pulldown", "pull-down", "pullup", "pull-up", "chinup",
                    "chin-up", "lat ", "face pull", "rear delt", "bicep", "curl",
                    "shrug", "t-bar", "cable pull"]

CONDITIONING_KEYWORDS = ["bike", "run", "ski", "row machine", "rowing machine", "treadmill",
                          "jump rope", "double under",
                          "metcon", "conditioning", "wod", "amrap", "emom"]

def _matches(title_lower, keywords):
    return any(kw in title_lower for kw in keywords)

def classify_exercise(title: str) -> dict:
    """
    Classify an exercise title into movement pattern percentages.

    Returns a dict with keys:
        pct_quad_dom, pct_posterior, pct_upper_push, pct_upper_pull,
        is_conditioning, source
    """
    t = title.lower().strip()

    # Check explicit mappings first
    if t in EXPLICIT_MAPPINGS:
        q, po, pu, pl, cond = EXPLICIT_MAPPINGS[t]
        return {
            "pct_quad_dom": q,
            "pct_posterior": po,
            "pct_upper_push": pu,
            "pct_upper_pull": pl,
            "is_conditioning": cond,
            "source": "auto"
        }

    # Conditioning check before strength keywords
    if _matches(t, CONDITIONING_KEYWORDS):
        return {
            "pct_quad_dom": 0.0, "pct_posterior": 0.0,
            "pct_upper_push": 0.0, "pct_upper_pull": 0.0,
            "is_conditioning": True, "source": "auto"
        }

    # Leg curl / leg press — check before generic curl/press rules
    if "leg curl" in t:
        return {"pct_quad_dom": 0.0, "pct_posterior": 1.0,
                "pct_upper_push": 0.0, "pct_upper_pull": 0.0,
                "is_conditioning": False, "source": "auto"}

    if "leg press" in t:
        return {"pct_quad_dom": 1.0, "pct_posterior": 0.0,
                "pct_upper_push": 0.0, "pct_upper_pull": 0.0,
                "is_conditioning": False, "source": "auto"}

    # Standard keyword matching
    if _matches(t, QUAD_KEYWORDS):
        return {"pct_quad_dom": 1.0, "pct_posterior": 0.0,
                "pct_upper_push": 0.0, "pct_upper_pull": 0.0,
                "is_conditioning": False, "source": "auto"}

    if _matches(t, POSTERIOR_KEYWORDS):
        return {"pct_quad_dom": 0.0, "pct_posterior": 1.0,
                "pct_upper_push": 0.0, "pct_upper_pull": 0.0,
                "is_conditioning": False, "source": "auto"}

    if _matches(t, PUSH_KEYWORDS):
        return {"pct_quad_dom": 0.0, "pct_posterior": 0.0,
                "pct_upper_push": 1.0, "pct_upper_pull": 0.0,
                "is_conditioning": False, "source": "auto"}

    if _matches(t, PULL_KEYWORDS):
        return {"pct_quad_dom": 0.0, "pct_posterior": 0.0,
                "pct_upper_push": 0.0, "pct_upper_pull": 1.0,
                "is_conditioning": False, "source": "auto"}

    # Nothing matched — unassigned, needs user review
    return {
        "pct_quad_dom": 0.0, "pct_posterior": 0.0,
        "pct_upper_push": 0.0, "pct_upper_pull": 0.0,
        "is_conditioning": False, "source": "auto"
    }

# ---------------------------------------------------------------------------
# Ensure an exercise is in the mapping table — called during import
# ---------------------------------------------------------------------------
def ensure_exercise_mapped(title: str, db) -> None:
    """
    Check if an exercise already has a mapping. If not, auto-classify
    and insert it as unreviewed. Existing user-defined mappings are never overwritten.
    """
    exists = db.query(ExerciseMapping).filter(
        ExerciseMapping.exercise_title == title
    ).first()

    if exists:
        return  # Already mapped — don't overwrite

    classification = classify_exercise(title)
    stmt = sqlite_insert(ExerciseMapping).values(
        exercise_title=title,
        pct_quad_dom=classification["pct_quad_dom"],
        pct_posterior=classification["pct_posterior"],
        pct_upper_push=classification["pct_upper_push"],
        pct_upper_pull=classification["pct_upper_pull"],
        is_conditioning=classification["is_conditioning"],
        source=classification["source"],
        is_reviewed=False
    ).on_conflict_do_nothing()
    db.execute(stmt)
