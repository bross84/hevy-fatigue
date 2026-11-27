import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from cryptography.fernet import InvalidToken
from credentials import UNREADABLE_KEY_MESSAGE, StoredKeyUnreadable
from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
from fastapi.staticfiles import StaticFiles
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from .database import get_db, get_rpe_percentage, init_db
from . import soreness
from . import exercise_creation
from . import motivation
from .motivation import MotivationInput
from . import session_checkins
from . import fatigue
from . import fatigue_trial
from . import trial_dashboard
from . import fatigue_relationships
from . import body_weight
from . import hevy_client
from . import exercise_state
from . import progress
from . import refs_store
from . import rpe_observed
from . import rpe_history
from . import rpe_assignments
from . import set_log
from . import session_review
from . import session_advice
from . import stress_index
from . import stress_service
from . import mesocycles
from . import plan_proposals
from . import plan_changes
from . import weekly_call
from . import week_entry
from . import week_text
from . import training_max
from .workout_payload import build_hevy_workout
from .workout_view import summarize_workout


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    yield


def initialize():
    init_db()
    mesocycles.migrate_single_week_plans()
    mesocycles.clear_initial_day_placeholders()
    mesocycles.deactivate_completed_plans()
    from . import workout_saves
    workout_saves.initialize()


app = FastAPI(title="Hevy-Fatigue Training", lifespan=lifespan)


@app.middleware("http")
async def isolated_preview(request: Request, call_next):
    # Preview DBs may contain an encrypted production key; never permit remote writes.
    # Mounted requests retain the host prefix in scope['path']; match this app's
    # route after removing its root path, just as for a standalone deployment.
    path = request.scope["path"]
    root = request.scope.get("root_path", "").rstrip("/")
    if root and path.startswith(root + "/"):
        path = path[len(root):]
    if os.environ.get("RACKBOOK_READ_ONLY_PREVIEW") == "1" and request.method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/hevy/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Hevy writes are disabled in this isolated local preview."}, status_code=403)
    response = await call_next(request)
    if path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get("/fatigue-trial/settings", response_model=fatigue_trial.TrialStatus)
def trial_settings():
    return {"enabled": fatigue_trial.enabled(), "preview": os.environ.get("RACKBOOK_READ_ONLY_PREVIEW") == "1"}


@app.post("/fatigue-trial/started", response_model=dict[str, bool])
def trial_started(data: fatigue_trial.MovementStart):
    return fatigue_trial.mark_started(data)


@app.get("/fatigue-trial/comparisons", response_model=list[fatigue_trial.TrialResult], response_model_exclude_none=True)
def trial_comparisons():
    return fatigue_trial.history()


@app.get("/fatigue-trial/evaluation", response_model=list[fatigue_trial.TrialEvaluation])
def trial_evaluation():
    return fatigue_trial.evaluation()


@app.get('/trial', include_in_schema=False)
def trial_page():
    return FileResponse(PACKAGE_DIR / "trial.html", headers=NO_CACHE)


@app.get('/fatigue-trial/dashboard', response_model=trial_dashboard.Dashboard, response_model_exclude_none=True)
def trial_dashboard_data():
    return trial_dashboard.dashboard()


@app.put("/fatigue-trial/settings", response_model=fatigue_trial.TrialStatus)
def trial_configure(data: fatigue_trial.TrialSettings):
    return fatigue_trial.configure(data.enabled)


