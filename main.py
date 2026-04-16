from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date as date_type, timedelta, datetime
from cryptography.fernet import Fernet
import os
import threading

from database import SessionLocal, DailyReadiness, WorkoutLog, ExerciseMapping, AppSetting, init_db

# ── Encryption ────────────────────────────────────────────────────────────────
# A Fernet key is generated once and stored in the Docker volume at /data/app.key.
# The API key in the DB is encrypted with it, so a DB dump alone can't expose it.
_FERNET_KEY_PATH = os.getenv("FERNET_KEY_PATH", "/data/app.key")
_fernet: Fernet | None = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    if os.path.exists(_FERNET_KEY_PATH):
        with open(_FERNET_KEY_PATH, "rb") as f:
            key = f.read().strip()
    else:
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(_FERNET_KEY_PATH), exist_ok=True)
        with open(_FERNET_KEY_PATH, "wb") as f:
            f.write(key)
        try:
            os.chmod(_FERNET_KEY_PATH, 0o600)
        except OSError:
            pass  # Windows doesn't support chmod — safe to ignore
    _fernet = Fernet(key)
    return _fernet

def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()

def _decrypt(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        # If decryption fails the value may be a legacy plaintext key — return as-is
        return ciphertext
from rpe_table import get_set_central_stress, get_set_peripheral_stress, seed_rpe_table
from importer import import_hevy_data

app = FastAPI(title="Hevy Fatigue Monitor")

# CORS — restrict to your Cloudflare tunnel domain in production.
# Set ALLOWED_ORIGIN in your .env file, e.g.:
#   ALLOWED_ORIGIN=https://your-tunnel-domain.com
# Falls back to localhost only if not set.
_allowed_origin = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin],
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
    hrv_ms: Optional[float] = Field(None, ge=0)
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(None, ge=0, le=4)

class ReadinessUpdate(BaseModel):
    weight_lbs: Optional[float] = None
    sore_quad_dom: Optional[int] = Field(None, ge=0, le=4)
    sore_posterior: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_push: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_pull: Optional[int] = Field(None, ge=0, le=4)
    joint_upper: Optional[int] = Field(None, ge=0, le=4)
    joint_lower: Optional[int] = Field(None, ge=0, le=4)
    tiredness: Optional[int] = Field(None, ge=0, le=4)
    perceived_recovery: Optional[int] = Field(None, ge=0, le=4)
    hrv_ms: Optional[float] = Field(None, ge=0)
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(None, ge=0, le=4)

class SettingsInput(BaseModel):
    hevy_api_key: str

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
        get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
        for s in sets
    )
    peripheral = sum(
        get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
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

# --- Sync state (prevents concurrent imports and rate-limits manual triggers) ---
_sync_lock = threading.Lock()
_sync_status = {"running": False, "last_result": None, "last_run": None}
_SYNC_COOLDOWN_SECONDS = 600  # 10 minutes between manual syncs

# --- Settings helper ---
def _get_db_api_key(db: Session) -> str | None:
    """Read and decrypt the Hevy API key stored in the app_settings table."""
    row = db.query(AppSetting).filter(AppSetting.key == "hevy_api_key").first()
    if not row or not row.value:
        return None
    return _decrypt(row.value)

# --- Routes ---

@app.get("/", include_in_schema=False)
def serve_frontend():
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Hevy Fatigue API — place index.html in the static/ folder"}

@app.post("/api/sync")
def trigger_sync(force: bool = False, db: Session = Depends(get_db)):
    """
    Pull latest workouts from the Hevy API into the local database.
    Rejects if a sync is already running or ran within the cooldown window.
    Pass ?force=true to bypass the cooldown (e.g. from the auto-sync on check-in).
    """
    if not _sync_lock.acquire(blocking=False):
        return {"status": "already_running"}

    try:
        # Enforce cooldown on manual triggers to prevent API hammering
        if not force and _sync_status["last_run"] is not None:
            elapsed = (datetime.utcnow() - _sync_status["last_run"]).total_seconds()
            if elapsed < _SYNC_COOLDOWN_SECONDS:
                remaining = int(_SYNC_COOLDOWN_SECONDS - elapsed)
                return {"status": "cooldown", "retry_after_seconds": remaining}

        _sync_status["running"] = True
        # Resolve API key: DB setting first, then file/env fallback inside HevyClient
        api_key = _get_db_api_key(db)
        result = import_hevy_data(api_key=api_key)
        _sync_status["last_result"] = result
        _sync_status["last_run"] = datetime.utcnow()
        return {"status": "ok", "new_sets": result.get("new_sets", 0)}
    except Exception as e:
        _sync_status["last_result"] = {"error": str(e)}
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
    finally:
        _sync_status["running"] = False
        _sync_lock.release()

@app.get("/api/sync/status")
def sync_status():
    """Check whether a sync is currently running and what the last run returned."""
    return {"running": _sync_status["running"], "last_result": _sync_status["last_result"]}

# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    """Return whether the Hevy API key is configured, and a masked preview."""
    key = _get_db_api_key(db)
    if key and len(key) >= 4:
        preview = "···" + key[-4:]
    elif key:
        preview = "···"
    else:
        preview = None
    return {"api_key_set": bool(key), "api_key_preview": preview}

@app.put("/api/settings")
def save_settings(data: SettingsInput, db: Session = Depends(get_db)):
    """Encrypt and save the Hevy API key in the database."""
    key = data.hevy_api_key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="API key cannot be empty.")
    encrypted = _encrypt(key)
    row = db.query(AppSetting).filter(AppSetting.key == "hevy_api_key").first()
    if row:
        row.value = encrypted
    else:
        db.add(AppSetting(key="hevy_api_key", value=encrypted))
    db.commit()
    preview = "···" + key[-4:] if len(key) >= 4 else "···"
    return {"message": "API key saved.", "api_key_preview": preview}

