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
    return _get_fernet().decrypt(ciphertext.encode()).decode()
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
RESOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

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
    sore_quad_dom: Optional[int] = Field(None, ge=0, le=4)
    sore_posterior: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_push: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_pull: Optional[int] = Field(None, ge=0, le=4)
    joint_upper: Optional[int] = Field(None, ge=0, le=4)
    joint_lower: Optional[int] = Field(None, ge=0, le=4)
    tiredness: Optional[int] = Field(None, ge=0, le=4)
    perceived_recovery: Optional[int] = Field(None, ge=0, le=4)

class ReadinessUpdate(BaseModel):
    sore_quad_dom: Optional[int] = Field(None, ge=0, le=4)
    sore_posterior: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_push: Optional[int] = Field(None, ge=0, le=4)
    sore_upper_pull: Optional[int] = Field(None, ge=0, le=4)
    joint_upper: Optional[int] = Field(None, ge=0, le=4)
    joint_lower: Optional[int] = Field(None, ge=0, le=4)
    tiredness: Optional[int] = Field(None, ge=0, le=4)
    perceived_recovery: Optional[int] = Field(None, ge=0, le=4)

class SettingsInput(BaseModel):
    hevy_api_key: str

class CalibrationSettingsInput(BaseModel):
    enabled: bool = False
    threshold_large_decrease: float = Field(8.0, ge=0.0, le=10.0)
    threshold_decrease: float = Field(6.5, ge=0.0, le=10.0)
    threshold_continue: float = Field(4.5, ge=0.0, le=10.0)
    threshold_increase: float = Field(3.0, ge=0.0, le=10.0)
    adaptive_enabled: bool = False
    adaptive_lookback_days: int = Field(90, ge=30, le=180)
    adaptive_min_entries: int = Field(21, ge=7, le=120)

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

    # Backfill-safe conditioning exclusion:
    # prefer per-set snapshot flag, with ExerciseMapping fallback for legacy rows.
    exercise_titles = {s.exercise_title for s in sets if s.exercise_title}
    conditioning_titles = set()
    if exercise_titles:
        mapping_rows = (
            db.query(ExerciseMapping.exercise_title)
            .filter(
                ExerciseMapping.exercise_title.in_(exercise_titles),
                ExerciseMapping.is_conditioning == True,
            )
            .all()
        )
        conditioning_titles = {row.exercise_title for row in mapping_rows}

    working_sets = [
        s for s in sets
        if not (s.is_conditioning or s.exercise_title in conditioning_titles)
    ]

    central = sum(
        get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
        for s in working_sets
    )
    peripheral = sum(
        get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
        for s in working_sets
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
    try:
        return _decrypt(row.value)
    except Exception:
        # One-time compatibility migration from legacy plaintext storage.
        legacy_plaintext = row.value.strip()
        if not legacy_plaintext:
            return None
        row.value = _encrypt(legacy_plaintext)
        db.commit()
        return legacy_plaintext

_CALIBRATION_DEFAULTS = {
    "enabled": False,
    "threshold_large_decrease": 8.0,
    "threshold_decrease": 6.5,
    "threshold_continue": 4.5,
    "threshold_increase": 3.0,
    "adaptive_enabled": False,
    "adaptive_lookback_days": 90,
    "adaptive_min_entries": 21,
}

def _get_setting_value(db: Session, key: str) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None

def _set_setting_value(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))

def _validate_calibration_thresholds(cfg: dict) -> None:
    if not (
        cfg["threshold_large_decrease"] >= cfg["threshold_decrease"] >=
        cfg["threshold_continue"] >= cfg["threshold_increase"] >= 0.0
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Thresholds must be ordered: "
                "large_decrease >= decrease >= continue >= increase >= 0"
            ),
        )