@app.get("/fatigue-trial/daily", response_model=fatigue_trial.DailyCheckin)
def trial_daily(day: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$")):
    return fatigue_trial.daily(day)


@app.post("/fatigue-trial/snapshots", response_model=fatigue_trial.TrialResult, response_model_exclude_none=True)
def trial_snapshot(data: fatigue_trial.SnapshotInput):
    try:
        return fatigue_trial.record(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/fatigue-trial/snapshots/{trial_id}", response_model=fatigue_trial.TrialResult, response_model_exclude_none=True)
def trial_read(trial_id: str):
    try:
        return fatigue_trial.read(trial_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/fatigue-trial/snapshots/{trial_id}/complete", response_model=fatigue_trial.TrialResult, response_model_exclude_none=True)
def trial_complete(trial_id: str, data: fatigue_trial.CompletionInput):
    try:
        return fatigue_trial.complete(trial_id, data.hevy_workout_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/fatigue-trial/snapshots/{trial_id}/notes", response_model=dict[str, bool])
def trial_note(trial_id: str, data: fatigue_trial.TrialNote):
    try:
        return fatigue_trial.note(trial_id, data)
    except ValueError as exc:
        raise HTTPException(404, str(exc))

# Pages change whenever the app is rebuilt, so browsers must re-check them instead of reusing a stored copy.
NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    # The front door is the workout log.
    return RedirectResponse("/training/log", headers=NO_CACHE)


# The old multi-tab settings page is retired; its trial switch lives on the host Settings tab. Old bookmarks land there.
@app.get("/legacy")
def legacy_index():
    return RedirectResponse("/#settings", headers=NO_CACHE)


@app.get("/favicon.ico")
def favicon():
    return FileResponse(PACKAGE_DIR / "static/icon-192.png", media_type="image/png", headers=NO_CACHE)


# Lets a phone or tablet add the pages to its home screen and open them like an app.
@app.get("/manifest.webmanifest")
def web_app_manifest():
    return FileResponse(PACKAGE_DIR / "static/manifest.webmanifest", media_type="application/manifest+json", headers=NO_CACHE)


@app.get("/sw.js")
def service_worker():
    # Served from the root so it covers every page. It caches nothing; some browsers want one before offering "Install app".
    return FileResponse(PACKAGE_DIR / "static/sw.js", media_type="text/javascript", headers=NO_CACHE)


app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")


# ── Recent workouts (read from Hevy) ───────────────────────────────────────────

class SetView(BaseModel):
    index: int | None = None
    type: str
    weight_kg: float | None = None
    weight_lb: float | None = None
    reps: int | None = None
    rpe: float | None = None
    target_rpe: float | None = None
    distance_meters: float | None = None
    duration_seconds: float | None = None


class ExerciseView(BaseModel):
    title: str
    notes: str | None = None
    exercise_template_id: str | None = None
    sets: list[SetView]


class WorkoutView(BaseModel):
    id: str
    title: str
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_minutes: int | None = None
    working_sets: int
    volume_kg: float
    exercises: list[ExerciseView]
    soreness_editable: bool = False


class WorkoutsPage(BaseModel):
    page: int
    page_count: int
    workouts: list[WorkoutView]


@app.get("/recent")
def recent_page():
    return FileResponse(PACKAGE_DIR / "recent.html", headers=NO_CACHE)


def _call_hevy(call):
    """Run call(HevyClient) and translate Hevy and key failures into HTTP errors."""
    try:
        return call(hevy_client.HevyClient())
    except InvalidToken:
        raise HTTPException(
            status_code=400,
            detail=UNREADABLE_KEY_MESSAGE,
        )
    except ValueError as exc:  # no key stored, or a corrupt Fernet key file
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            detail = "Hevy rejected the API key. Check that it's current and that your account is Hevy Pro."
        else:
            detail = f"Hevy returned an error ({status})."
            try:
                message = exc.response.json().get("error")
            except ValueError:
                message = None
            if message:
                detail += f" {message}"
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Couldn't reach Hevy.")


@app.get("/hevy/workouts", response_model=WorkoutsPage)
def list_hevy_workouts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=10),  # Hevy allows at most 10 workouts per page
):
    data = _call_hevy(lambda client: client.list_workouts(page=page, page_size=page_size))
    raw = data.get("workouts", [])
    recorded = set_log.for_workouts([str(w.get("id") or "") for w in raw])
    return {
        "page": int(data.get("page", page)),
        "page_count": int(data.get("page_count", 1)),
        # RPEs Hevy dropped (below 6, or 6.5) come back from our own set record
        "workouts": [{**set_log.overlay_summary_rpe(summarize_workout(w), recorded.get(str(w.get("id") or ""), [])),
                      "soreness_editable": soreness.editable(w["id"])} for w in raw],
    }


# ── Log a workout (write to Hevy) ──────────────────────────────────────────────

class EntrySet(BaseModel):
    type: Literal["warmup", "normal", "failure", "dropset"] = "normal"
    weight_kg: float | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=0, le=10)
    target_rpe: float | None = Field(default=None, ge=0, le=10)
    review: session_review.SetEvidence | None = None
    ts: bool = False  # the set that sets this movement's TM; only takes effect once the workout is saved


class EntryExercise(BaseModel):
    exercise_template_id: str
    title: str | None = None
    notes: str | None = None
    weight_unit: Literal['kg', 'lb'] | None = None
    sets: list[EntrySet]


class PatternSoreness(BaseModel):
    level: int | None = Field(default=None, ge=0, le=3, strict=True)
    pain: bool = Field(default=False, strict=True)


class SessionSoreness(BaseModel):
    squat: PatternSoreness | None = None
    bench_press: PatternSoreness | None = None
    deadlift: PatternSoreness | None = None


@app.get("/soreness/patterns", response_model=dict[str, str])
def soreness_patterns():
    return soreness.patterns()


@app.get("/workout-soreness/{workout_id}", response_model=SessionSoreness)
def get_workout_soreness(workout_id: str):
    try:
        return soreness.read(workout_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))


@app.patch("/workout-soreness/{workout_id}", response_model=SessionSoreness)
def edit_workout_soreness(workout_id: str, ratings: SessionSoreness):
    try:
        return soreness.update(workout_id, ratings.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))


@app.post('/session-checkins')
def confirm_session_checkin(data: session_checkins.CheckinInput):
    try:
        return session_checkins.record(data)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


