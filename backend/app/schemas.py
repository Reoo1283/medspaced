from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Geçerli bir e-posta adresi girin")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserCreateRequest(RegisterRequest):
    role: Literal["student", "reviewer", "admin"] = "student"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
class ContentFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    error_message: str | None
    uploaded_by: str | None
    processed_at: datetime | None
    created_at: datetime


class ContentFileDetail(ContentFileOut):
    chunk_count: int = 0
    exercise_count: int = 0


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    chunk_index: int
    section_title: str
    heading_path: list | None
    page_number: int | None
    raw_text: str
    token_count: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: str
    progress: int
    message: str | None
    payload: dict | None
    result: dict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class GenerateRequest(BaseModel):
    skill_id: str
    exercise_types: list[Literal["mcq", "cloze", "matching", "vignette"]] = Field(
        default_factory=lambda: ["mcq", "cloze"]
    )
    max_chunks: int | None = Field(default=None, ge=1, le=200)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
class SkillCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    category: str = Field(default="genel", max_length=100)
    description: str = ""
    parent_id: str | None = None


class SkillUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    parent_id: str | None = None


class SkillOut(BaseModel):
    id: str
    title: str
    category: str
    description: str
    parent_id: str | None
    prerequisites: list[str] = Field(default_factory=list)
    mastery_score: float = 0.0
    unlocked: bool = False


class SkillTreeNode(SkillOut):
    children: list["SkillTreeNode"] = Field(default_factory=list)


class PrerequisiteRequest(BaseModel):
    prerequisite_id: str


class SkillProgressOut(BaseModel):
    skill_id: str
    title: str
    category: str
    mastery_score: float
    unlocked: bool
    last_practiced_at: datetime | None


# ---------------------------------------------------------------------------
# Exercises / review
# ---------------------------------------------------------------------------
class ReviewDecision(BaseModel):
    action: Literal["submit", "approve", "reject"]
    note: str | None = None


class SourceOut(BaseModel):
    chunk_id: str
    file_id: str
    filename: str
    section_title: str
    page_number: int | None
    snippet: str


class ExerciseOut(BaseModel):
    id: str
    skill_id: str | None
    skill_title: str | None
    concept_id: str | None
    type: str
    status: str
    payload: dict
    difficulty: float
    source: SourceOut | None
    generation_meta: dict | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------
class ReviewSubmit(BaseModel):
    exercise_id: str
    rating: Literal["again", "hard", "good", "easy"] | None = None
    answer: dict = Field(default_factory=dict)
    response_time_ms: int | None = Field(default=None, ge=0, le=600000)


class StudyItem(BaseModel):
    exercise_id: str
    skill_id: str | None
    skill_title: str | None
    type: str
    payload: dict
    source: SourceOut | None
    state: str
    due_at: datetime | None
    retrievability: float | None
    rotation_match: bool = False


class RotationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    starts_on: date | None = None
    ends_on: date | None = None


class RotationOut(BaseModel):
    id: str
    name: str
    starts_on: date | None
    ends_on: date | None
    active: bool


class ReviewResult(BaseModel):
    exercise_id: str
    is_correct: bool
    correct_answer: dict | None
    explanation: str | None
    rating: str
    next_due_at: datetime | None
    interval_days: int
    xp_awarded: int
    total_xp: int
    current_streak: int
    mastery_score: float | None
    ability_theta: float
    ability_se: float
    exercise_difficulty: float


class PersonalizationOut(BaseModel):
    desired_retention: float
    strategy: str
    reviews_analyzed: int
    accuracy: float | None
    lapse_rate: float | None
    parameter_count: int = 0
    optimized_at: datetime | None
    model_version: int = 3
    min_reviews: int = 512
    meets_threshold: bool = False
    can_rollback: bool = True
    optimizer_enabled: bool = True


