from datetime import date as date_type
from sqlalchemy import create_engine, Column, Integer, Float, String, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Path to your local database file
DB_URL = "sqlite:///./hevy_fatigue.db"

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
    # Training Load - system calculated from previous day's Hevy data
    # 0=no training, 1=below normal, 3=normal, 5=well above normal
    perceived_training_load = Column(Float, nullable=True)

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
    exercise_title = Column(String, nullable=False)
    set_number = Column(Integer)
    workout_id = Column(String, nullable=False)
    exercise_id = Column(String)
    notes = Column(String, nullable=True)
    weight_lbs = Column(Float)
    reps = Column(Integer)
    rpe = Column(Float)
    estimated_1rm = Column(Float)
    is_conditioning = Column(Boolean, default=False)

    def __repr__(self):
        return f"<WorkoutLog date={self.date} exercise={self.exercise_title} set={self.set_number}>"

# This part actually creates the file and tables when you run the script
def init_db():
    Base.metadata.create_all(bind=engine)
if __name__ == "__main__":
    init_db()
    print("✅ Database and tables initialized successfully.")