class WorkoutEntry(BaseModel):
    client_workout_id: UUID | None = None
    title: str
    weight_unit: Literal['kg', 'lb'] | None = None
    description: str | None = None
    start_time: str
    end_time: str
    exercises: list[EntryExercise]
    soreness: SessionSoreness | None = None
    motivation: MotivationInput | None = None
    checkin_required: Literal[True] | None = None
    planned_session: mesocycles.PlanLink | None = None
    prescription: session_review.Prescription | None = None
    advisory_links: list[session_advice.AdviceLink] | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def review_identities(self):
        if self.prescription is None:
            return self
        seen = set()
        originals = {ex.id: ex for ex in self.prescription.exercises}
        owners = {s.id: ex.id for ex in self.prescription.exercises for s in ex.sets}
        movements = set()
        for ex in self.exercises:
            ids = {s.review.exercise_id for s in ex.sets if s.review}
            if len(ids) != 1 or ids & movements:
                raise ValueError('Each completed movement needs a distinct review identity')
            movements.update(ids)
            for s in ex.sets:
                if s.review is None or s.review.set_id in seen:
                    raise ValueError('Completed sets need unique review identities')
                meta = s.review
                seen.add(meta.set_id)
                if meta.exercise_id in originals and originals[meta.exercise_id].exercise_template_id != ex.exercise_template_id:
                    raise ValueError('Review movement does not match the prescription')
                if meta.set_id in owners and owners[meta.set_id] != meta.exercise_id:
                    raise ValueError('Review set belongs to another prescribed movement')
        return self


@app.get('/session-reviews/{workout_id}', response_model=session_review.ReviewResponse)
def get_session_review(workout_id: str):
    return {**session_review.read(workout_id), 'advisory_outcomes':session_advice.outcomes(workout_id), 'motivation':motivation.read(workout_id)}


@app.post('/session-advice', response_model=session_advice.AdviceView)
def create_session_advice(data: session_advice.AdviceRequest):
    try:
        return session_advice.create(data)
    except session_advice.AdviceError as exc:
        raise HTTPException(exc.status,exc.message) from exc


@app.post('/session-advice/{recommendation_id}/decisions', response_model=session_advice.AdviceView)
def decide_session_advice(recommendation_id: UUID, data: session_advice.DecisionRequest):
    try:
        return session_advice.decide(recommendation_id,data)
    except session_advice.AdviceError as exc:
        raise HTTPException(exc.status,exc.message) from exc


class SavedWorkout(BaseModel):
    state: str | None = None
    client_workout_id: str | None = None
    hevy_workout_id: str | None = None
    status: str | None = None
    failure_reason: str | None = None
    monitoring_refresh: str | None = None
    monitoring_sync_url: str | None = None
    trial_results: list = []
    id: str | None = None
    plan_warning: str | None = None


class TrainingMax(BaseModel):
    found: bool
    e1rm_lb: float | None = None
    weight_lb: float | None = None
    reps: int | None = None
    rpe: float | None = None
    set_at: str | None = None


class RpeTable(BaseModel):
    rows: list[list[float]]  # [rpe, reps, fraction of e1RM], e.g. [8.0, 5, 0.826]


class ExerciseRefInput(BaseModel):
    weight_unit: Literal['kg', 'lb'] | None = None  # None follows the page's unit preference.
    basis: Literal["e1rm", "tm"] = "e1rm"
    auto_weights: bool = True
    ls: bool = True  # plan the next set from the last set's e1RM (LSe1RM)
    tm_pct: float = Field(default=refs_store.DEFAULT_TM_PCT, ge=0.5, le=1.0)
    step_kg: float = Field(default=refs_store.DEFAULT_STEP_KG, ge=0.25, le=10.0)  # plate step planned weights round to, in kg
    step_lb: float = Field(default=refs_store.DEFAULT_STEP_LB, ge=0.5, le=25.0)  # the same, when you lift in lb
    bar_kg: float = Field(default=refs_store.DEFAULT_BAR_KG, ge=0, le=100)  # the bar this movement is lifted with (for the plate loader)
    chain_kg: float = Field(default=refs_store.DEFAULT_CHAIN_KG, ge=0, le=200)  # chains hung on the bar: part of the load, not plates
    rest_sec: int | None = Field(default=None, ge=0, le=3600)  # this movement's rest timer in seconds (0 = off); None = the page's default


class ExerciseRef(ExerciseRefInput):
    exercise_template_id: str


class PreviousSet(BaseModel):
    type: str
    weight_kg: float | None = None
    weight_lb: float | None = None
    reps: int | None = None
    rpe: float | None = None


class ExerciseState(BaseModel):
    previous: list[PreviousSet] = []
    previous_workout_start_time: str | None = None
    found: bool
    workout_title: str | None = None
    workout_start_time: str | None = None
    set_weight_lb: float | None = None
    set_reps: int | None = None
    set_rpe: float | None = None
    e1rm_lb: float | None = None


class StressInput(BaseModel):
    sets: list[EntrySet] = Field(default_factory=list, max_length=500)
    preview_sets: list[EntrySet] | None = Field(default=None, max_length=500)
    session_start: datetime | None = None


class StressScore(BaseModel):
    total: float
    peripheral: float
    central: float
    sets: int
    estimated_sets: int
    skipped_sets: int


class StressWindow(BaseModel):
    median: float | None
    lower: float | None
    upper: float | None
    elevated_upper: float | None
    sessions: int
    estimated_sessions: int
    provisional: bool
    days: int


class MovementStress(BaseModel):
    model_version: str
    session: StressScore
    set_scores: list[StressScore | None] = Field(default_factory=list)
    preview: StressScore | None = None
    preview_set_scores: list[StressScore | None] = Field(default_factory=list)
    preview_status: str | None = None
    window: StressWindow
    status: Literal["no_sets", "no_baseline", "below_usual", "usual", "elevated", "much_higher"]
    rolling_7: StressScore
    rolling_28: StressScore
    days_since_last: int | None
    as_of: str


