from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date as date_type, timedelta
import os

from database import SessionLocal, DailyReadiness, WorkoutLog, ExerciseMapping, init_db
from rpe_table import get_set_central_stress, get_set_peripheral_stress, seed_rpe_table

app = FastAPI(title="Hevy Fatigue Monitor")

# Allow the frontend to talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# --- Database Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models ---
class ReadinessInput(BaseModel):
    date: date_type = Field(default_factory=date_type.today)
    weight_lbs: Optional[float] = None
    sore_quad_dom: Optional[int] = Field(None, ge=0, le=4)
    sore_posterior: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_push: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_pull: Optional[int] = Field(None, ge=0, le=4)
    joint_upper: Optional[int] = Field(None, ge=0, le=4)
    joint_lower: Optional[int] = Field(None, ge=0, le=4)
    tiredness: Optional[int] = Field(None, ge=0, le=4)
    perceived_recovery: Optional[int] = Field(None, ge=0, le=4)

class MappingUpdate(BaseModel):
    pct_quad_dom: float = Field(ge=0.0, le=1.0)
    pct_posterior: float = Field(ge=0.0, le=1.0)
    pct_upper_push: float = Field(ge=0.0, le=1.0)
    pct_upper_pull: float = Field(ge=0.0, le=1.0)
    is_conditioning: bool = False
    is_reviewed: bool = True

# --- Stress Calculators ---
def calculate_stress_scores(target_date: date_type, db: Session) -> dict:
    """
    Calculate central and peripheral stress for a given day.

    central_stress    = sum of (pct² × reps) — driven by intensity, reflects CNS fatigue
    peripheral_stress = sum of (pct  × reps) — driven by volume, reflects muscular fatigue

    Both use the RPE table → history → Wendler fallback hierarchy.
    Returns {"central": float, "peripheral": float}
    """
    sets = db.query(WorkoutLog).filter(WorkoutLog.date == target_date).all()

    central = sum(
        get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.exercise_title, db)
        for s in sets
    )
    peripheral = sum(
        get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.exercise_title, db)
        for s in sets
    )

    return {"central": round(central, 3), "peripheral": round(peripheral, 3)}

# --- Startup ---
@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        seed_rpe_table(db)
    finally:
        db.close()

# --- Routes ---

@app.get("/", include_in_schema=False)
def serve_frontend():
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Hevy Fatigue API — place index.html in the static/ folder"}

# NOTE: /api/stress/history must be defined BEFORE /api/stress/{target_date}
# so FastAPI matches the literal path first.

@app.get("/api/stress/history")
def get_stress_history(days: int = 60, db: Session = Depends(get_db)):
    """Return central and peripheral stress for each workout day in the past N days."""
    since = date_type.today() - timedelta(days=days)
    workout_dates = (
        db.query(WorkoutLog.date)
        .filter(WorkoutLog.date >= since)
        .distinct()
        .order_by(WorkoutLog.date)
        .all()
    )
    return [
        {"date": row.date, **calculate_stress_scores(row.date, db)}
        for row in workout_dates
    ]

@app.get("/api/stress/{target_date}")
def get_stress(target_date: date_type, db: Session = Depends(get_db)):
    """Return central and peripheral stress scores for a given date."""
    scores = calculate_stress_scores(target_date, db)
    return {"date": target_date, **scores}

@app.get("/api/stress/patterns/{target_date}")
def get_pattern_stress(target_date: date_type, db: Session = Depends(get_db)):
    """
    Return central and peripheral stress broken down by movement pattern for a given date.
    Uses ExerciseMapping percentage splits to distribute each set's stress across patterns.
    Conditioning exercises are excluded from pattern totals.
    """
    sets = db.query(WorkoutLog).filter(WorkoutLog.date == target_date).all()

    patterns = {
        "quad_dom":    {"central": 0.0, "peripheral": 0.0},
        "posterior":   {"central": 0.0, "peripheral": 0.0},
        "upper_push":  {"central": 0.0, "peripheral": 0.0},
        "upper_pull":  {"central": 0.0, "peripheral": 0.0},
        "unassigned":  {"central": 0.0, "peripheral": 0.0},
        "conditioning":{"central": 0.0, "peripheral": 0.0},
    }

    for s in sets:
        central = get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.exercise_title, db)
        peripheral = get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.exercise_title, db)

        mapping = db.query(ExerciseMapping).filter(
            ExerciseMapping.exercise_title == s.exercise_title
        ).first()

        if mapping and mapping.is_conditioning:
            patterns["conditioning"]["central"]    += central
            patterns["conditioning"]["peripheral"] += peripheral
            continue

        if mapping:
            total_pct = (mapping.pct_quad_dom + mapping.pct_posterior +
                         mapping.pct_upper_push + mapping.pct_upper_pull)

            if total_pct > 0:
                patterns["quad_dom"]["central"]      += central    * mapping.pct_quad_dom
                patterns["quad_dom"]["peripheral"]   += peripheral * mapping.pct_quad_dom
                patterns["posterior"]["central"]     += central    * mapping.pct_posterior
                patterns["posterior"]["peripheral"]  += peripheral * mapping.pct_posterior
                patterns["upper_push"]["central"]    += central    * mapping.pct_upper_push
                patterns["upper_push"]["peripheral"] += peripheral * mapping.pct_upper_push
                patterns["upper_pull"]["central"]    += central    * mapping.pct_upper_pull
                patterns["upper_pull"]["peripheral"] += peripheral * mapping.pct_upper_pull
            else:
                patterns["unassigned"]["central"]    += central
                patterns["unassigned"]["peripheral"] += peripheral
        else:
            patterns["unassigned"]["central"]    += central
            patterns["unassigned"]["peripheral"] += peripheral

    for p in patterns.values():
        p["central"]    = round(p["central"], 3)
        p["peripheral"] = round(p["peripheral"], 3)

    return {"date": target_date, "patterns": patterns}