def _get_calibration_settings(db: Session) -> dict:
    def _safe_float(raw: str | None, default: float) -> float:
        if raw is None:
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def _safe_int(raw: str | None, default: int) -> int:
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    enabled_raw = _get_setting_value(db, "fatigue_calibration_enabled")
    ld_raw = _get_setting_value(db, "fatigue_threshold_large_decrease")
    d_raw = _get_setting_value(db, "fatigue_threshold_decrease")
    c_raw = _get_setting_value(db, "fatigue_threshold_continue")
    i_raw = _get_setting_value(db, "fatigue_threshold_increase")
    adaptive_enabled_raw = _get_setting_value(db, "fatigue_calibration_adaptive_enabled")
    adaptive_lookback_raw = _get_setting_value(db, "fatigue_calibration_adaptive_lookback_days")
    adaptive_min_raw = _get_setting_value(db, "fatigue_calibration_adaptive_min_entries")

    cfg = {
        "enabled": enabled_raw == "1" if enabled_raw is not None else _CALIBRATION_DEFAULTS["enabled"],
        "threshold_large_decrease": _safe_float(ld_raw, _CALIBRATION_DEFAULTS["threshold_large_decrease"]),
        "threshold_decrease": _safe_float(d_raw, _CALIBRATION_DEFAULTS["threshold_decrease"]),
        "threshold_continue": _safe_float(c_raw, _CALIBRATION_DEFAULTS["threshold_continue"]),
        "threshold_increase": _safe_float(i_raw, _CALIBRATION_DEFAULTS["threshold_increase"]),
        "adaptive_enabled": adaptive_enabled_raw == "1" if adaptive_enabled_raw is not None else _CALIBRATION_DEFAULTS["adaptive_enabled"],
        "adaptive_lookback_days": _safe_int(adaptive_lookback_raw, _CALIBRATION_DEFAULTS["adaptive_lookback_days"]),
        "adaptive_min_entries": _safe_int(adaptive_min_raw, _CALIBRATION_DEFAULTS["adaptive_min_entries"]),
    }
    return cfg

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

@app.get("/api/settings/calibration")
def get_calibration_settings(db: Session = Depends(get_db)):
    """Return fatigue recommendation calibration settings."""
    cfg = _get_calibration_settings(db)
    _validate_calibration_thresholds(cfg)
    return cfg

@app.put("/api/settings/calibration")
def save_calibration_settings(data: CalibrationSettingsInput, db: Session = Depends(get_db)):
    """Save user-defined fatigue recommendation thresholds (opt-in)."""
    cfg = {
        "enabled": data.enabled,
        "threshold_large_decrease": round(float(data.threshold_large_decrease), 2),
        "threshold_decrease": round(float(data.threshold_decrease), 2),
        "threshold_continue": round(float(data.threshold_continue), 2),
        "threshold_increase": round(float(data.threshold_increase), 2),
        "adaptive_enabled": data.adaptive_enabled,
        "adaptive_lookback_days": int(data.adaptive_lookback_days),
        "adaptive_min_entries": int(data.adaptive_min_entries),
    }
    _validate_calibration_thresholds(cfg)

    _set_setting_value(db, "fatigue_calibration_enabled", "1" if cfg["enabled"] else "0")
    _set_setting_value(db, "fatigue_threshold_large_decrease", str(cfg["threshold_large_decrease"]))
    _set_setting_value(db, "fatigue_threshold_decrease", str(cfg["threshold_decrease"]))
    _set_setting_value(db, "fatigue_threshold_continue", str(cfg["threshold_continue"]))
    _set_setting_value(db, "fatigue_threshold_increase", str(cfg["threshold_increase"]))
    _set_setting_value(db, "fatigue_calibration_adaptive_enabled", "1" if cfg["adaptive_enabled"] else "0")
    _set_setting_value(db, "fatigue_calibration_adaptive_lookback_days", str(cfg["adaptive_lookback_days"]))
    _set_setting_value(db, "fatigue_calibration_adaptive_min_entries", str(cfg["adaptive_min_entries"]))
    db.commit()
    return {"message": "Calibration settings saved.", **cfg}