@app.get("/api/settings/test")
def test_api_key(db: Session = Depends(get_db)):
    """Test whether the stored API key can reach the Hevy API."""
    from hevy_client import HevyClient
    key = _get_db_api_key(db)
    client = HevyClient(api_key=key)
    ok = client.test_connection()
    return {"ok": ok}

# ── Training Load (ATL / CTL / TSB) ──────────────────────────────────────────

def _compute_training_load(days: int, db: Session) -> list[dict]:
    """
    Calculate ATL, CTL, and TSB for each day using exponentially weighted
    moving averages of the combined daily stress score (central + peripheral).

    ATL (Acute Training Load)   — 7-day EWMA  — short-term fatigue
    CTL (Chronic Training Load) — 28-day EWMA — long-term fitness baseline
    TSB (Training Stress Balance) = CTL - ATL  — positive = fresh, negative = fatigued
    """
    k_atl = 2 / (7  + 1)   # ≈ 0.250
    k_ctl = 2 / (28 + 1)   # ≈ 0.069

    # Pull enough history for CTL to converge (at least 90 days behind)
    lookback = max(days + 90, 120)
    from_date = date_type.today() - timedelta(days=lookback)

    # Get every distinct workout date in the lookback window
    workout_dates = (
        db.query(WorkoutLog.date)
        .filter(WorkoutLog.date >= from_date)
        .distinct()
        .order_by(WorkoutLog.date)
        .all()
    )

    # Build a dict of date → combined stress using the same RPE-based calculator
    # used everywhere else (central + peripheral computed from actual sets)
    stress_by_date = {}
    for row in workout_dates:
        scores = calculate_stress_scores(row.date, db)
        stress_by_date[row.date] = scores["central"] + scores["peripheral"]

    # Walk day-by-day applying EWMA
    atl, ctl = 0.0, 0.0
    atl_max, ctl_max = 0.0, 0.0
    results = []
    start = from_date
    end   = date_type.today()
    current = start
    cutoff  = date_type.today() - timedelta(days=days - 1)

    while current <= end:
        stress = stress_by_date.get(current, 0.0)
        atl = stress * k_atl + atl * (1 - k_atl)
        ctl = stress * k_ctl + ctl * (1 - k_ctl)
        tsb = ctl - atl

        # Track full-lookback maxima for normalization (not just the display window)
        if atl > atl_max:
            atl_max = atl
        if ctl > ctl_max:
            ctl_max = ctl

        if current >= cutoff:
            results.append({
                "date":       str(current),
                "atl":        round(atl, 2),
                "ctl":        round(ctl, 2),
                "tsb":        round(tsb, 2),
                "stress":     round(stress, 2),
            })
        current += timedelta(days=1)

    return results, max(atl_max, 1.0), max(ctl_max, 1.0)


