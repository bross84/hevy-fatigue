from __future__ import annotations
from datetime import date as date_type
from datetime import datetime as dt_datetime
from typing import Optional
from sqlalchemy import create_engine, Integer, Float, String, Date, DateTime, Boolean, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column

# Path to the database file.
# In Docker this is overridden via DB_PATH env var pointing to the named volume.
# Locally it defaults to ./hevy_fatigue.db in the project directory.
import os as _os
_db_path = _os.environ.get("DB_PATH", "./hevy_fatigue.db")
DB_URL = f"sqlite:///{_db_path}"

# Setup the Engine and Session
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
class Base(DeclarativeBase):
    pass

# --- TABLE 1: Daily Readiness Check-in ---
class DailyReadiness(Base):
    __tablename__ = "daily_readiness"
    date: Mapped[date_type] = mapped_column(Date, primary_key=True, default=date_type.today)
    # Soreness (0=none, 4=high soreness/injury)
    sore_quad_dom: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)       # Squat patterns, quads
    sore_posterior: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # Deadlift patterns, hamstrings, glutes, erectors
    sore_upper_push: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)     # Bench variations, triceps
    sore_upper_pull: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)     # Rows, pulldowns, rear delts
    # Joint Health (0=no pain, 4=high pain/injury)
    joint_upper: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)         # Shoulders, elbows, wrists
    joint_lower: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)         # Low back, hips, knees
    # Readiness (0=fresh, 4=exhausted/beat up)
    tiredness: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    perceived_recovery: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Stress scores — system calculated from previous day's Hevy data
    central_stress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peripheral_stress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self):
        return f"<DailyReadiness date={self.date}>"

# --- TABLE 2: Workout Data (Imported from Hevy) ---
class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    
    __table_args__=(
        UniqueConstraint('workout_id', 'exercise_id', 'set_number', name='uq_workout_set'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    workout_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exercise_title: Mapped[str] = mapped_column(String, nullable=False)
    set_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    workout_id: Mapped[str] = mapped_column(String, nullable=False)
    exercise_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weight_lbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # Rate of Perceived Exertion (0–10), logged in Hevy
    rir: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # Reps in Reserve — alternative to RPE; converted via RPE = 10 - RIR
    estimated_1rm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_conditioning: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self):
        return f"<WorkoutLog date={self.date} exercise={self.exercise_title} set={self.set_number}>"

# --- TABLE 3: RPE Chart (intensity % lookup by RPE and reps) ---
class RPEChart(Base):
    __tablename__ = "rpe_chart"

    __table_args__ = (
        UniqueConstraint('movement_pattern', 'rpe', 'reps', name='uq_rpe_entry'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    movement_pattern: Mapped[str] = mapped_column(String, nullable=False, default='general')  # general, quad_dom, posterior, upper_push, upper_pull
    rpe: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)  # stored as decimal e.g. 0.93 = 93%

    def __repr__(self):
        return f"<RPEChart pattern={self.movement_pattern} rpe={self.rpe} reps={self.reps} pct={self.percentage}>"

# --- TABLE 4: App Settings (key/value store) ---
class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def __repr__(self):
        return f"<AppSetting key={self.key}>"

# --- TABLE 5: Exercise Movement Pattern Mapping ---
class ExerciseMapping(Base):
    __tablename__ = "exercise_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exercise_title: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Movement pattern percentages — must sum to 1.0
    # Default auto-classifications are 100% one pattern
    # Users can set custom splits (e.g. box squat = 35% quad, 65% posterior)
    pct_quad_dom: Mapped[float] = mapped_column(Float, default=0.0)
    pct_posterior: Mapped[float] = mapped_column(Float, default=0.0)
    pct_upper_push: Mapped[float] = mapped_column(Float, default=0.0)
    pct_upper_pull: Mapped[float] = mapped_column(Float, default=0.0)
    # Classification metadata
    source: Mapped[str] = mapped_column(String, default='auto')        # 'auto' or 'user'
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)   # has user confirmed this?
    is_conditioning: Mapped[bool] = mapped_column(Boolean, default=False)  # METCON/conditioning — excluded from pattern stress

    def __repr__(self):
        return f"<ExerciseMapping {self.exercise_title} source={self.source} reviewed={self.is_reviewed}>"

# --- TABLE 6: Workout Sessions (Imported from Hevy) ---
class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hevy_workout_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    workout_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    workout_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_time: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    modality: Mapped[str] = mapped_column(String, nullable=False, default="strength")  # strength|hypertrophy|conditioning|cardio
    modality_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    modality_note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verification_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending|verified
    verified_at: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, nullable=True)
    srpe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt_datetime] = mapped_column(DateTime, nullable=False, default=dt_datetime.utcnow)
    updated_at: Mapped[dt_datetime] = mapped_column(DateTime, nullable=False, default=dt_datetime.utcnow, onupdate=dt_datetime.utcnow)

    def __repr__(self):
        return (
            f"<WorkoutSession workout_id={self.hevy_workout_id} "
            f"modality={self.modality} status={self.verification_status}>"
        )


