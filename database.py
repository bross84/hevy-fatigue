from datetime import date as date_type
from sqlalchemy import create_engine, Column, Integer, Float, String, Date, Boolean, UniqueConstraint
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
    weight_lbs = Column(Float, nullable=True)
    # Soreness (0=none, 4=severe pain/limited ROM)
    sore_quad_dom = Column(Integer)       # Squat patterns, quads
    sore_posterior = Column(Integer)      # Deadlift patterns, hamstrings, glutes, erectors
    sore_upper_push = Column(Integer)     # Bench variations, triceps
    sore_upper_pull = Column(Integer)     # Rows, pulldowns, rear delts
    # Joint Health (0=no issues, 4=significant pain)
    joint_upper = Column(Integer)         # Shoulders, elbows, wrists
    joint_lower = Column(Integer)         # Low back, hips, knees
    # Readiness (0=fresh, 4=super fatigued/tired)
    tiredness = Column(Integer)
    perceived_recovery = Column(Integer)
    # Stress scores - system calculated from previous day's Hevy data
    # central_stress:    driven by intensity (RPE/% of 1RM) — CNS fatigue
    # peripheral_stress: driven by volume (sets x reps) — muscular fatigue
    central_stress = Column(Float, nullable=True)
    peripheral_stress = Column(Float, nullable=True)
    # Optional biometric inputs (manual entry)
    hrv_ms = Column(Float, nullable=True)        # Morning HRV in milliseconds
    sleep_hours = Column(Float, nullable=True)   # Total sleep time
    sleep_quality = Column(Integer, nullable=True)  # 0=terrible, 4=excellent

    def __repr__(self):
        return f"<DailyReadiness date={self.date} weight={self.weight_lbs}>"

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

# --- TABLE 4: Exercise Movement Pattern Mapping ---
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

# This part actually creates the file and tables when you run the script
def init_db():
    Base.metadata.create_all(bind=engine)
    # Migrate: add new optional columns to existing databases without wiping data
    _migrate_add_columns(engine, "daily_readiness", [
        ("hrv_ms",        "REAL"),
        ("sleep_hours",   "REAL"),
        ("sleep_quality", "INTEGER"),
    ])

def _migrate_add_columns(eng, table: str, columns: list):
    """Safely add columns to an existing table if they don't already exist."""
    with eng.connect() as conn:
        existing = {row[1] for row in conn.execute(
            __import__('sqlalchemy').text(f"PRAGMA table_info({table})")
        )}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(__import__('sqlalchemy').text(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                ))
        conn.commit()
if __name__ == "__main__":
    init_db()
    print("✅ Database and tables initialized successfully.")