def _tsb_recommendation(tsb: float) -> str:
    if   tsb >  15: return "large_increase"
    elif tsb >   5: return "increase"
    elif tsb >  -5: return "continue"
    elif tsb > -15: return "decrease"
    else:           return "large_decrease"


@app.get("/api/training-load")
def get_training_load(days: int = 60, db: Session = Depends(get_db)):
    """
    Return ATL/CTL/TSB history for the chart and today's summary values.
    """
    history, atl_max, ctl_max = _compute_training_load(days, db)
    today = history[-1] if history else {"date": str(date_type.today()), "atl": 0, "ctl": 0, "tsb": 0, "stress": 0}

    # Normalize ATL and CTL to a 0–10 scale relative to the user's own peak
    atl_score = round(min(10.0, (today["atl"] / atl_max) * 10), 1)
    ctl_score = round(min(10.0, (today["ctl"] / ctl_max) * 10), 1)

    # CTL trend: compare today vs 7 days ago (rising/flat/declining)
    ctl_7d_ago = history[-8]["ctl"] if len(history) >= 8 else None
    if ctl_7d_ago and ctl_7d_ago > 0:
        ctl_pct_change = (today["ctl"] - ctl_7d_ago) / ctl_7d_ago * 100
        ctl_trend = "building" if ctl_pct_change > 1 else "declining" if ctl_pct_change < -1 else "maintaining"
    else:
        ctl_trend = "maintaining"

    return {
        "today": {
            "date":           today["date"],
            "atl":            today["atl"],
            "ctl":            today["ctl"],
            "tsb":            today["tsb"],
            "atl_score":      atl_score,
            "ctl_score":      ctl_score,
            "ctl_trend":      ctl_trend,
            "recommendation": _tsb_recommendation(today["tsb"]),
        },
        "history": history,
    }


# ── Readiness history ─────────────────────────────────────────────────────────

@app.get("/api/readiness/history")
def get_readiness_history(days: int = 30, db: Session = Depends(get_db)):
    """
    Return daily check-in scores for the recovery trend chart.
    recovery_score = tiredness + perceived_recovery (0–8, lower = more recovered)
    """
    from_date = date_type.today() - timedelta(days=days - 1)
    rows = (
        db.query(DailyReadiness)
        .filter(DailyReadiness.date >= from_date)
        .order_by(DailyReadiness.date)
        .all()
    )
    return [
        {
            "date":             str(r.date),
            "recovery_score":   (r.tiredness or 0) + (r.perceived_recovery or 0),
            "tiredness":        r.tiredness,
            "perceived_recovery": r.perceived_recovery,
            "soreness":         (r.sore_quad_dom or 0) + (r.sore_posterior or 0)
                                + (r.sore_upper_push or 0) + (r.sore_upper_pull or 0),
            "joint":            (r.joint_upper or 0) + (r.joint_lower or 0),
            "hrv_ms":           r.hrv_ms,
            "sleep_hours":      r.sleep_hours,
        }
        for r in rows
    ]


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
        central = get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
        peripheral = get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)

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
    """Submit the daily readiness check-in."""
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
        peripheral_stress=stress["peripheral"],
        hrv_ms=data.hrv_ms,
        sleep_hours=data.sleep_hours,
        sleep_quality=data.sleep_quality,
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

@app.get("/api/readiness/log")
def get_readiness_log(db: Session = Depends(get_db)):
    """Return all readiness entries with full fields, newest first."""
    entries = (
        db.query(DailyReadiness)
        .order_by(DailyReadiness.date.desc())
        .all()
    )
    return [
        {
            "date":               str(e.date),
            "weight_lbs":         e.weight_lbs,
            "sore_quad_dom":      e.sore_quad_dom  or 0,
            "sore_posterior":     e.sore_posterior  or 0,
            "sore_upper_push":    e.sore_upper_push or 0,
            "sore_upper_pull":    e.sore_upper_pull or 0,
            "joint_upper":        e.joint_upper     or 0,
            "joint_lower":        e.joint_lower     or 0,
            "tiredness":          e.tiredness       or 0,
            "perceived_recovery": e.perceived_recovery or 0,
            "central_stress":     e.central_stress,
            "peripheral_stress":  e.peripheral_stress,
            "hrv_ms":             e.hrv_ms,
            "sleep_hours":        e.sleep_hours,
            "sleep_quality":      e.sleep_quality,
        }
        for e in entries
    ]