class StressMovement(BaseModel):
    id: str
    title: str
    primary_key: Literal["squat", "bench", "deadlift"] | None = None


class HistoricalStress(BaseModel):
    workout_id: str | None
    title: str
    start_time: str
    score: StressScore
    window: StressWindow
    status: str
    rolling_7: StressScore
    rolling_28: StressScore


class StressDashboard(BaseModel):
    exercise_template_id: str
    model_version: str
    as_of: str
    days: int
    current: MovementStress
    sessions: list[HistoricalStress]
    available_sessions: int
    first_recorded_at: str | None


@app.get("/stress")
@app.get("/stress/details")
def stress_dashboard_page():
    return FileResponse(PACKAGE_DIR / "stress.html", headers=NO_CACHE)


@app.get("/stress/movements", response_model=list[StressMovement])
def stress_movements():
    with get_db() as conn:
        rows = conn.execute("SELECT id, title FROM hevy_exercise_cache ORDER BY title COLLATE NOCASE").fetchall()
    primary = {progress.LIFT_TITLES[key]: key for key in ("squat", "bench", "deadlift")}
    return [{"id": r["id"], "title": r["title"], "primary_key": primary.get(r["title"])} for r in rows]


FatiguePattern = Literal["squat", "bench_press", "deadlift"]