# --- TABLE 7: Canonical Exercise Titles ---
class ExerciseCanonical(Base):
    __tablename__ = "exercise_canonical"

    exercise_id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, default=dt_datetime.utcnow)
    updated_at: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, default=dt_datetime.utcnow, onupdate=dt_datetime.utcnow)

    def __repr__(self):
        return f"<ExerciseCanonical exercise_id={self.exercise_id} canonical_title={self.canonical_title}>"


class ExerciseConflict(Base):
    __tablename__ = "exercise_conflicts"

    exercise_id: Mapped[str] = mapped_column(String, primary_key=True)
    hevy_title: Mapped[str] = mapped_column(String, nullable=False)
    stored_title: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, default=dt_datetime.utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[dt_datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ExerciseConflict exercise_id={self.exercise_id} resolved={self.resolved}>"


# This part actually creates the file and tables when you run the script
def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        exercise_canonical_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='exercise_canonical'")
        ).first()
        if not exercise_canonical_exists:
            Base.metadata.tables["exercise_canonical"].create(bind=conn)
            conn.commit()

        cols = conn.execute(text("PRAGMA table_info(workout_sessions)")).fetchall()
        col_names = {row[1] for row in cols}
        if "modality_note" not in col_names:
            conn.execute(text("ALTER TABLE workout_sessions ADD COLUMN modality_note VARCHAR"))
            conn.commit()

        # Ensure workout_logs has a hard unique index on natural set identity.
        # Existing deployments may contain duplicates from earlier versions, so
        # dedup first to guarantee index creation succeeds.
        conn.execute(
            text(
                """
                DELETE FROM workout_logs
                WHERE id IN (
                    SELECT wl.id
                    FROM workout_logs wl
                    JOIN (
                        SELECT workout_id, exercise_id, set_number, MIN(id) AS keep_id
                        FROM workout_logs
                        GROUP BY workout_id, exercise_id, set_number
                        HAVING COUNT(*) > 1
                    ) d
                      ON wl.workout_id = d.workout_id
                     AND wl.exercise_id = d.exercise_id
                     AND wl.set_number = d.set_number
                    WHERE wl.id <> d.keep_id
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_workout_logs_set
                ON workout_logs (workout_id, exercise_id, set_number)
                """
            )
        )
        conn.commit()

        exercise_conflicts_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='exercise_conflicts'")
        ).first()
        if not exercise_conflicts_exists:
            Base.metadata.tables["exercise_conflicts"].create(bind=conn)
            conn.commit()

        migration_flag_key = "migration_incremental_sync_v1"
        migration_flag_exists = conn.execute(
            text("SELECT key FROM app_settings WHERE key = :key"),
            {"key": migration_flag_key},
        ).first()
        if not migration_flag_exists:
            conn.execute(
                text("DELETE FROM app_settings WHERE key = :key"),
                {"key": "last_sync"},
            )
            conn.execute(
                text("INSERT INTO app_settings (key, value) VALUES (:key, :value)"),
                {"key": migration_flag_key, "value": "1"},
            )
            conn.commit()

        canonical_backfill_flag_key = "migration_canonical_title_backfill_v1"
        canonical_backfill_flag_exists = conn.execute(
            text("SELECT key FROM app_settings WHERE key = :key"),
            {"key": canonical_backfill_flag_key},
        ).first()
        if not canonical_backfill_flag_exists:
            conn.execute(
                text(
                    """
                    UPDATE workout_logs
                    SET exercise_title = (
                        SELECT ec.canonical_title
                        FROM exercise_canonical ec
                        WHERE ec.exercise_id = workout_logs.exercise_id
                    )
                    WHERE exercise_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1
                          FROM exercise_canonical ec2
                          WHERE ec2.exercise_id = workout_logs.exercise_id
                      )
                    """
                )
            )
            conn.execute(
                text("INSERT INTO app_settings (key, value) VALUES (:key, :value)"),
                {"key": canonical_backfill_flag_key, "value": "1"},
            )
            conn.commit()

        canonical_mapping_sync_flag_key = "migration_canonical_mapping_sync_v1"
        canonical_mapping_sync_flag_exists = conn.execute(
            text("SELECT key FROM app_settings WHERE key = :key"),
            {"key": canonical_mapping_sync_flag_key},
        ).first()
        if not canonical_mapping_sync_flag_exists:
            conn.execute(
                text(
                    """
                    INSERT INTO exercise_mappings (
                        exercise_title,
                        pct_quad_dom,
                        pct_posterior,
                        pct_upper_push,
                        pct_upper_pull,
                        source,
                        is_reviewed,
                        is_conditioning
                    )
                    SELECT
                        ec.canonical_title,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        'auto',
                        0,
                        0
                    FROM exercise_canonical ec
                    WHERE ec.canonical_title IS NOT NULL
                      AND TRIM(ec.canonical_title) <> ''
                      AND NOT EXISTS (
                          SELECT 1
                          FROM exercise_mappings em
                          WHERE LOWER(em.exercise_title) = LOWER(ec.canonical_title)
                      )
                    """
                )
            )
            conn.execute(
                text("INSERT INTO app_settings (key, value) VALUES (:key, :value)"),
                {"key": canonical_mapping_sync_flag_key, "value": "1"},
            )
            conn.commit()

    # app_settings table is created by create_all above (new installs and existing DBs)
if __name__ == "__main__":
    init_db()
    print("✅ Database and tables initialized successfully.")