@app.post("/api/settings/calibration/reset")
def reset_calibration_settings(db: Session = Depends(get_db)):
    """Reset fatigue recommendation thresholds to defaults and disable calibration."""
    defaults = dict(_CALIBRATION_DEFAULTS)
    _set_setting_value(db, "fatigue_calibration_enabled", "0")
    _set_setting_value(db, "fatigue_threshold_large_decrease", str(defaults["threshold_large_decrease"]))
    _set_setting_value(db, "fatigue_threshold_decrease", str(defaults["threshold_decrease"]))
    _set_setting_value(db, "fatigue_threshold_continue", str(defaults["threshold_continue"]))
    _set_setting_value(db, "fatigue_threshold_increase", str(defaults["threshold_increase"]))
    _set_setting_value(db, "fatigue_calibration_adaptive_enabled", "0")
    _set_setting_value(db, "fatigue_calibration_adaptive_lookback_days", str(defaults["adaptive_lookback_days"]))
    _set_setting_value(db, "fatigue_calibration_adaptive_min_entries", str(defaults["adaptive_min_entries"]))
    db.commit()
    return {"message": "Calibration settings reset.", **defaults}

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


_REC_LEVELS = ["large_decrease", "decrease", "continue", "increase", "large_increase"]

def _tsb_recommendation(tsb: float) -> str:
    if   tsb >  15: return "large_increase"
    elif tsb >  10: return "increase"
    elif tsb > -10: return "continue"
    elif tsb > -15: return "decrease"
    else:           return "large_decrease"

def _subjective_fatigue(entry) -> float:
    """0.0 (fully fresh) → 1.0 (maximally fatigued) from a DailyReadiness entry."""
    t = (entry.tiredness          or 0) / 4
    r = (entry.perceived_recovery or 0) / 4
    s = ((entry.sore_quad_dom  or 0) + (entry.sore_posterior  or 0) +
         (entry.sore_upper_push or 0) + (entry.sore_upper_pull or 0)) / 16
    j = ((entry.joint_upper or 0) + (entry.joint_lower or 0)) / 8
    # Subjective base weighting (global score):
    # tiredness/recovery dominate, soreness/joints remain meaningful secondary signals.
    return round(0.40 * t + 0.30 * r + 0.20 * s + 0.10 * j, 3)

def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))

def _training_modifier(history: list[dict]) -> float:
    """
    Convert recent training stress into a bounded fatigue modifier.

    Positive modifier increases fatigue score (worse); negative reduces it.
    Uses a weighted 3-day recent load vs personal baseline for adaptability.
    """
    if not history:
        return 0.0

    stresses = [max(0.0, float(day.get("stress", 0.0))) for day in history]
    if not any(stresses):
        return 0.0

    return _training_modifier_for_index(stresses, len(stresses) - 1)

def _training_modifier_for_index(stresses: list[float], idx: int) -> float:
    """Compute bounded training modifier using a given day index in a stress series."""
    if not stresses or idx < 0 or idx >= len(stresses):
        return 0.0

    s1 = stresses[idx]
    s2 = stresses[idx - 1] if idx - 1 >= 0 else 0.0
    s3 = stresses[idx - 2] if idx - 2 >= 0 else 0.0
    recent_load = (1.0 * s1 + 0.6 * s2 + 0.3 * s3) / 1.9

    baseline_pool = stresses[:max(0, idx - 2)]
    baseline_slice = baseline_pool[-28:] if baseline_pool else stresses[:idx + 1]
    baseline_load = (sum(baseline_slice) / len(baseline_slice)) if baseline_slice else recent_load

    if baseline_load <= 0:
        return 0.0

    relative_delta = (recent_load - baseline_load) / baseline_load
    return round(_clamp(relative_delta * 1.2, -1.5, 1.5), 2)