class ExamStartRequest(BaseModel):
    skill_ids: list[str] = Field(default_factory=list, max_length=50)
    count: int = Field(default=10, ge=3, le=50)
    duration_minutes: int = Field(default=30, ge=5, le=180)


class ExamQuestion(BaseModel):
    exercise_id: str
    skill_id: str | None
    skill_title: str | None
    type: str
    payload: dict


class ExamSession(BaseModel):
    session_id: str
    started_at: datetime
    expires_at: datetime
    duration_minutes: int
    questions: list[ExamQuestion]


class ExamAnswer(BaseModel):
    exercise_id: str
    answer: dict = Field(default_factory=dict)
    response_time_ms: int | None = Field(default=None, ge=0)


class ExamSubmitRequest(BaseModel):
    session_id: str
    answers: list[ExamAnswer] = Field(default_factory=list, max_length=50)

    @field_validator("answers")
    @classmethod
    def validate_unique_answers(cls, value: list[ExamAnswer]) -> list[ExamAnswer]:
        ids = [item.exercise_id for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("Aynı soru için birden fazla cevap gönderilemez")
        return value


class ExamItemResult(BaseModel):
    exercise_id: str
    is_correct: bool
    correct_answer: dict | None
    explanation: str | None
    score: float | None = None


class ExamResult(BaseModel):
    score: float
    correct_count: int
    total: int
    xp_awarded: int
    total_xp: int
    league: str
    current_streak: int
    duration_seconds: int
    details: list[ExamItemResult]


class StudyStats(BaseModel):
    ability_theta: float
    ability_se: float
    rotation: str | None = None
    due_count: int
    new_count: int
    approved_exercise_count: int
    mastered_skill_count: int
    total_xp: int
    weekly_xp: int
    league: str
    current_streak: int
    longest_streak: int
    reviews_today: int
    last_active_date: date | None
    mastery_threshold: float = 70.0
    daily_new_card_limit: int = 20


# ---------------------------------------------------------------------------
# Ability / Analytics
# ---------------------------------------------------------------------------
class AbilityDimensionOut(BaseModel):
    dimension: str
    theta: float
    se: float
    attempts: int


class AbilityCorrelationOut(BaseModel):
    dimension_a: str
    dimension_b: str
    r: float | None
    n: int


class AbilityProfileOut(BaseModel):
    model: str
    theta: float
    se: float
    dimensions: list[AbilityDimensionOut]
    correlations: list[AbilityCorrelationOut]


class CalibrationBinOut(BaseModel):
    predicted_range: str
    avg_predicted: float | None
    actual_accuracy: float | None
    count: int


class DailyReviewOut(BaseModel):
    date: str
    count: int


class ReadinessComponentsOut(BaseModel):
    mastery_avg: float
    retention: float
    coverage: float


class LearningMetricsOut(BaseModel):
    reviews_total: int
    reviews_last_30d: int
    retention: float
    lapse_rate: float
    exam_readiness: float
    readiness_components: ReadinessComponentsOut
    calibration: list[CalibrationBinOut]
    daily_reviews: list[DailyReviewOut]


class LearningPolicyOut(BaseModel):
    mastery_threshold: float
    daily_new_card_limit: int


class LearningPolicyUpdate(BaseModel):
    mastery_threshold: float | None = Field(default=None, ge=50.0, le=95.0)
    daily_new_card_limit: int | None = Field(default=None, ge=5, le=100)


class DifficultyCalibrationItemOut(BaseModel):
    exercise_id: str
    skill_id: str | None
    type: str
    attempts: int
    approval_difficulty: float | None
    current_difficulty: float
    deviation: float | None
    abs_deviation: float | None


class DifficultyCalibrationReportOut(BaseModel):
    reviewed_items: int
    items_with_baseline: int
    mean_deviation: float | None
    mean_absolute_deviation: float | None
    max_absolute_deviation: float | None
    high_deviation_count: int
    high_deviation_threshold: float
    high_deviation_items: list[DifficultyCalibrationItemOut]