class FatigueRelationshipInput(BaseModel):
    patterns: list[FatiguePattern] = Field(max_length=3)

    @field_validator("patterns")
    @classmethod
    def unique_patterns(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Choose each pattern at most once.")
        return value


class FatigueRelationship(FatigueRelationshipInput):
    exercise_template_id: str
    title: str
    suggested_patterns: list[FatiguePattern]
    reviewed: bool
    reviewed_at: str | None


@app.get("/fatigue/relationships", response_model=list[FatigueRelationship])
def list_fatigue_relationships():
    return fatigue_relationships.list_relationships()


@app.put("/fatigue/relationships/{exercise_id}", response_model=FatigueRelationship)
def save_fatigue_relationship(exercise_id: str, data: FatigueRelationshipInput):
    try:
        return fatigue_relationships.save(exercise_id, data.patterns)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class PendingFatigueMapping(BaseModel):
    exercise_template_id: str
    title: str


class FatigueContext(BaseModel):
    reference_exercise_days: float | None
    reference_pattern_days: float | None
    reference_related_sets_7: float | None
    recent_exercise_days: float | None
    recent_pattern_days: float | None
    recent_related_sets_7: float | None
    latest_exercise_days: float | None
    latest_pattern_days: float | None
    latest_related_sets_7: int | None
    current_exercise_days: float | None
    pending_mappings: list[PendingFatigueMapping]
    additional_work_since_ts: bool
    extra_sets_eligible: bool
    block_reasons: list[str]


class FatiguePoint(BaseModel):
    days_since_exercise: float | None
    days_since_pattern: float | None
    related_sets_7_before: int | None
    related_workouts_7_before: int | None
    dose_complete: bool
    rolling_sets_7: int
    start_time: str
    e1rm_lb: float | None
    ts_reps: int | None
    ts_rpe: float | None
    bodyweight_kg: float | None
    bw_readings: int
    relative_e1rm: float | None
    working_sets: int | None
    total_reps: int | None
    median_reps: float | None
    median_rpe: float | None
    soreness: int | None
    pain: bool


class FatigueCollection(BaseModel):
    ready: bool
    sessions: int
    required_sessions: int
    previous_paired: int
    recent_paired: int
    required_paired_per_window: int
    window_sessions: int
    recent_ratings: int
    required_recent_ratings: int


class FatigueTrend(BaseModel):
    model_version: str
    pattern: str | None
    as_of: str
    baseline_start: str | None
    gap_reset: bool
    comparable_sessions: int
    needed_sessions: int
    collection: FatigueCollection
    context: FatigueContext
    status: str
    action: str
    message: str
    reasons: list[str]
    e1rm_change_pct: float | None
    bw_change_pct: float | None
    relative_change_pct: float | None
    sets_change: float | None
    recent_sets: float | None
    recent_soreness: float | None
    points: list[FatiguePoint]


@app.get("/movement-fatigue/{exercise_template_id}", response_model=FatigueTrend)
def movement_fatigue(exercise_template_id: str):
    return fatigue.load(exercise_template_id, now=datetime.now(timezone.utc))


@app.get("/movement-stress/{exercise_template_id}/history", response_model=StressDashboard)
def movement_stress_history(exercise_template_id: str, days: int = Query(56, ge=0, le=3650)):
    entries = stress_service.history(exercise_template_id, lambda: _call_hevy(
        lambda client: client.exercise_history(exercise_template_id)))
    merged = stress_index.merge_history(entries, set_log.for_exercise(exercise_template_id))
    return {"exercise_template_id": exercise_template_id,
            **stress_index.build_dashboard(merged, now=datetime.now(timezone.utc), days=days)}


@app.post("/movement-stress/{exercise_template_id}", response_model=MovementStress)
def preview_movement_stress(exercise_template_id: str, data: StressInput):
    """Read-only preview: completed draft sets plus history, never a Hevy write."""
    if data.session_start is not None and data.session_start.tzinfo is None:
        raise HTTPException(status_code=422, detail="Session start must include a timezone.")
    entries = stress_service.history(exercise_template_id, lambda: _call_hevy(
        lambda client: client.exercise_history(exercise_template_id)))
    merged = stress_index.merge_history(entries, set_log.for_exercise(exercise_template_id))
    return stress_index.build_summary(merged, [s.model_dump() for s in data.sets],
        now=datetime.now(timezone.utc), session_start=data.session_start,
        preview_sets=[s.model_dump() for s in data.preview_sets] if data.preview_sets is not None else None)


@app.get("/log")
def log_page():
    return FileResponse(PACKAGE_DIR / "log.html", headers=NO_CACHE)


@app.get('/microcycles')
@app.get('/mesocycles')
def mesocycle_page():
    return FileResponse(PACKAGE_DIR / "mesocycles.html", headers=NO_CACHE)


def _plan_call(fn, *args):
    try:
        return fn(*args)
    except mesocycles.PlanError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.get('/api/mesocycles', response_model=list[mesocycles.PlanView])
def list_mesocycles():
    return mesocycles.list_plans()


@app.post('/api/mesocycles', response_model=mesocycles.PlanView)
def create_mesocycle(data: mesocycles.PlanInput):
    return _plan_call(mesocycles.save_plan, data)


@app.get('/api/mesocycles/{plan_id}', response_model=mesocycles.PlanView)
def get_mesocycle(plan_id: str):
    return _plan_call(mesocycles.get_plan, plan_id)


@app.get('/api/mesocycles/{plan_id}/sessions/{session_id}', response_model=mesocycles.PlanView)
def resolve_microcycle_session(plan_id: str, session_id: str):
    return _plan_call(mesocycles.resolve_plan, plan_id, session_id)


@app.put('/api/mesocycles/{plan_id}', response_model=mesocycles.PlanView)
def update_mesocycle(plan_id: str, data: mesocycles.PlanInput):
    return _plan_call(mesocycles.save_plan, data, plan_id)


class PlanProposalRequest(BaseModel):
    text: str = Field(min_length=1, max_length=plan_proposals.MAX_REPLY_CHARS)
    conversation_id: UUID
    turn_id: UUID


@app.post('/api/plan-proposals/preview')
def preview_plan_proposal(data: PlanProposalRequest):
    """Read-only: validate the reply's proposal and describe it. Writes nothing."""
    return plan_proposals.preview(data.text)


@app.post('/api/plan-proposals/save')
def save_plan_proposal(data: PlanProposalRequest):
    """Explicit user action: save the proposal as one new inactive draft microcycle."""
    try:
        return plan_proposals.save_draft(data.text, data.conversation_id, data.turn_id)
    except plan_proposals.ProposalError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


class WeekTextPreviewRequest(BaseModel):
    text: str = Field(max_length=week_text.MAX_TEXT_CHARS)
    # {normalised name as written: movement id} the athlete picked for names that did not match exactly.
    choices: dict[Annotated[str, Field(max_length=200)], Annotated[str, Field(max_length=200)]] = Field(default_factory=dict, max_length=200)


class WeekTextDraftsRequest(WeekTextPreviewRequest):
    program_name: str = Field(default='', max_length=90)
    cycle: int = Field(default=1, ge=1, le=9999)


@app.post('/api/week-text/preview')
def preview_week_text(data: WeekTextPreviewRequest):
    """Read-only: what the written week becomes, with every problem listed by line. Writes nothing."""
    return week_entry.preview(data.text, data.choices)


@app.post('/api/week-text/drafts')
def save_week_text_drafts(data: WeekTextDraftsRequest):
    """Explicit user action: save each written week as a new inactive draft microcycle, all or none."""
    try:
        return week_entry.save_drafts(data.text, data.choices, data.program_name.strip(), data.cycle)
    except week_entry.WeekTextError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


class PlanChangeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=plan_changes.MAX_REPLY_CHARS)
    conversation_id: UUID
    turn_id: UUID


def _change_call(function, *args):
    try:
        return function(*args)
    except plan_changes.ChangeError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.post('/api/plan-changes/preview')
def preview_plan_change(data: PlanChangeRequest):
    """Read-only: validate the reply's plan change against the current plan and describe it day by day."""
    return plan_changes.preview(data.text, data.conversation_id, data.turn_id)


@app.post('/api/plan-changes/accept')
def accept_plan_change(data: PlanChangeRequest):
    """The athlete's Accept tap: apply the coach's change to that plan, keeping the previous version for undo (ADR 0002)."""
    return _change_call(plan_changes.accept, data.text, data.conversation_id, data.turn_id)


@app.post('/api/plan-changes/{change_id}/undo')
def undo_plan_change(change_id: UUID):
    """The athlete's Undo tap: restore the plan as it was before that accepted change."""
    return _change_call(plan_changes.undo, str(change_id))


def _call(function, *args):
    try:
        return function(*args)
    except weekly_call.CallError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.get('/api/weekly-call')
def weekly_call_due():
    """Read-only: the finished microcycle whose weekly coaching call is due on the Log page, or null."""
    return weekly_call.rollover()


@app.get('/api/weekly-call/{plan_id}')
def weekly_call_status(plan_id: str):
    return _call(weekly_call.status, plan_id)