def _fatigue_recommendation(fatigue_score: float, thresholds: dict | None = None) -> str:
    """Map 0-10 fatigue score (10 = worst) to recommendation buckets."""
    cfg = thresholds or _CALIBRATION_DEFAULTS
    ld = float(cfg.get("threshold_large_decrease", _CALIBRATION_DEFAULTS["threshold_large_decrease"]))
    d = float(cfg.get("threshold_decrease", _CALIBRATION_DEFAULTS["threshold_decrease"]))
    c = float(cfg.get("threshold_continue", _CALIBRATION_DEFAULTS["threshold_continue"]))
    i = float(cfg.get("threshold_increase", _CALIBRATION_DEFAULTS["threshold_increase"]))

    if fatigue_score >= ld:
        return "large_decrease"
    if fatigue_score >= d:
        return "decrease"
    if fatigue_score >= c:
        return "continue"
    if fatigue_score >= i:
        return "increase"
    return "large_increase"

def _adjusted_recommendation(base_rec: str, subj: float) -> str:
    level = _REC_LEVELS.index(base_rec)
    if   subj >= 0.75: adj = -2
    elif subj >= 0.50: adj = -1
    elif subj <  0.15: adj = +1
    else:              adj =  0
    return _REC_LEVELS[max(0, min(4, level + adj))]

