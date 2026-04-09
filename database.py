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

# --- TABLE 1: Daily Questionnaire (TRAC-style) ---
class DailyReadiness(Base):
    __tablename__ = "daily_readiness"
    date = Column(Date, primary_key=True, default=date_type.today)
    weight_lbs = Column(Float, nullable=True)
    sleep_quality = Column(Integer, nullable=False)  # Scale 0-4
    sleep_hours = Column(Float, nullable=False)
    cns_prep = Column(Integer)       # Scale 0-4
    # Soreness (0-4)
    sore_quads = Column(Integer)
    sore_hams = Column(Integer)
    sore_push = Column(Integer)
    sore_pull = Column(Integer)
    # Joints (0-4)
    joint_shldr = Column(Integer)
    joint_elbow = Column(Integer)
    joint_hip = Column(Integer)
    joint_knee = Column(Integer)
    joint_lowback = Column(Integer)
    total_kcal = Column(Integer)

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