@app.post('/api/weekly-call/{plan_id}/preview')
def weekly_call_preview(plan_id: str, data: PlanProposalRequest):
    """Read-only: a proposal in this microcycle's call, described as a candidate next week."""
    return _call(weekly_call.preview, data.text, data.conversation_id, data.turn_id, plan_id)


@app.post('/api/weekly-call/{plan_id}/next-week')
def weekly_call_accept(plan_id: str, data: PlanProposalRequest):
    """The athlete's Accept tap in the weekly coaching call: create the next week and make it active (ADR 0002)."""
    return _call(weekly_call.accept_next_week, data.text, data.conversation_id, data.turn_id, plan_id)


@app.post('/api/weekly-call/{plan_id}/run-it-back')
def weekly_call_run_it_back(plan_id: str):
    """The athlete's Run it back tap: repeat the finished microcycle unchanged as the active next week. No AI."""
    return _call(weekly_call.run_it_back, plan_id)


@app.post('/api/weekly-call/{plan_id}/undo')
def weekly_call_undo(plan_id: str):
    """The athlete's Undo tap: remove the untouched next week and restore what was active before."""
    return _call(weekly_call.undo, plan_id)


@app.post('/api/mesocycles/{plan_id}/sessions/{session_id}/complete', response_model=mesocycles.PlanView)
def mark_microcycle_day_completed(plan_id: str, session_id: str):
    return _plan_call(mesocycles.mark_completed, plan_id, session_id)


@app.delete('/api/mesocycles/{plan_id}/sessions/{session_id}/complete', response_model=mesocycles.PlanView)
def undo_microcycle_day_completion(plan_id: str, session_id: str):
    return _plan_call(mesocycles.undo_manual_completion, plan_id, session_id)


class SkipDayRequest(BaseModel):
    note: str | None = Field(default=None, max_length=mesocycles.SKIP_NOTE_CHARS)


@app.post('/api/mesocycles/{plan_id}/sessions/{session_id}/skip', response_model=mesocycles.PlanView)
def skip_microcycle_day(plan_id: str, session_id: str, data: SkipDayRequest | None = None):
    """Resolve a day the athlete will not train: finished for plan progress, recorded as skipped. Local only."""
    return _plan_call(mesocycles.skip_day, plan_id, session_id, data.note if data else None)


@app.delete('/api/mesocycles/{plan_id}/sessions/{session_id}/skip', response_model=mesocycles.PlanView)
def undo_microcycle_day_skip(plan_id: str, session_id: str):
    return _plan_call(mesocycles.undo_skip, plan_id, session_id)


@app.post('/api/mesocycles/{plan_id}/activate', response_model=mesocycles.PlanView)
def activate_mesocycle(plan_id: str):
    return _plan_call(mesocycles.activate, plan_id)


@app.post('/api/mesocycles/{plan_id}/archive', status_code=204)
def archive_mesocycle(plan_id: str):
    _plan_call(mesocycles.archive, plan_id)
    return Response(status_code=204)


@app.post('/api/mesocycles/{plan_id}/deactivate', response_model=mesocycles.PlanView)
def deactivate_mesocycle(plan_id: str):
    return _plan_call(mesocycles.deactivate, plan_id)


@app.get("/rpe-table", response_model=RpeTable)
def get_rpe_table():
    """The RPE table in use, so the log page can turn an RPE and reps into a percentage of e1RM."""
    with get_db() as conn:
        rows = conn.execute("SELECT rpe, reps, percentage FROM rpe_chart ORDER BY rpe DESC, reps").fetchall()
    return {"rows": [[r["rpe"], r["reps"], r["percentage"]] for r in rows]}


class ObservedLift(BaseModel):
    key: rpe_assignments.ChartGroup
    title: str  # chart group label
    exercise_template_id: str | None = None  # None until a set of it has been logged with an RPE
    sets: int  # working sets logged with an RPE
    sessions: int


class ObservedCell(BaseModel):
    rpe: float
    reps: int
    n: int  # sets averaged into this cell (the TS counts like any other set)
    ts: int = 0  # how many of those are the TS
    observed: float  # fraction of each workout's fitted e1RM, averaged over the sets
    chart: float | None = None  # what the RPE table in use says for the same RPE and reps


class EstimatedCell(BaseModel):
    rpe: float
    reps: int
    estimated: float  # interpolated from the sets logged at nearby efforts, never from the table in use
    chart: float | None = None


class DataGate(BaseModel):
    passed: bool  # all three below met: estimated cells are shown
    sets: int
    min_sets: int
    workouts: int
    min_workouts: int
    k_span: float  # reps of effort between the hardest and easiest sets logged
    min_k_span: float


class FitSession(BaseModel):
    workout_start: str
    exercise_title: str | None = None
    e1rm_lb: float  # the e1RM that workout's sets point to along the fitted curve
    table_e1rm_lb: float | None = None  # the e1RM the TS gave from the table in use
    sets: int


class CurveFit(BaseModel):
    slope: float  # share of the max lost per extra rep to failure, fitted
    table_slope: float | None = None  # the same for the table in use
    rms_error: float  # typical miss of a set against the fit, as a fraction of the max
    informative_sessions: int  # workouts with sets at two or more different k: the ones that pin the slope
    sets_fitted: int
    sessions: list[FitSession]


