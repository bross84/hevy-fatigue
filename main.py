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

from database import SessionLocal, DailyReadiness, WorkoutLog, WorkoutSession, ExerciseMapping, AppSetting, init_db

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
    v2_threshold_stressed: float = Field(0.75, ge=0.0, le=1.0)
    v2_threshold_neutral: float = Field(0.50, ge=0.0, le=1.0)
    tsb_threshold_underloaded: float = Field(8.0, ge=-50.0, le=50.0)
    tsb_threshold_slightly_fresh: float = Field(3.0, ge=-50.0, le=50.0)
    tsb_threshold_balanced: float = Field(-5.0, ge=-50.0, le=50.0)
    tsb_threshold_slightly_fatigued: float = Field(-10.0, ge=-50.0, le=50.0)
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


class SessionVerificationUpdate(BaseModel):
    modality: str
    duration_minutes: Optional[int] = Field(None, ge=1, le=480)
    srpe: Optional[float] = Field(None, ge=0.0, le=10.0)


class SessionStatusUpdate(BaseModel):
    verification_status: str = Field(pattern="^(pending|verified)$")
    modality: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=480)
    srpe: Optional[float] = Field(None, ge=0.0, le=10.0)

# --- Stress Calculators ---
def calculate_stress_scores(target_date: date_type, db: Session) -> dict:
    """
    Calculate central and peripheral stress for a given day across three pathways,
    plus per-pattern (knee/hip/push/pull) stress for Stage 5 EWMA inputs.

    Pathway 1 — Strength / Hypertrophy (per-set RPE math, unchanged):
        central_stress    = sum of (pct² × reps) — intensity-driven, reflects CNS fatigue
        peripheral_stress = sum of (pct  × reps) — volume-driven, reflects muscular fatigue
        pattern_stress[p] = sum of (central_i + peripheral_i) × pct_p  — per set

    Pathway 2 — Conditioning (verified sessions only):
        raw = (srpe × duration_minutes) / scaling_factor
        central   = raw × Σ avg_pct_i²
        peripheral = raw × Σ avg_pct_i
        pattern_stress[p] = raw × avg_pct_p   (per session)

    Pathway 3 — Cardio (verified sessions only):
        raw = (srpe × duration_minutes) / scaling_factor
        central   = raw × 0.30
        peripheral = raw × 0.70
        pattern_stress — zero (cardio has no pattern distribution)

    Unverified conditioning/cardio sessions contribute zero stress (silent).
    Multiple sessions on the same date are summed.
    Returns {"central": float, "peripheral": float, "knee": float, "hip": float, "push": float, "pull": float}
    """
    sets = db.query(WorkoutLog).filter(WorkoutLog.date == target_date).all()

    # ── Pathway 1: Strength / Hypertrophy ────────────────────────────────────
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

    # Fetch pct mappings for all working-set exercises in one query so pattern
    # stress can be accumulated in the same pass as central/peripheral.
    strength_titles = {s.exercise_title for s in working_sets if s.exercise_title}
    pct_map: dict = {}
    if strength_titles:
        pct_rows = (
            db.query(ExerciseMapping)
            .filter(ExerciseMapping.exercise_title.in_(strength_titles))
            .all()
        )
        pct_map = {m.exercise_title: m for m in pct_rows}

    central = peripheral = 0.0
    knee = hip = push = pull = 0.0

    for s in working_sets:
        c = get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
        p = get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
        central    += c
        peripheral += p
        m = pct_map.get(s.exercise_title)
        if m:
            ss = c + p
            knee += ss * (m.pct_quad_dom    or 0.0)
            hip  += ss * (m.pct_posterior   or 0.0)
            push += ss * (m.pct_upper_push  or 0.0)
            pull += ss * (m.pct_upper_pull  or 0.0)

    # ── Pathways 2 & 3: Conditioning / Cardio ────────────────────────────────
    scaling_factor = _get_conditioning_scaling_factor(db)

    cond_sessions = (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.workout_date == target_date,
            WorkoutSession.verification_status == "verified",
            WorkoutSession.srpe.isnot(None),
            WorkoutSession.duration_minutes.isnot(None),
            WorkoutSession.modality.in_(["conditioning", "cardio"]),
        )
        .all()
    )

    for session in cond_sessions:
        raw = (session.srpe * session.duration_minutes) / scaling_factor

        if session.modality == "conditioning":
            # Pathway 2: use average ExerciseMapping pcts from this session's sets.
            # central weight = Σ avg_pct_i²  (mirrors strength central formula)
            # peripheral weight = Σ avg_pct_i (mirrors strength peripheral formula)
            session_titles = {
                s.exercise_title
                for s in sets
                if s.workout_id == session.hevy_workout_id and s.exercise_title
            }
            pct_c_weight = 0.0
            pct_p_weight = 0.0
            avg_quad = avg_post = avg_push = avg_pull = 0.0
            if session_titles:
                maps = (
                    db.query(ExerciseMapping)
                    .filter(ExerciseMapping.exercise_title.in_(session_titles))
                    .all()
                )
                if maps:
                    n = len(maps)
                    avg_quad = sum(m.pct_quad_dom    for m in maps) / n
                    avg_post = sum(m.pct_posterior   for m in maps) / n
                    avg_push = sum(m.pct_upper_push  for m in maps) / n
                    avg_pull = sum(m.pct_upper_pull  for m in maps) / n
                    pct_c_weight = avg_quad**2 + avg_post**2 + avg_push**2 + avg_pull**2
                    pct_p_weight = avg_quad    + avg_post    + avg_push    + avg_pull
            if pct_c_weight == 0.0 and pct_p_weight == 0.0:
                # Fallback: equal distribution across four patterns
                avg_quad = avg_post = avg_push = avg_pull = 0.25
                pct_c_weight = 4 * (0.25 ** 2)  # 0.25
                pct_p_weight = 4 *  0.25         # 1.0
            central    += raw * pct_c_weight
            peripheral += raw * pct_p_weight
            # Distribute conditioning stress to pattern buckets
            knee += raw * avg_quad
            hip  += raw * avg_post
            push += raw * avg_push
            pull += raw * avg_pull

        else:
            # Pathway 3: Cardio — flat 30/70 split, no pattern distribution
            central    += raw * 0.30
            peripheral += raw * 0.70
            # Cardio contributes zero to pattern buckets

    return {
        "central":    round(central,    3),
        "peripheral": round(peripheral, 3),
        "knee":       round(knee,       3),
        "hip":        round(hip,        3),
        "push":       round(push,       3),
        "pull":       round(pull,       3),
    }

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