@app.put("/api/readiness/{entry_date}")
def update_readiness(entry_date: date_type, data: ReadinessUpdate, db: Session = Depends(get_db)):
    """Update the subjective fields of an existing readiness entry."""
    entry = db.query(DailyReadiness).filter(DailyReadiness.date == entry_date).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"No readiness entry for {entry_date}")
    entry.weight_lbs         = data.weight_lbs
    entry.sore_quad_dom      = data.sore_quad_dom
    entry.sore_posterior     = data.sore_posterior
    entry.sore_upper_push    = data.sore_upper_push
    entry.sore_upper_pull    = data.sore_upper_pull
    entry.joint_upper        = data.joint_upper
    entry.joint_lower        = data.joint_lower
    entry.tiredness          = data.tiredness
    entry.perceived_recovery = data.perceived_recovery
    entry.hrv_ms             = data.hrv_ms
    entry.sleep_hours        = data.sleep_hours
    entry.sleep_quality      = data.sleep_quality
    db.commit()
    return {"message": "Entry updated", "date": str(entry_date)}

@app.delete("/api/readiness/{entry_date}")
def delete_readiness(entry_date: date_type, db: Session = Depends(get_db)):
    """Delete a readiness entry by date."""
    entry = db.query(DailyReadiness).filter(DailyReadiness.date == entry_date).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"No readiness entry for {entry_date}")
    db.delete(entry)
    db.commit()
    return {"message": "Entry deleted", "date": str(entry_date)}

@app.get("/api/workouts/recent")
def get_recent_workouts(count: int = 12, db: Session = Depends(get_db)):
    """Return the N most recent workouts with per-workout stress calculations."""
    workout_groups = (
        db.query(
            WorkoutLog.date,
            WorkoutLog.workout_id,
            WorkoutLog.workout_title,
            func.count(WorkoutLog.id).label('set_count'),
            func.sum(WorkoutLog.weight_lbs * WorkoutLog.reps).label('volume'),
            func.avg(WorkoutLog.rpe).label('avg_rpe'),
        )
        .group_by(WorkoutLog.workout_id, WorkoutLog.date, WorkoutLog.workout_title)
        .order_by(WorkoutLog.date.desc(), WorkoutLog.workout_id.desc())
        .limit(count)
        .all()
    )

    result = []
    for row in workout_groups:
        # Stress calculated from this workout's sets only (not the whole day)
        workout_sets = db.query(WorkoutLog).filter(
            WorkoutLog.workout_id == row.workout_id
        ).all()

        central = sum(
            get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
            for s in workout_sets
        )
        peripheral = sum(
            get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
            for s in workout_sets
        )

        result.append({
            "date":              str(row.date),
            "workout_title":     row.workout_title,
            "set_count":         row.set_count,
            "volume":            round(float(row.volume or 0), 0),
            "avg_rpe":           round(row.avg_rpe, 1) if row.avg_rpe else None,
            "central_stress":    round(central, 3),
            "peripheral_stress": round(peripheral, 3),
        })

    return result


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
    """Return all exercise movement pattern mappings with usage stats from WorkoutLog."""
    q = db.query(ExerciseMapping)
    if unreviewed:
        q = q.filter(ExerciseMapping.is_reviewed == False)
    mappings = q.order_by(ExerciseMapping.exercise_title).all()

    # Pull set count and most-recent date for every exercise in one query
    usage_rows = db.query(
        WorkoutLog.exercise_title,
        func.count(WorkoutLog.id).label("use_count"),
        func.max(WorkoutLog.date).label("last_used"),
    ).group_by(WorkoutLog.exercise_title).all()

    usage = {r.exercise_title: {"use_count": r.use_count, "last_used": str(r.last_used)} for r in usage_rows}

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
            "use_count": usage.get(m.exercise_title, {}).get("use_count", 0),
            "last_used": usage.get(m.exercise_title, {}).get("last_used", None),
        }
        for m in mappings
    ]

@app.put("/api/exercises/mappings/{mapping_id}")
def update_exercise_mapping(
    mapping_id: int, data: MappingUpdate, db: Session = Depends(get_db)
):
    """Update a movement pattern mapping by numeric ID. Marks source as 'user' and is_reviewed as True."""
    mapping = db.query(ExerciseMapping).filter(
        ExerciseMapping.id == mapping_id
    ).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Exercise mapping #{mapping_id} not found.")

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