@app.post("/api/readiness")
def submit_readiness(data: ReadinessInput, db: Session = Depends(get_db)):
    """Submit the daily morning readiness check-in."""
    existing = db.query(DailyReadiness).filter(DailyReadiness.date == data.date).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Readiness entry for {data.date} already exists.")

    # Auto-calculate stress scores from yesterday's Hevy data
    yesterday = data.date - timedelta(days=1)
    stress = calculate_stress_scores(yesterday, db)

    entry = DailyReadiness(
        date=data.date,
        weight_lbs=data.weight_lbs,
        sore_quad_dom=data.sore_quad_dom,
        sore_posterior=data.sore_posterior,
        sore_upper_push=data.sore_upper_push,
        sore_upper_pull=data.sore_upper_pull,
        joint_upper=data.joint_upper,
        joint_lower=data.joint_lower,
        tiredness=data.tiredness,
        perceived_recovery=data.perceived_recovery,
        central_stress=stress["central"],
        peripheral_stress=stress["peripheral"]
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "message": "Readiness logged successfully",
        "date": entry.date,
        "central_stress": stress["central"],
        "peripheral_stress": stress["peripheral"]
    }

@app.get("/api/readiness/today")
def get_today_readiness(db: Session = Depends(get_db)):
    """Check if today's readiness entry already exists."""
    entry = db.query(DailyReadiness).filter(DailyReadiness.date == date_type.today()).first()
    if not entry:
        raise HTTPException(status_code=404, detail="No readiness entry for today yet.")
    return entry

@app.get("/api/readiness")
def get_readiness_history(days: int = 30, db: Session = Depends(get_db)):
    """Return readiness entries for the past N days."""
    since = date_type.today() - timedelta(days=days)
    entries = db.query(DailyReadiness).filter(
        DailyReadiness.date >= since
    ).order_by(DailyReadiness.date).all()
    return entries

@app.get("/api/workouts/summary")
def get_workout_summary(days: int = 30, db: Session = Depends(get_db)):
    """Return daily training volume, set count, and avg RPE for the past N days."""
    since = date_type.today() - timedelta(days=days)
    rows = db.query(
        WorkoutLog.date,
        func.sum(WorkoutLog.weight_lbs * WorkoutLog.reps).label('total_volume'),
        func.count(WorkoutLog.id).label('total_sets'),
        func.avg(WorkoutLog.rpe).label('avg_rpe')
    ).filter(
        WorkoutLog.date >= since
    ).group_by(WorkoutLog.date).order_by(WorkoutLog.date).all()

    return [
        {
            "date": row.date,
            "total_volume": round(row.total_volume or 0, 2),
            "total_sets": row.total_sets,
            "avg_rpe": round(row.avg_rpe, 1) if row.avg_rpe else None
        }
        for row in rows
    ]

@app.get("/api/exercises/mappings")
def get_exercise_mappings(unreviewed: bool = False, db: Session = Depends(get_db)):
    """Return all exercise movement pattern mappings, optionally filtered to unreviewed only."""
    q = db.query(ExerciseMapping)
    if unreviewed:
        q = q.filter(ExerciseMapping.is_reviewed == False)
    mappings = q.order_by(ExerciseMapping.exercise_title).all()
    return [
        {
            "id": m.id,
            "exercise_title": m.exercise_title,
            "pct_quad_dom": m.pct_quad_dom,
            "pct_posterior": m.pct_posterior,
            "pct_upper_push": m.pct_upper_push,
            "pct_upper_pull": m.pct_upper_pull,
            "is_conditioning": m.is_conditioning,
            "source": m.source,
            "is_reviewed": m.is_reviewed,
        }
        for m in mappings
    ]

@app.put("/api/exercises/mappings/{exercise_title}")
def update_exercise_mapping(
    exercise_title: str, data: MappingUpdate, db: Session = Depends(get_db)
):
    """Update a movement pattern mapping. Marks source as 'user' and is_reviewed as True."""
    mapping = db.query(ExerciseMapping).filter(
        ExerciseMapping.exercise_title == exercise_title
    ).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Exercise '{exercise_title}' not found.")

    mapping.pct_quad_dom    = data.pct_quad_dom
    mapping.pct_posterior   = data.pct_posterior
    mapping.pct_upper_push  = data.pct_upper_push
    mapping.pct_upper_pull  = data.pct_upper_pull
    mapping.is_conditioning = data.is_conditioning
    mapping.is_reviewed     = data.is_reviewed
    mapping.source          = "user"
    db.commit()

    return {
        "id": mapping.id,
        "exercise_title": mapping.exercise_title,
        "pct_quad_dom": mapping.pct_quad_dom,
        "pct_posterior": mapping.pct_posterior,
        "pct_upper_push": mapping.pct_upper_push,
        "pct_upper_pull": mapping.pct_upper_pull,
        "is_conditioning": mapping.is_conditioning,
        "source": mapping.source,
        "is_reviewed": mapping.is_reviewed,
    }

# --- Static files (mounted AFTER all API routes) ---
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
