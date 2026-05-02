from datetime import date as date_type
from datetime import datetime as dt_datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, Date, DateTime, Boolean, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
    date = Column(Date, primary_key=True, default=date_type.today)
    # Soreness (0=none, 4=high soreness/injury)
    sore_quad_dom = Column(Integer)       # Squat patterns, quads
    sore_posterior = Column(Integer)      # Deadlift patterns, hamstrings, glutes, erectors
    sore_upper_push = Column(Integer)     # Bench variations, triceps
    sore_upper_pull = Column(Integer)     # Rows, pulldowns, rear delts
    # Joint Health (0=no pain, 4=high pain/injury)
    joint_upper = Column(Integer)         # Shoulders, elbows, wrists
    joint_lower = Column(Integer)         # Low back, hips, knees
    # Readiness (0=fresh, 4=exhausted/beat up)
    tiredness = Column(Integer)
    perceived_recovery = Column(Integer)
    # Stress scores — system calculated from previous day's Hevy data
    central_stress = Column(Float, nullable=True)
    peripheral_stress = Column(Float, nullable=True)

    def __repr__(self):
        return f"<DailyReadiness date={self.date}>"

# --- TABLE 2: Workout Data (Imported from Hevy) ---
class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    
    __table_args__=(
        UniqueConstraint('workout_id', 'exercise_id', 'set_number', name='uq_workout_set'),
    )
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    workout_title = Column(String, nullable=True)
    exercise_title = Column(String, nullable=False)
    set_number = Column(Integer)
    workout_id = Column(String, nullable=False)
    exercise_id = Column(String)
    notes = Column(String, nullable=True)
    weight_lbs = Column(Float)
    reps = Column(Integer)
    rpe = Column(Float)           # Rate of Perceived Exertion (0–10), logged in Hevy
    rir = Column(Float)           # Reps in Reserve — alternative to RPE; converted via RPE = 10 - RIR
    estimated_1rm = Column(Float)
    is_conditioning = Column(Boolean, default=False)

    def __repr__(self):
        return f"<WorkoutLog date={self.date} exercise={self.exercise_title} set={self.set_number}>"

# --- TABLE 3: RPE Chart (intensity % lookup by RPE and reps) ---
class RPEChart(Base):
    __tablename__ = "rpe_chart"

    __table_args__ = (
        UniqueConstraint('movement_pattern', 'rpe', 'reps', name='uq_rpe_entry'),
    )
    id = Column(Integer, primary_key=True, index=True)
    movement_pattern = Column(String, nullable=False, default='general')  # general, quad_dom, posterior, upper_push, upper_pull
    rpe = Column(Float, nullable=False)
    reps = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)  # stored as decimal e.g. 0.93 = 93%

    def __repr__(self):
        return f"<RPEChart pattern={self.movement_pattern} rpe={self.rpe} reps={self.reps} pct={self.percentage}>"

# --- TABLE 4: App Settings (key/value store) ---
class AppSetting(Base):
    __tablename__ = "app_settings"
    key   = Column(String, primary_key=True)
    value = Column(String, nullable=True)

    def __repr__(self):
        return f"<AppSetting key={self.key}>"

# --- TABLE 5: Exercise Movement Pattern Mapping ---
class ExerciseMapping(Base):
    __tablename__ = "exercise_mappings"

    id = Column(Integer, primary_key=True, index=True)
    exercise_title = Column(String, nullable=False, unique=True)
    # Movement pattern percentages — must sum to 1.0
    # Default auto-classifications are 100% one pattern
    # Users can set custom splits (e.g. box squat = 35% quad, 65% posterior)
    pct_quad_dom = Column(Float, default=0.0)
    pct_posterior = Column(Float, default=0.0)
    pct_upper_push = Column(Float, default=0.0)
    pct_upper_pull = Column(Float, default=0.0)
    # Classification metadata
    source = Column(String, default='auto')        # 'auto' or 'user'
    is_reviewed = Column(Boolean, default=False)   # has user confirmed this?
    is_conditioning = Column(Boolean, default=False)  # METCON/conditioning — excluded from pattern stress

    def __repr__(self):
        return f"<ExerciseMapping {self.exercise_title} source={self.source} reviewed={self.is_reviewed}>"

# --- TABLE 6: Workout Sessions (Imported from Hevy) ---
class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True, index=True)
    hevy_workout_id = Column(String, nullable=False, unique=True, index=True)
    workout_date = Column(Date, nullable=False)
    workout_title = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    modality = Column(String, nullable=False, default="strength")  # strength|hypertrophy|conditioning|cardio
    modality_confidence = Column(Float, nullable=False, default=0.0)
    modality_note = Column(String, nullable=True)
    verification_status = Column(String, nullable=False, default="pending")  # pending|verified
    verified_at = Column(DateTime, nullable=True)
    srpe = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=dt_datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=dt_datetime.utcnow, onupdate=dt_datetime.utcnow)

    def __repr__(self):
        return (
            f"<WorkoutSession workout_id={self.hevy_workout_id} "
            f"modality={self.modality} status={self.verification_status}>"
        )


# --- TABLE 7: Canonical Exercise Titles ---
class ExerciseCanonical(Base):
    __tablename__ = "exercise_canonical"

    exercise_id = Column(String, primary_key=True)
    canonical_title = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt_datetime.utcnow)
    updated_at = Column(DateTime, default=dt_datetime.utcnow, onupdate=dt_datetime.utcnow)

    def __repr__(self):
        return f"<ExerciseCanonical exercise_id={self.exercise_id} canonical_title={self.canonical_title}>"

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
    # app_settings table is created by create_all above (new installs and existing DBs)
if __name__ == "__main__":
    init_db()
    print("✅ Database and tables initialized successfully.")