class RpeSource(BaseModel):
    exercise_template_id: str
    title: str
    local_sets: int
    imported_sets: int


class RpeImportResult(BaseModel):
    workouts_scanned: int
    sessions_imported: int
    sets_imported: int
    local_sessions_preserved: int
    sessions_already_imported: int


class ObservedTable(BaseModel):
    exercise_template_id: str
    title: str | None = None
    sets_used: int  # working sets measured, the TS included
    ts_sets: int = 0
    cells: list[ObservedCell]
    estimated: list[EstimatedCell] = []  # only once the gate is passed
    gate: DataGate
    fit: CurveFit | None = None  # a table-free fit to all the sets; None until a workout has sets at two different k
    sources: list[RpeSource] = []


@app.get("/rpe-charts")
def rpe_charts_page():
    return FileResponse(PACKAGE_DIR / "rpe_charts.html", headers=NO_CACHE)


@app.get("/rpe-observed", response_model=list[ObservedLift])
def list_observed_lifts():
    return rpe_history.list_lifts()


@app.get('/rpe-chart-assignments', response_model=dict[str, rpe_assignments.Assignment])
def get_rpe_chart_assignments():
    return rpe_assignments.all_assignments()


@app.post("/rpe-history/import-bs-bridge", response_model=RpeImportResult)
def import_bs_bridge_rpe_history():
    prepared = _call_hevy(rpe_history.fetch_bridge)
    return rpe_history.store_import(prepared)


@app.get("/rpe-observed/group/{lift}", response_model=ObservedTable)
def get_observed_group(lift: rpe_assignments.ChartGroup):
    return rpe_history.build_group(lift, get_rpe_percentage)


@app.get("/rpe-observed/{exercise_template_id}", response_model=ObservedTable)
def get_observed_table(exercise_template_id: str):
    """The RPE table your own sets of this movement describe so far, next to the table in use."""
    sets = set_log.for_exercise(exercise_template_id)
    history = training_max.history(exercise_template_id)
    built = rpe_observed.build_observed(sets, history, get_rpe_percentage)
    built["fit"] = rpe_observed.fit_curve(sets, history, get_rpe_percentage)
    title = next((s["exercise_title"] for s in sets if s["exercise_title"]), None)
    return {"exercise_template_id": exercise_template_id, "title": title, **built}


@app.get("/exercise-refs", response_model=list[ExerciseRef])
def list_exercise_refs():
    return refs_store.list_refs()


@app.put("/exercise-refs/{exercise_template_id}", response_model=ExerciseRef)
def put_exercise_ref(exercise_template_id: str, data: ExerciseRefInput):
    return refs_store.save_ref(exercise_template_id, data.basis, data.ls, data.tm_pct, data.step_kg, data.step_lb, data.bar_kg, data.chain_kg, data.rest_sec, data.weight_unit, data.auto_weights)


@app.get("/hevy/exercise-state/{exercise_template_id}", response_model=ExerciseState)
def get_exercise_state(exercise_template_id: str):
    """A movement's current e1RM, worked out from its last session in Hevy with the user's RPE table."""
    entries = _call_hevy(lambda client: client.exercise_history(exercise_template_id))
    entries = set_log.overlay_exact_rpe(entries, set_log.for_exercise(exercise_template_id))  # RPEs Hevy dropped
    return exercise_state.build_exercise_state(entries, get_rpe_percentage, as_of=datetime.now(timezone.utc))


@app.get("/training-max/{exercise_template_id}", response_model=TrainingMax)
def get_training_max(exercise_template_id: str):
    """The movement's current TS: the set marked when its newest TS workout was saved."""
    return training_max.latest(exercise_template_id)


@app.post("/hevy/workouts", response_model=SavedWorkout, response_model_exclude_unset=True)
def create_hevy_workout(entry: WorkoutEntry):
    from . import workout_saves
    saved = workout_saves.save(entry, hevy_client.HevyClient)
    if entry.client_workout_id is None and saved['state'] not in ('complete', 'remote_saved'):
        # The old logger only checks HTTP success before clearing its draft.
        # Preserve non-success responses whenever no remote save is known.
        raise HTTPException(400 if saved['state'] == 'prepared' else 502,
                            saved['failure_reason'] or saved['status'])
    return saved


class ReconcileInput(BaseModel):
    hevy_workout_id: str = Field(min_length=1, max_length=200)


@app.get('/workout-saves/{client_workout_id}', response_model=SavedWorkout, response_model_exclude_unset=True)
def workout_save_status(client_workout_id: UUID):
    from . import workout_saves
    return workout_saves.status(client_workout_id)


@app.post('/workout-saves/{client_workout_id}/finalize', response_model=SavedWorkout, response_model_exclude_unset=True)
def workout_save_finalize(client_workout_id: UUID):
    from . import workout_saves
    return workout_saves.finish_or_pending(client_workout_id)


@app.post('/workout-saves/{client_workout_id}/reconcile', response_model=SavedWorkout, response_model_exclude_unset=True)
def workout_save_reconcile(client_workout_id: UUID, data: ReconcileInput):
    from . import workout_saves
    return workout_saves.reconcile(client_workout_id, data.hevy_workout_id, hevy_client.HevyClient)