_CONDITIONING_SCALING_DEFAULT = 29.0

_CALIBRATION_DEFAULTS = {
    "enabled": False,
    "threshold_large_decrease": 8.0,
    "threshold_decrease": 6.5,
    "threshold_continue": 4.5,
    "threshold_increase": 3.0,
    "v2_threshold_stressed": 0.75,
    "v2_threshold_neutral": 0.50,
    "tsb_threshold_underloaded": 8.0,
    "tsb_threshold_slightly_fresh": 3.0,
    "tsb_threshold_balanced": -5.0,
    "tsb_threshold_slightly_fatigued": -10.0,
    "adaptive_enabled": False,
    "adaptive_lookback_days": 90,
    "adaptive_min_entries": 21,
}

_VALID_MODALITIES = {"strength", "hypertrophy", "conditioning", "cardio"}


def _normalize_modality(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in _VALID_MODALITIES:
        raise HTTPException(
            status_code=422,
            detail="modality must be one of: strength, hypertrophy, conditioning, cardio",
        )
    return normalized


def _assert_session_can_be_verified(modality: str, duration_minutes: int | None, srpe: float | None) -> None:
    if duration_minutes is None or duration_minutes <= 0 or duration_minutes > 480:
        raise HTTPException(
            status_code=422,
            detail="Valid duration_minutes (1..480) is required before verification.",
        )

    if modality in {"conditioning", "cardio"} and srpe is None:
        raise HTTPException(
            status_code=422,
            detail="sRPE is required to verify conditioning/cardio sessions.",
        )

def _get_setting_value(db: Session, key: str) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None

def _set_setting_value(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))

