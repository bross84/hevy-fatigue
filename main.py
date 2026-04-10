from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date as date_type, timedelta

from database import SessionLocal, DailyReadiness, WorkoutLog, init_db

app = FastAPI(title="Hevy Fatigue Monitor")

# Allow the frontend to talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Model for Readiness Input ---
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

# --- Training Load Calculator ---
def calculate_training_load(target_date: date_type, db: Session) -> float:
    """
    Compares a day's total training volume to a 28-day rolling average.
    Volume = sum of (weight_lbs * reps) across all sets for that day.

    Score:
        0 = no training
        1 = below 60% of average (well below normal)
        2 = 60-80% of average (below normal)
        3 = 80-120% of average (normal)
        4 = 120-150% of average (above normal)
        5 = above 150% of average (well above normal)
    """
    daily_volume = db.query(
        func.sum(WorkoutLog.weight_lbs * WorkoutLog.reps)
    ).filter(WorkoutLog.date == target_date).scalar() or 0

    if daily_volume == 0:
        return 0.0

    # Rolling average: training days only, over the past 28 days
    window_start = target_date - timedelta(days=28)
    daily_volumes = db.query(
        func.sum(WorkoutLog.weight_lbs * WorkoutLog.reps).label('volume')
    ).filter(
        WorkoutLog.date >= window_start,
        WorkoutLog.date < target_date
    ).group_by(WorkoutLog.date).all()

    # Only count days with actual weighted volume — excludes conditioning/bodyweight days
    weighted_days = [d.volume for d in daily_volumes if d.volume and d.volume > 0]

    if not weighted_days:
        return 3.0  # No history yet — assume normal

    avg_volume = sum(weighted_days) / len(weighted_days)

    if avg_volume == 0:
        return 3.0

    ratio = daily_volume / avg_volume

    if ratio < 0.6:
        return 1.0
    elif ratio < 0.8:
        return 2.0
    elif ratio <= 1.2:
        return 3.0
    elif ratio <= 1.5:
        return 4.0
    else:
        return 5.0

# --- Startup ---
@app.on_event("startup")
def startup():
    init_db()

# --- Routes ---

@app.get("/api/training-load/{target_date}")
def get_training_load(target_date: date_type, db: Session = Depends(get_db)):
    """Return the calculated training load score for a given date."""
    load = calculate_training_load(target_date, db)
    return {"date": target_date, "perceived_training_load": load}

@app.post("/api/readiness")
def submit_readiness(data: ReadinessInput, db: Session = Depends(get_db)):
    """Submit the daily morning readiness check-in."""
    existing = db.query(DailyReadiness).filter(DailyReadiness.date == data.date).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Readiness entry for {data.date} already exists.")

    # Auto-calculate training load from yesterday's Hevy data
    yesterday = data.date - timedelta(days=1)
    training_load = calculate_training_load(yesterday, db)

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
        perceived_training_load=training_load
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "message": "Readiness logged successfully",
        "date": entry.date,
        "perceived_training_load": training_load
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