# ── Settings ───────────────────────────────────────────────────────────────────

class ApiKeyInput(BaseModel):
    api_key: str


@app.get("/settings")
def get_settings():
    """Return whether the Hevy API key is configured. Never returns the key itself."""
    try:
        key = hevy_client.get_api_key()
    except StoredKeyUnreadable:
        return {"hevy_api_key_set": False, "hevy_api_key_preview": None,
                "hevy_api_key_error": UNREADABLE_KEY_MESSAGE}
    if key and len(key) >= 4:
        preview = "···" + key[-4:]
    elif key:
        preview = "···"
    else:
        preview = None
    return {"hevy_api_key_set": bool(key), "hevy_api_key_preview": preview}


@app.post("/settings/api-key", status_code=204)
def save_api_key(data: ApiKeyInput):
    """Encrypt and store the Hevy API key. Returns 204 on success."""
    key = data.api_key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="API key cannot be empty.")
    hevy_client.save_api_key(key)


# ── Exercises ──────────────────────────────────────────────────────────────────

@app.get('/exercise-creation/options')
def creation_options():
    from typing import get_args
    return {'enabled': exercise_creation.writes_enabled(), 'types': get_args(exercise_creation.ExerciseType),
            'equipment': get_args(exercise_creation.Equipment), 'muscles': get_args(exercise_creation.Muscle)}


def _creation_call(fn, *args):
    try:
        return fn(*args)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except httpx.HTTPError:
        raise HTTPException(502, 'Hevy is unavailable. Your exercise details have been kept; check status before retrying.')


@app.get('/exercise-creation/template/{template_id}')
def creation_template(template_id: str):
    return _creation_call(hevy_client.HevyClient().get_exercise_template, template_id)


@app.post('/exercise-creation')
def create_exercise(data: exercise_creation.CreationInput):
    return _creation_call(exercise_creation.create, data, hevy_client.HevyClient())


@app.get('/exercise-creation/{request_id}')
def creation_status(request_id: UUID):
    return _creation_call(exercise_creation.status, request_id)


@app.post('/exercise-creation/{request_id}/reconcile')
def reconcile_exercise_creation(request_id: UUID):
    return _creation_call(exercise_creation.reconcile, request_id, hevy_client.HevyClient())

@app.get("/exercises")
def get_exercises():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.primary_muscle, c.cached_at, l.id AS local_id
            FROM hevy_exercise_cache c
            LEFT JOIN local_exercises l ON l.hevy_id = c.id
            ORDER BY c.title COLLATE NOCASE ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/exercises/local")
def get_local_exercises():
    """The app's own exercise catalog. hevy_id is null while an exercise is not yet in Hevy."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT l.*, c.state AS creation_state
            FROM local_exercises l LEFT JOIN exercise_creations c ON c.id = l.id
            ORDER BY l.title COLLATE NOCASE ASC
            """
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["other_muscles"] = json.loads(item["other_muscles"] or "[]")
        item["is_custom"] = None if item["is_custom"] is None else bool(item["is_custom"])
        item["in_hevy"] = item["hevy_id"] is not None
        out.append(item)
    return out


@app.post("/exercises/sync")
def sync_exercises():
    count = hevy_client.HevyClient().sync_exercise_cache()
    return {"cached": count}


class BodyMeasurementOut(BaseModel):
    date: str
    weight_kg: float
    lean_mass_kg: float | None = None
    fat_percent: float | None = None


@app.post("/body-weight/sync")
def sync_body_weight():
    count = body_weight.sync_body_measurements(hevy_client.HevyClient())
    return {"synced": count}


@app.get("/body-weight", response_model=list[BodyMeasurementOut])
def get_body_weight():
    return body_weight.list_body_measurements()


class ProgressPoint(BaseModel):
    date: str
    e1rm_lb: float
    bodyweight_lb: float | None = None
    bodyweight_source_date: str | None = None
    bodyweight_age_days: int | None = None
    bodyweight_weigh_in_count: int | None = None
    dots: float | None = None


class ProgressData(BaseModel):
    lift: str
    title: str
    series: list[ProgressPoint]


@app.get("/progress")
def progress_page():
    return FileResponse(PACKAGE_DIR / "progress.html", headers=NO_CACHE)


@app.get("/progress/data", response_model=ProgressData)
def get_progress_data(lift: Literal["squat", "bench", "deadlift", "press"]):
    """A main lift's e1RM per session (Hevy history + the RPE table) next to smoothed bodyweight and DOTS."""
    title = progress.LIFT_TITLES[lift]
    with get_db() as conn:
        row = conn.execute("SELECT id FROM hevy_exercise_cache WHERE title = ?", (title,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"'{title}' isn't in the exercise cache. Sync exercises first.")
    entries = _call_hevy(lambda client: client.exercise_history(row["id"]))
    entries = set_log.overlay_exact_rpe(entries, set_log.for_exercise(row["id"]))  # RPEs Hevy dropped
    sessions = progress.e1rm_by_session(entries, get_rpe_percentage)
    sex = "female" if os.getenv("DOTS_SEX", "male").lower() == "female" else "male"
    series = progress.build_series(sessions, body_weight.list_body_measurements(), sex)
    return {"lift": lift, "title": title, "series": series}


