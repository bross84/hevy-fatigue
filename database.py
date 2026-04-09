import os
from sqlalchemy import create_engine, Column, Integer, Float, String, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Path to your local database file
DB_URL = "sqlite:///./hevy_fatigue.db"

# Setup the Engine and Session
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- TABLE 1: Daily Questionnaire (TRAC-style) ---
class DailyReadiness(Base):
    __tablename__ = "daily_readiness"
    date = Column(Date, primary_key=True, default=datetime.utcnow().date)
    weight_lbs = Column(Float)
    sleep_quality = Column(Integer)  # Scale 0-4
    sleep_hours = Column(Float)
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

# --- TABLE 2: Workout Data (Imported from Hevy) ---
class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date)
    exercise_title = Column(String)
    weight_lbs = Column(Float)
    reps = Column(Integer)
    rpe = Column(Float)
    estimated_1rm = Column(Float)
    is_conditioning = Column(Boolean, default=False)

# This part actually creates the file and tables when you run the script
if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("✅ Database and tables initialized successfully.")