def _get_conditioning_scaling_factor(db: Session) -> float:
    """
    Read conditioning_stress_scaling_factor from app_settings.
    Normalises (sRPE × duration_minutes) onto the same scale as strength stress.
    Default 29 — chosen so a moderate conditioning session (sRPE 7, 45 min) produces
    a combined stress comparable to a moderate strength day.
    """
    raw = _get_setting_value(db, "conditioning_stress_scaling_factor")
    if raw is None:
        return _CONDITIONING_SCALING_DEFAULT
    try:
        v = float(raw)
        return v if v > 0 else _CONDITIONING_SCALING_DEFAULT
    except (TypeError, ValueError):
        return _CONDITIONING_SCALING_DEFAULT

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

    if not (1.0 >= cfg["v2_threshold_stressed"] >= cfg["v2_threshold_neutral"] >= 0.0):
        raise HTTPException(
            status_code=422,
            detail=(
                "V2 thresholds must be ordered: "
                "stressed >= neutral >= 0"
            ),
        )

    if not (
        cfg["tsb_threshold_underloaded"] >= cfg["tsb_threshold_slightly_fresh"] >=
        cfg["tsb_threshold_balanced"] >= cfg["tsb_threshold_slightly_fatigued"]
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "TSB thresholds must be ordered: "
                "underloaded >= slightly_fresh >= balanced >= slightly_fatigued"
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
    v2_stressed_raw = _get_setting_value(db, "fatigue_v2_threshold_stressed")
    v2_neutral_raw = _get_setting_value(db, "fatigue_v2_threshold_neutral")
    tsb_underloaded_raw = _get_setting_value(db, "tsb_threshold_underloaded")
    tsb_fresh_raw = _get_setting_value(db, "tsb_threshold_slightly_fresh")
    tsb_balanced_raw = _get_setting_value(db, "tsb_threshold_balanced")
    tsb_slightly_fatigued_raw = _get_setting_value(db, "tsb_threshold_slightly_fatigued")
    adaptive_enabled_raw = _get_setting_value(db, "fatigue_calibration_adaptive_enabled")
    adaptive_lookback_raw = _get_setting_value(db, "fatigue_calibration_adaptive_lookback_days")
    adaptive_min_raw = _get_setting_value(db, "fatigue_calibration_adaptive_min_entries")

    cfg = {
        "enabled": enabled_raw == "1" if enabled_raw is not None else _CALIBRATION_DEFAULTS["enabled"],
        "threshold_large_decrease": _safe_float(ld_raw, _CALIBRATION_DEFAULTS["threshold_large_decrease"]),
        "threshold_decrease": _safe_float(d_raw, _CALIBRATION_DEFAULTS["threshold_decrease"]),
        "threshold_continue": _safe_float(c_raw, _CALIBRATION_DEFAULTS["threshold_continue"]),
        "threshold_increase": _safe_float(i_raw, _CALIBRATION_DEFAULTS["threshold_increase"]),
        "v2_threshold_stressed": _safe_float(v2_stressed_raw, _CALIBRATION_DEFAULTS["v2_threshold_stressed"]),
        "v2_threshold_neutral": _safe_float(v2_neutral_raw, _CALIBRATION_DEFAULTS["v2_threshold_neutral"]),
        "tsb_threshold_underloaded": _safe_float(tsb_underloaded_raw, _CALIBRATION_DEFAULTS["tsb_threshold_underloaded"]),
        "tsb_threshold_slightly_fresh": _safe_float(tsb_fresh_raw, _CALIBRATION_DEFAULTS["tsb_threshold_slightly_fresh"]),
        "tsb_threshold_balanced": _safe_float(tsb_balanced_raw, _CALIBRATION_DEFAULTS["tsb_threshold_balanced"]),
        "tsb_threshold_slightly_fatigued": _safe_float(tsb_slightly_fatigued_raw, _CALIBRATION_DEFAULTS["tsb_threshold_slightly_fatigued"]),
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
        "v2_threshold_stressed": round(float(data.v2_threshold_stressed), 3),
        "v2_threshold_neutral": round(float(data.v2_threshold_neutral), 3),
        "tsb_threshold_underloaded": round(float(data.tsb_threshold_underloaded), 2),
        "tsb_threshold_slightly_fresh": round(float(data.tsb_threshold_slightly_fresh), 2),
        "tsb_threshold_balanced": round(float(data.tsb_threshold_balanced), 2),
        "tsb_threshold_slightly_fatigued": round(float(data.tsb_threshold_slightly_fatigued), 2),
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
    _set_setting_value(db, "fatigue_v2_threshold_stressed", str(cfg["v2_threshold_stressed"]))
    _set_setting_value(db, "fatigue_v2_threshold_neutral", str(cfg["v2_threshold_neutral"]))
    _set_setting_value(db, "tsb_threshold_underloaded", str(cfg["tsb_threshold_underloaded"]))
    _set_setting_value(db, "tsb_threshold_slightly_fresh", str(cfg["tsb_threshold_slightly_fresh"]))
    _set_setting_value(db, "tsb_threshold_balanced", str(cfg["tsb_threshold_balanced"]))
    _set_setting_value(db, "tsb_threshold_slightly_fatigued", str(cfg["tsb_threshold_slightly_fatigued"]))
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
    _set_setting_value(db, "fatigue_v2_threshold_stressed", str(defaults["v2_threshold_stressed"]))
    _set_setting_value(db, "fatigue_v2_threshold_neutral", str(defaults["v2_threshold_neutral"]))
    _set_setting_value(db, "tsb_threshold_underloaded", str(defaults["tsb_threshold_underloaded"]))
    _set_setting_value(db, "tsb_threshold_slightly_fresh", str(defaults["tsb_threshold_slightly_fresh"]))
    _set_setting_value(db, "tsb_threshold_balanced", str(defaults["tsb_threshold_balanced"]))
    _set_setting_value(db, "tsb_threshold_slightly_fatigued", str(defaults["tsb_threshold_slightly_fatigued"]))
    _set_setting_value(db, "fatigue_calibration_adaptive_enabled", "0")
    _set_setting_value(db, "fatigue_calibration_adaptive_lookback_days", str(defaults["adaptive_lookback_days"]))
    _set_setting_value(db, "fatigue_calibration_adaptive_min_entries", str(defaults["adaptive_min_entries"]))
    db.commit()
    return {"message": "Calibration settings reset.", **defaults}

# ── Training Load (ATL / CTL / TSB) ──────────────────────────────────────────

def _training_stress_included_through(db: Session) -> date_type:
    """
    Freeze imported workout impact until the next check-in is submitted.

    A readiness entry dated D is assumed to reflect training completed through D-1.
    So only workout stress up to (latest_readiness_date - 1) is allowed to affect
    ATL/CTL/TSB and fatigue recommendation math.
    """
    latest_readiness = db.query(func.max(DailyReadiness.date)).scalar()
    if latest_readiness:
        return latest_readiness - timedelta(days=1)
    return date_type.today() - timedelta(days=1)

def _compute_training_load(days: int, db: Session) -> list[dict]:
    """
    Calculate ATL, CTL, and TSB for each day using exponentially weighted
    moving averages of the combined daily stress score (central + peripheral).

    ATL (Acute Training Load)   — 7-day EWMA  — short-term fatigue
    CTL (Chronic Training Load) — 28-day EWMA — long-term fitness baseline
    TSB (Training Stress Balance) = CTL - ATL  — positive = fresh, negative = fatigued

    Also computes four parallel pattern EWMAs (knee/hip/push/pull) using the
    same k values, sourced from calculate_stress_scores pattern breakdown.
    Pattern loads are included in each history item as "pattern_loads".
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

    # Build dicts of date → combined stress and date → pattern stress
    stress_by_date: dict = {}
    pattern_stress_by_date: dict = {}
    for row in workout_dates:
        scores = calculate_stress_scores(row.date, db)
        stress_by_date[row.date] = scores["central"] + scores["peripheral"]
        pattern_stress_by_date[row.date] = {
            "knee": scores["knee"],
            "hip":  scores["hip"],
            "push": scores["push"],
            "pull": scores["pull"],
        }

    _PATTERNS = ("knee", "hip", "push", "pull")

    # Walk day-by-day applying EWMA
    atl, ctl = 0.0, 0.0
    atl_max, ctl_max = 0.0, 0.0
    p_atl = {p: 0.0 for p in _PATTERNS}
    p_ctl = {p: 0.0 for p in _PATTERNS}
    results = []
    start = from_date
    end   = date_type.today()
    current = start
    cutoff  = date_type.today() - timedelta(days=days - 1)

    included_through = _training_stress_included_through(db)

    while current <= end:
        # Ignore workouts that are newer than the unlocked stress window.
        # They become active once the following day's readiness is submitted.
        locked_in = current <= included_through
        stress = stress_by_date.get(current, 0.0) if locked_in else 0.0
        p_stress = pattern_stress_by_date.get(current, {p: 0.0 for p in _PATTERNS}) if locked_in else {p: 0.0 for p in _PATTERNS}

        atl = stress * k_atl + atl * (1 - k_atl)
        ctl = stress * k_ctl + ctl * (1 - k_ctl)
        tsb = ctl - atl

        for p in _PATTERNS:
            ps = p_stress.get(p, 0.0)
            p_atl[p] = ps * k_atl + p_atl[p] * (1 - k_atl)
            p_ctl[p] = ps * k_ctl + p_ctl[p] * (1 - k_ctl)

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
                "pattern_loads": {
                    p: {
                        "atl": round(p_atl[p], 3),
                        "ctl": round(p_ctl[p], 3),
                        "tsb": round(p_ctl[p] - p_atl[p], 3),
                    }
                    for p in _PATTERNS
                },
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
    # Subjective base weighting (global score):
    # joints are collected but not included in fatigue score weighting.
    return round(0.45 * t + 0.30 * r + 0.25 * s, 3)

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


_PATTERN_KEYS = ("knee", "hip", "push", "pull")
_PATTERN_LABELS = {
    "knee": "Knee",
    "hip": "Hip",
    "push": "Push",
    "pull": "Pull",
}


def _resolve_v2_thresholds(calibration: dict | None = None) -> dict:
    cfg = calibration or {}
    stressed = float(cfg.get("v2_threshold_stressed", _CALIBRATION_DEFAULTS["v2_threshold_stressed"]))
    neutral = float(cfg.get("v2_threshold_neutral", _CALIBRATION_DEFAULTS["v2_threshold_neutral"]))

    stressed = _clamp(stressed, 0.0, 1.0)
    neutral = _clamp(neutral, 0.0, 1.0)
    if stressed < neutral:
        stressed, neutral = neutral, stressed

    return {
        "stressed": round(stressed, 3),
        "neutral": round(neutral, 3),
    }


TSB_STATES = [
    ("underloaded", 8.0, "Underloaded", "Fitness is significantly outpacing recent training stress"),
    ("slightly_fresh", 3.0, "Slightly Fresh", "Fitness outpacing fatigue - recovery is ahead of training"),
    ("balanced", -5.0, "Balanced", "Fitness and fatigue well matched - normal training state"),
    ("slightly_fatigued", -10.0, "Slightly Fatigued", "Fatigue outpacing fitness - accumulated stress present"),
    ("fatigued", None, "Fatigued", "Fatigue significantly elevated - recovery is the priority"),
]


FATIGUE_TIERS = [
    (8.0, "High", "Fatigue score elevated"),
    (6.5, "Moderate-High", "Meaningful fatigue present"),
    (4.5, "Moderate", "Some fatigue present"),
    (3.0, "Low-Moderate", "Fatigue manageable"),
    (0.0, "Low", "Feeling recovered"),
]


def _resolve_tsb_state_thresholds(calibration: dict | None = None) -> dict:
    cfg = calibration or {}
    return {
        "underloaded": float(cfg.get("tsb_threshold_underloaded", _CALIBRATION_DEFAULTS["tsb_threshold_underloaded"])),
        "slightly_fresh": float(cfg.get("tsb_threshold_slightly_fresh", _CALIBRATION_DEFAULTS["tsb_threshold_slightly_fresh"])),
        "balanced": float(cfg.get("tsb_threshold_balanced", _CALIBRATION_DEFAULTS["tsb_threshold_balanced"])),
        "slightly_fatigued": float(cfg.get("tsb_threshold_slightly_fatigued", _CALIBRATION_DEFAULTS["tsb_threshold_slightly_fatigued"])),
        "fatigued": None,
    }


def _resolve_training_state(tsb: float, tsb_thresholds: dict) -> tuple[str, str, str]:
    ordered = [
        ("underloaded", tsb_thresholds.get("underloaded"), "Underloaded", "Fitness is significantly outpacing recent training stress"),
        ("slightly_fresh", tsb_thresholds.get("slightly_fresh"), "Slightly Fresh", "Fitness outpacing fatigue - recovery is ahead of training"),
        ("balanced", tsb_thresholds.get("balanced"), "Balanced", "Fitness and fatigue well matched - normal training state"),
        ("slightly_fatigued", tsb_thresholds.get("slightly_fatigued"), "Slightly Fatigued", "Fatigue outpacing fitness - accumulated stress present"),
        ("fatigued", None, "Fatigued", "Fatigue significantly elevated - recovery is the priority"),
    ]

    for key, threshold, label, detail in ordered:
        if threshold is None or tsb >= float(threshold):
            return key, label, detail
    return "fatigued", "Fatigued", "Fatigue significantly elevated - recovery is the priority"


def _resolve_fatigue_tier(fatigue_score: float) -> tuple[str, str]:
    for threshold, label, detail in FATIGUE_TIERS:
        if fatigue_score >= threshold:
            return label, detail
    return "Low", "Feeling recovered"


def _dots_filled(combined_signal: float) -> int:
    if combined_signal >= 0.90:
        return 5
    if combined_signal >= 0.75:
        return 4
    if combined_signal >= 0.55:
        return 3
    if combined_signal >= 0.35:
        return 2
    return 1


def _stress_level_label(status: str) -> str:
    if status == "stressed":
        return "High"
    if status == "neutral":
        return "Moderate"
    return "Fresh"


def _pattern_last_loaded_dates(db: Session, today: date_type) -> dict:
    dates = (
        db.query(WorkoutLog.date)
        .filter(WorkoutLog.date <= today)
        .distinct()
        .order_by(WorkoutLog.date)
        .all()
    )

    last = {p: None for p in _PATTERN_KEYS}
    for row in dates:
        scores = calculate_stress_scores(row.date, db)
        for p in _PATTERN_KEYS:
            if float(scores.get(p, 0.0) or 0.0) > 0.0:
                last[p] = row.date
    return last


def _days_since_loaded(pattern: str, last_loaded_dates: dict, today: date_type) -> int | None:
    last = last_loaded_dates.get(pattern)
    if last is None:
        return None
    return max(0, int((today - last).days))


def _pattern_soreness_signals(checkin: DailyReadiness | None) -> dict:
    if not checkin:
        # Missing check-in defaults to neutral soreness (2/4 -> 0.5), not fresh.
        return {p: 0.5 for p in _PATTERN_KEYS}
    return {
        "knee": round((checkin.sore_quad_dom or 0) / 4.0, 3),
        "hip": round((checkin.sore_posterior or 0) / 4.0, 3),
        "push": round((checkin.sore_upper_push or 0) / 4.0, 3),
        "pull": round((checkin.sore_upper_pull or 0) / 4.0, 3),
    }


def _pattern_load_signal(atl: float, ctl: float) -> float:
    """
    Convert pattern ATL/CTL into a 0..1 stress signal.

    Edge handling when CTL is zero:
    - atl <= 0 => signal 0
    - atl > 0  => signal scales quickly toward 1 (new/unaccustomed load)
    """
    atl = max(0.0, float(atl or 0.0))
    ctl = max(0.0, float(ctl or 0.0))

    if ctl <= 0.0:
        return round(_clamp(atl / 4.0, 0.0, 1.0), 3)

    ratio = atl / ctl
    signal = (ratio - 0.85) / 0.75
    return round(_clamp(signal, 0.0, 1.0), 3)


def _state_from_signal(signal: float, thresholds: dict) -> str:
    if signal > thresholds["stressed"]:
        return "stressed"
    if signal >= thresholds["neutral"]:
        return "neutral"
    return "available"


def _resolve_joint_advisory(joint_upper: int, joint_lower: int) -> dict:
    def level(score: int) -> str:
        if score >= 4:
            return "warning"
        if score >= 3:
            return "advisory"
        return "none"

    def label(score: int, region: str) -> str | None:
        if score >= 4:
            return f"{region} joint health poor - consider avoiding loading today"
        if score >= 3:
            return f"{region} joint health suboptimal - be conservative with loading"
        return None

    return {
        "upper": {
            "score": int(joint_upper),
            "level": level(int(joint_upper)),
            "label": label(int(joint_upper), "Upper"),
            "affected_patterns": ["push", "pull"] if int(joint_upper) >= 3 else [],
        },
        "lower": {
            "score": int(joint_lower),
            "level": level(int(joint_lower)),
            "label": label(int(joint_lower), "Lower"),
            "affected_patterns": ["knee", "hip"] if int(joint_lower) >= 3 else [],
        },
    }


def _build_recommendation_v2(today_pattern_loads: dict, checkin: DailyReadiness | None, calibration: dict | None = None, db: Session | None = None, today_date: date_type | None = None, today_tsb: float = 0.0, fatigue_score: float = 0.0) -> dict:
    """
    Stage 6 recommendation engine using pattern ATL/CTL/TSB and same-day soreness.
    Produces a pattern-aware recommendation without implying hidden physiology.
    """
    thresholds = _resolve_v2_thresholds(calibration)
    tsb_thresholds = _resolve_tsb_state_thresholds(calibration)
    soreness = _pattern_soreness_signals(checkin)
    joint_upper = int((checkin.joint_upper if checkin else 0) or 0)
    joint_lower = int((checkin.joint_lower if checkin else 0) or 0)
    joint_advisory = _resolve_joint_advisory(joint_upper, joint_lower)

    pattern_rows = {}
    for p in _PATTERN_KEYS:
        pl = (today_pattern_loads or {}).get(p, {})
        atl = float(pl.get("atl", 0.0) or 0.0)
        ctl = float(pl.get("ctl", 0.0) or 0.0)
        tsb = float(pl.get("tsb", ctl - atl) or 0.0)

        load_signal = _pattern_load_signal(atl, ctl)
        soreness_signal = float(soreness[p])
        combined_signal = round(_clamp((0.70 * load_signal) + (0.30 * soreness_signal), 0.0, 1.0), 3)
        state = _state_from_signal(combined_signal, thresholds)

        pattern_rows[p] = {
            "atl": round(atl, 3),
            "ctl": round(ctl, 3),
            "tsb": round(tsb, 3),
            "load_signal": round(load_signal, 3),
            "soreness_signal": round(soreness_signal, 3),
            "combined_signal": combined_signal,
            "state": state,
        }

    training_state, training_state_label, training_state_detail = _resolve_training_state(float(today_tsb), tsb_thresholds)
    fatigue_tier, fatigue_tier_detail = _resolve_fatigue_tier(float(fatigue_score))

    ref_today = today_date or date_type.today()
    if db is not None:
        last_loaded_dates = _pattern_last_loaded_dates(db, ref_today)
    else:
        last_loaded_dates = {p: None for p in _PATTERN_KEYS}

    pattern_status = {}
    for p in _PATTERN_KEYS:
        state = pattern_rows[p]["state"]
        pattern_status[p] = {
            "status": state,
            "stress_level_label": _stress_level_label(state),
            "combined_signal": pattern_rows[p]["combined_signal"],
            "days_since_loaded": _days_since_loaded(p, last_loaded_dates, ref_today),
            "dots_filled": _dots_filled(pattern_rows[p]["combined_signal"]),
            "dots_total": 5,
        }

    return {
        "training_state": training_state,
        "training_state_label": training_state_label,
        "training_state_detail": training_state_detail,
        "tsb": round(float(today_tsb), 3),
        "fatigue_score": round(float(fatigue_score), 2),
        "fatigue_tier": fatigue_tier,
        "fatigue_tier_detail": fatigue_tier_detail,
        "pattern_status": pattern_status,
        "joint_advisory": joint_advisory,
        "tsb_thresholds": tsb_thresholds,
        "signal_thresholds": thresholds,
    }


@app.get("/api/training-load")
def get_training_load(days: int = 60, db: Session = Depends(get_db)):
    """
    Return ATL/CTL/TSB history for the chart and today's summary values.
    """
    history, atl_max, ctl_max = _compute_training_load(days, db)
    today = history[-1] if history else {"date": str(date_type.today()), "atl": 0, "ctl": 0, "tsb": 0, "stress": 0}
    stress_included_through = _training_stress_included_through(db)
    latest_workout_date = db.query(func.max(WorkoutLog.date)).scalar()
    has_pending_workout_stress = bool(latest_workout_date and latest_workout_date > stress_included_through)

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
    recommendation_v2 = _build_recommendation_v2(
        today.get("pattern_loads", {}),
        checkin,
        calibration,
        db,
        date_type.today(),
        today.get("tsb", 0.0),
        fatigue_score,
    )

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
            "recommendation_v2":       recommendation_v2,
            "subj_fatigue":            subj,
            "calibration_enabled":      calibration.get("enabled", False),
            "recommendation_mode":      thresholds.get("mode", "default"),
            "stress_included_through": str(stress_included_through),
            "has_pending_workout_stress": has_pending_workout_stress,
            "pattern_loads":           today.get("pattern_loads", {}),
        },
        "thresholds": {
            "threshold_large_decrease": thresholds.get("threshold_large_decrease", _CALIBRATION_DEFAULTS["threshold_large_decrease"]),
            "threshold_decrease": thresholds.get("threshold_decrease", _CALIBRATION_DEFAULTS["threshold_decrease"]),
            "threshold_continue": thresholds.get("threshold_continue", _CALIBRATION_DEFAULTS["threshold_continue"]),
            "threshold_increase": thresholds.get("threshold_increase", _CALIBRATION_DEFAULTS["threshold_increase"]),
            "v2_threshold_stressed": calibration.get("v2_threshold_stressed", _CALIBRATION_DEFAULTS["v2_threshold_stressed"]),
            "v2_threshold_neutral": calibration.get("v2_threshold_neutral", _CALIBRATION_DEFAULTS["v2_threshold_neutral"]),
            "tsb_threshold_underloaded": calibration.get("tsb_threshold_underloaded", _CALIBRATION_DEFAULTS["tsb_threshold_underloaded"]),
            "tsb_threshold_slightly_fresh": calibration.get("tsb_threshold_slightly_fresh", _CALIBRATION_DEFAULTS["tsb_threshold_slightly_fresh"]),
            "tsb_threshold_balanced": calibration.get("tsb_threshold_balanced", _CALIBRATION_DEFAULTS["tsb_threshold_balanced"]),
            "tsb_threshold_slightly_fatigued": calibration.get("tsb_threshold_slightly_fatigued", _CALIBRATION_DEFAULTS["tsb_threshold_slightly_fatigued"]),
            "tsb_threshold_fatigued": None,
            "mode": thresholds.get("mode", "default"),
            "sample_size": thresholds.get("sample_size"),
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


@app.get("/api/workout-sessions")
def get_workout_sessions(
    days: int = 30,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List workout sessions for review and verification workflows."""
    since = date_type.today() - timedelta(days=max(1, days) - 1)
    q = db.query(WorkoutSession).filter(WorkoutSession.workout_date >= since)

    if status:
        status_normalized = status.strip().lower()
        if status_normalized not in {"pending", "verified"}:
            raise HTTPException(status_code=422, detail="status must be 'pending' or 'verified'")
        q = q.filter(WorkoutSession.verification_status == status_normalized)

    rows = (
        q.order_by(WorkoutSession.workout_date.desc(), WorkoutSession.start_time.desc())
        .all()
    )

    return [
        {
            "hevy_workout_id": row.hevy_workout_id,
            "workout_date": str(row.workout_date),
            "workout_title": row.workout_title,
            "start_time": row.start_time,
            "end_time": row.end_time,
            "duration_minutes": row.duration_minutes,
            "modality": row.modality,
            "modality_confidence": row.modality_confidence,
            "verification_status": row.verification_status,
            "verified_at": row.verified_at,
            "srpe": row.srpe,
            "needs_manual_duration": row.duration_minutes is None,
        }
        for row in rows
    ]


@app.get("/api/workout-sessions/pending")
def get_pending_workout_sessions(days: int = 30, db: Session = Depends(get_db)):
    """Convenience endpoint for pending verification queue."""
    return get_workout_sessions(days=days, status="pending", db=db)


@app.get("/api/workout-sessions/{hevy_workout_id}")
def get_workout_session_detail(hevy_workout_id: str, db: Session = Depends(get_db)):
    """Return one session plus on-demand detail for the Workouts session log."""
    session_row = db.query(WorkoutSession).filter(
        WorkoutSession.hevy_workout_id == hevy_workout_id
    ).first()
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Workout session {hevy_workout_id} not found")

    workout_sets = (
        db.query(WorkoutLog)
        .filter(WorkoutLog.workout_id == hevy_workout_id)
        .order_by(WorkoutLog.exercise_title.asc(), WorkoutLog.set_number.asc())
        .all()
    )

    total_volume = 0.0
    rpe_values = []
    exercise_rollup = {}
    set_rows = []
    for s in workout_sets:
        weight = float(s.weight_lbs or 0)
        reps = int(s.reps or 0)
        set_volume = weight * reps
        total_volume += set_volume
        if s.rpe is not None:
            rpe_values.append(float(s.rpe))

        title = s.exercise_title or "Unknown exercise"
        agg = exercise_rollup.setdefault(title, {
            "exercise_title": title,
            "set_count": 0,
            "total_reps": 0,
            "total_volume": 0.0,
            "top_weight": 0.0,
            "rpe_values": [],
        })
        agg["set_count"] += 1
        agg["total_reps"] += reps
        agg["total_volume"] += set_volume
        agg["top_weight"] = max(float(agg["top_weight"]), weight)
        if s.rpe is not None:
            agg["rpe_values"].append(float(s.rpe))

        set_rows.append({
            "exercise_title": title,
            "set_number": s.set_number,
            "weight_lbs": s.weight_lbs,
            "reps": s.reps,
            "rpe": s.rpe,
            "rir": s.rir,
            "notes": s.notes,
        })

    exercises = []
    for title in sorted(exercise_rollup.keys()):
        agg = exercise_rollup[title]
        avg_rpe = None
        if agg["rpe_values"]:
            avg_rpe = round(sum(agg["rpe_values"]) / len(agg["rpe_values"]), 1)
        exercises.append({
            "exercise_title": agg["exercise_title"],
            "set_count": agg["set_count"],
            "total_reps": agg["total_reps"],
            "total_volume": round(float(agg["total_volume"]), 0),
            "top_weight": round(float(agg["top_weight"]), 1),
            "avg_rpe": avg_rpe,
        })

    detail_type = "pending" if session_row.verification_status == "pending" else session_row.modality

    response = {
        "detail_type": detail_type,
        "session": {
            "hevy_workout_id": session_row.hevy_workout_id,
            "workout_date": str(session_row.workout_date),
            "workout_title": session_row.workout_title,
            "start_time": session_row.start_time,
            "end_time": session_row.end_time,
            "duration_minutes": session_row.duration_minutes,
            "modality": session_row.modality,
            "modality_confidence": session_row.modality_confidence,
            "verification_status": session_row.verification_status,
            "verified_at": session_row.verified_at,
            "srpe": session_row.srpe,
            "needs_manual_duration": session_row.duration_minutes is None,
        },
        "summary": {
            "set_count": len(workout_sets),
            "exercise_count": len(exercises),
            "volume": round(float(total_volume), 0),
            "avg_rpe": round(sum(rpe_values) / len(rpe_values), 1) if rpe_values else None,
        },
        "exercises": exercises,
    }

    if detail_type in {"strength", "hypertrophy"}:
        central = sum(
            get_set_central_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
            for s in workout_sets
        )
        peripheral = sum(
            get_set_peripheral_stress(s.weight_lbs, s.reps, s.rpe, s.rir, s.exercise_title, db)
            for s in workout_sets
        )
        response["stress"] = {
            "central": round(central, 3),
            "peripheral": round(peripheral, 3),
        }
        response["sets"] = set_rows

    elif detail_type == "conditioning":
        stress = None
        scaling_factor = _get_conditioning_scaling_factor(db)
        if session_row.srpe is not None and session_row.duration_minutes is not None:
            raw = (session_row.srpe * session_row.duration_minutes) / scaling_factor
            avg_quad = avg_post = avg_push = avg_pull = 0.25
            session_titles = {s.exercise_title for s in workout_sets if s.exercise_title}
            if session_titles:
                maps = (
                    db.query(ExerciseMapping)
                    .filter(ExerciseMapping.exercise_title.in_(session_titles))
                    .all()
                )
                if maps:
                    n = len(maps)
                    avg_quad = sum(m.pct_quad_dom for m in maps) / n
                    avg_post = sum(m.pct_posterior for m in maps) / n
                    avg_push = sum(m.pct_upper_push for m in maps) / n
                    avg_pull = sum(m.pct_upper_pull for m in maps) / n
            pct_c_weight = avg_quad**2 + avg_post**2 + avg_push**2 + avg_pull**2
            pct_p_weight = avg_quad + avg_post + avg_push + avg_pull
            stress = {
                "raw": round(raw, 3),
                "central": round(raw * pct_c_weight, 3),
                "peripheral": round(raw * pct_p_weight, 3),
                "pattern_distribution": {
                    "knee": round(avg_quad, 3),
                    "hip": round(avg_post, 3),
                    "push": round(avg_push, 3),
                    "pull": round(avg_pull, 3),
                },
                "scaling_factor": scaling_factor,
            }
        response["stress"] = stress

    elif detail_type == "cardio":
        stress = None
        scaling_factor = _get_conditioning_scaling_factor(db)
        if session_row.srpe is not None and session_row.duration_minutes is not None:
            raw = (session_row.srpe * session_row.duration_minutes) / scaling_factor
            stress = {
                "raw": round(raw, 3),
                "central": round(raw * 0.30, 3),
                "peripheral": round(raw * 0.70, 3),
                "scaling_factor": scaling_factor,
            }
        response["stress"] = stress

    else:
        response["pending_requirements"] = {
            "needs_manual_duration": session_row.duration_minutes is None,
            "needs_srpe": session_row.modality in {"conditioning", "cardio"},
            "modality": session_row.modality,
        }
        response["sets"] = set_rows

    return response


@app.put("/api/workout-sessions/{hevy_workout_id}/verify")
def verify_workout_session(
    hevy_workout_id: str,
    data: SessionVerificationUpdate,
    db: Session = Depends(get_db),
):
    """Manual verification endpoint with modality pre-selected from importer inference."""
    session_row = db.query(WorkoutSession).filter(
        WorkoutSession.hevy_workout_id == hevy_workout_id
    ).first()
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Workout session {hevy_workout_id} not found")

    modality = _normalize_modality(data.modality)
    duration_minutes = data.duration_minutes if data.duration_minutes is not None else session_row.duration_minutes
    srpe = data.srpe if data.srpe is not None else session_row.srpe

    _assert_session_can_be_verified(modality=modality, duration_minutes=duration_minutes, srpe=srpe)

    session_row.modality = modality
    session_row.duration_minutes = duration_minutes
    session_row.srpe = srpe
    session_row.verification_status = "verified"
    session_row.verified_at = datetime.utcnow()
    db.commit()
    db.refresh(session_row)

    return {
        "hevy_workout_id": session_row.hevy_workout_id,
        "verification_status": session_row.verification_status,
        "modality": session_row.modality,
        "modality_confidence": session_row.modality_confidence,
        "duration_minutes": session_row.duration_minutes,
        "srpe": session_row.srpe,
        "verified_at": session_row.verified_at,
    }


@app.put("/api/workout-sessions/{hevy_workout_id}/status")
def update_workout_session_status(
    hevy_workout_id: str,
    data: SessionStatusUpdate,
    db: Session = Depends(get_db),
):
    """Set session status to pending/verified while applying Stage 2 verification rules."""
    session_row = db.query(WorkoutSession).filter(
        WorkoutSession.hevy_workout_id == hevy_workout_id
    ).first()
    if not session_row:
        raise HTTPException(status_code=404, detail=f"Workout session {hevy_workout_id} not found")

    modality = _normalize_modality(data.modality) if data.modality else session_row.modality
    duration_minutes = data.duration_minutes if data.duration_minutes is not None else session_row.duration_minutes
    srpe = data.srpe if data.srpe is not None else session_row.srpe

    session_row.modality = modality
    session_row.duration_minutes = duration_minutes
    session_row.srpe = srpe

    if data.verification_status == "verified":
        _assert_session_can_be_verified(modality=modality, duration_minutes=duration_minutes, srpe=srpe)
        session_row.verification_status = "verified"
        session_row.verified_at = datetime.utcnow()
    else:
        session_row.verification_status = "pending"
        session_row.verified_at = None

    db.commit()
    db.refresh(session_row)

    return {
        "hevy_workout_id": session_row.hevy_workout_id,
        "verification_status": session_row.verification_status,
        "modality": session_row.modality,
        "modality_confidence": session_row.modality_confidence,
        "duration_minutes": session_row.duration_minutes,
        "srpe": session_row.srpe,
        "verified_at": session_row.verified_at,
    }


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