def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile for an unsorted list."""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    ordered = sorted(values)
    idx = (p / 100.0) * (len(ordered) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    frac = idx - lower
    return (ordered[lower] * (1 - frac)) + (ordered[upper] * frac)

def _recent_fatigue_scores_for_adaptive(db: Session, lookback_days: int) -> list[float]:
    """Compute recent fatigue scores (0..10) from readiness entries for adaptive thresholds."""
    from_date = date_type.today() - timedelta(days=max(1, lookback_days) - 1)
    readiness_rows = (
        db.query(DailyReadiness)
        .filter(DailyReadiness.date >= from_date)
        .order_by(DailyReadiness.date)
        .all()
    )
    if not readiness_rows:
        return []

    history, _, _ = _compute_training_load(max(lookback_days, 30), db)
    history_index = {h["date"]: idx for idx, h in enumerate(history)}
    stress_series = [max(0.0, float(h.get("stress", 0.0))) for h in history]

    scores: list[float] = []
    for entry in readiness_rows:
        date_key = str(entry.date)
        subj = _subjective_fatigue(entry)
        idx = history_index.get(date_key)
        training_mod = _training_modifier_for_index(stress_series, idx) if idx is not None else 0.0
        score = _clamp((subj * 10) + training_mod, 0.0, 10.0)
        scores.append(round(score, 2))
    return scores

def _resolve_recommendation_thresholds(db: Session, calibration: dict | None = None) -> dict:
    """Resolve active thresholds and mode (default/custom/adaptive/adaptive_fallback)."""
    cfg = calibration or _get_calibration_settings(db)

    if bool(cfg.get("enabled", False)):
        base = {
            "threshold_large_decrease": float(cfg.get("threshold_large_decrease", _CALIBRATION_DEFAULTS["threshold_large_decrease"])),
            "threshold_decrease": float(cfg.get("threshold_decrease", _CALIBRATION_DEFAULTS["threshold_decrease"])),
            "threshold_continue": float(cfg.get("threshold_continue", _CALIBRATION_DEFAULTS["threshold_continue"])),
            "threshold_increase": float(cfg.get("threshold_increase", _CALIBRATION_DEFAULTS["threshold_increase"])),
        }
        mode = "custom"
    else:
        base = {
            "threshold_large_decrease": _CALIBRATION_DEFAULTS["threshold_large_decrease"],
            "threshold_decrease": _CALIBRATION_DEFAULTS["threshold_decrease"],
            "threshold_continue": _CALIBRATION_DEFAULTS["threshold_continue"],
            "threshold_increase": _CALIBRATION_DEFAULTS["threshold_increase"],
        }
        mode = "default"

    if not bool(cfg.get("adaptive_enabled", False)):
        return {"mode": mode, "sample_size": 0, **base}

    lookback_days = int(cfg.get("adaptive_lookback_days", _CALIBRATION_DEFAULTS["adaptive_lookback_days"]))
    min_entries = int(cfg.get("adaptive_min_entries", _CALIBRATION_DEFAULTS["adaptive_min_entries"]))
    scores = _recent_fatigue_scores_for_adaptive(db, lookback_days)
    sample_size = len(scores)

    if sample_size < min_entries:
        return {"mode": "adaptive_fallback", "sample_size": sample_size, **base}

    adaptive = {
        "threshold_large_decrease": round(_percentile(scores, 80), 2),
        "threshold_decrease": round(_percentile(scores, 60), 2),
        "threshold_continue": round(_percentile(scores, 40), 2),
        "threshold_increase": round(_percentile(scores, 20), 2),
    }
    return {"mode": "adaptive", "sample_size": sample_size, **adaptive}


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

    # Keep TSB recommendation available for legacy context displays.
    tsb_rec = _tsb_recommendation(today["tsb"])

    # Subjective-first model: check-in defines the base fatigue score.
    # Training stress modifies the base score in a bounded way.
    training_mod = _training_modifier(history)
    checkin = db.query(DailyReadiness).filter(
        DailyReadiness.date == date_type.today()
    ).first()
    if checkin:
        subj = _subjective_fatigue(checkin)
        subjective_base_score = round(subj * 10, 2)
        fatigue_score = round(_clamp(subjective_base_score + training_mod, 0.0, 10.0), 2)
        score_source = "subjective_plus_training"
    else:
        subj = None
        subjective_base_score = None
        # If no check-in exists today, provide a neutral fallback adjusted by training.
        fatigue_score = round(_clamp(5.0 + training_mod, 0.0, 10.0), 2)
        score_source = "training_fallback"

    calibration = _get_calibration_settings(db)
    thresholds = _resolve_recommendation_thresholds(db, calibration)
    fatigue_rec = _fatigue_recommendation(fatigue_score, thresholds)

    # Enrich history items with fatigue_score and recommendation_adjusted.
    # Fetch all readiness entries for the history window in one query.
    history_dates = [h["date"] for h in history]
    if history_dates:
        from datetime import date as _date_cls
        earliest_hist = min(history_dates)
        readiness_rows = (
            db.query(DailyReadiness)
            .filter(DailyReadiness.date >= earliest_hist)
            .all()
        )
        readiness_by_date = {str(r.date): r for r in readiness_rows}
    else:
        readiness_by_date = {}

    stress_series_hist = [max(0.0, float(h.get("stress", 0.0))) for h in history]
    for idx, item in enumerate(history):
        r_entry = readiness_by_date.get(item["date"])
        t_mod = _training_modifier_for_index(stress_series_hist, idx)
        if r_entry:
            h_subj = _subjective_fatigue(r_entry)
            h_fatigue = round(_clamp(h_subj * 10 + t_mod, 0.0, 10.0), 2)
        else:
            h_fatigue = round(_clamp(5.0 + t_mod, 0.0, 10.0), 2)
        item["fatigue_score"] = h_fatigue
        item["recommendation_adjusted"] = _fatigue_recommendation(h_fatigue, thresholds)

    return {
        "today": {
            "date":                    today["date"],
            "atl":                     today["atl"],
            "ctl":                     today["ctl"],
            "tsb":                     today["tsb"],
            "atl_score":               atl_score,
            "ctl_score":               ctl_score,
            "ctl_trend":               ctl_trend,
            "fatigue_score":           fatigue_score,
            "subjective_base_score":   subjective_base_score,
            "training_modifier":       training_mod,
            "score_source":            score_source,
            "tiredness":               checkin.tiredness           if checkin else None,
            "perceived_recovery":      checkin.perceived_recovery  if checkin else None,
            "recommendation":          tsb_rec,
            "recommendation_adjusted": fatigue_rec,
            "recommendation_legacy_tsb": tsb_rec,
            "subj_fatigue":            subj,
            "calibration_enabled":      calibration.get("enabled", False),
            "recommendation_mode":      thresholds.get("mode", "default"),
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
def get_readiness_entries(days: int = 30, db: Session = Depends(get_db)):
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
    if not entries:
        return []

    earliest = min(e.date for e in entries)
    days_back = (date_type.today() - earliest).days + 1
    history, _, _ = _compute_training_load(max(days_back, 30), db)
    tsb_by_date = {h["date"]: h["tsb"] for h in history}
    history_index = {h["date"]: idx for idx, h in enumerate(history)}
    stress_series = [max(0.0, float(h.get("stress", 0.0))) for h in history]

    calibration = _get_calibration_settings(db)
    thresholds = _resolve_recommendation_thresholds(db, calibration)

    result = []
    for e in entries:
        date_key = str(e.date)
        tsb = tsb_by_date.get(date_key, 0.0)
        base_rec = _tsb_recommendation(tsb)
        subj = _subjective_fatigue(e)
        subj_base_score = round(subj * 10, 2)

        idx = history_index.get(date_key)
        training_mod = _training_modifier_for_index(stress_series, idx) if idx is not None else 0.0
        fatigue_score = round(_clamp(subj_base_score + training_mod, 0.0, 10.0), 2)
        adj_rec = _fatigue_recommendation(fatigue_score, thresholds)

        result.append({
            "date":                    date_key,
            "sore_quad_dom":           e.sore_quad_dom      or 0,
            "sore_posterior":          e.sore_posterior      or 0,
            "sore_upper_push":         e.sore_upper_push     or 0,
            "sore_upper_pull":         e.sore_upper_pull     or 0,
            "joint_upper":             e.joint_upper         or 0,
            "joint_lower":             e.joint_lower         or 0,
            "tiredness":               e.tiredness           or 0,
            "perceived_recovery":      e.perceived_recovery  or 0,
            "central_stress":          e.central_stress,
            "peripheral_stress":       e.peripheral_stress,
            "fatigue_score":           fatigue_score,
            "subjective_base_score":   subj_base_score,
            "training_modifier":       training_mod,
            "recommendation":          base_rec,
            "recommendation_adjusted": adj_rec,
        })
    return result

@app.put("/api/readiness/{entry_date}")
def update_readiness(entry_date: date_type, data: ReadinessUpdate, db: Session = Depends(get_db)):
    """Update the subjective fields of an existing readiness entry."""
    entry = db.query(DailyReadiness).filter(DailyReadiness.date == entry_date).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"No readiness entry for {entry_date}")
    entry.sore_quad_dom      = data.sore_quad_dom
    entry.sore_posterior     = data.sore_posterior
    entry.sore_upper_push    = data.sore_upper_push
    entry.sore_upper_pull    = data.sore_upper_pull
    entry.joint_upper        = data.joint_upper
    entry.joint_lower        = data.joint_lower
    entry.tiredness          = data.tiredness
    entry.perceived_recovery = data.perceived_recovery
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

    total_pct = data.pct_quad_dom + data.pct_posterior + data.pct_upper_push + data.pct_upper_pull
    if data.is_conditioning:
        # Conditioning entries are excluded from movement-pattern stress.
        pct_quad_dom = 0.0
        pct_posterior = 0.0
        pct_upper_push = 0.0
        pct_upper_pull = 0.0
    else:
        if abs(total_pct - 1.0) > 0.005:
            raise HTTPException(
                status_code=422,
                detail="Pattern percentages must sum to 1.0 (±0.005) unless stress exclusion is enabled.",
            )
        pct_quad_dom = data.pct_quad_dom
        pct_posterior = data.pct_posterior
        pct_upper_push = data.pct_upper_push
        pct_upper_pull = data.pct_upper_pull

    mapping.pct_quad_dom    = pct_quad_dom
    mapping.pct_posterior   = pct_posterior
    mapping.pct_upper_push  = pct_upper_push
    mapping.pct_upper_pull  = pct_upper_pull
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
if os.path.isdir(RESOURCES_DIR):
    app.mount("/resources", StaticFiles(directory=RESOURCES_DIR), name="resources")
