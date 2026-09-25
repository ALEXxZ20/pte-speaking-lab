"""User input contracts. Original Xingji facts are never inferred here."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.screenshots.mapper import tokenize

Color = Literal["red", "yellow", "green", "unknown"]
Review = Literal["confirmed", "unreviewed"]


class Score(BaseModel):
    value: float = Field(ge=0)
    max: float = Field(gt=0)

    @model_validator(mode="after")
    def within_scale(self):
        if self.value > self.max:
            raise ValueError("score_exceeds_scale")
        return self


class Token(BaseModel):
    index: int = Field(ge=0)
    surface: str
    normalized: str = ""
    color: Color = "unknown"
    color_review_status: Review = "unreviewed"
    color_source_screenshot_id: str | None = None


class PauseLabel(BaseModel):
    after_token_index: int | None = None
    raw_label: str
    review_status: Review = "unreviewed"


class SampleInput(BaseModel):
    role: Literal["user", "benchmark"]
    audio_asset_id: str | None = None
    color_screenshot_asset_ids: list[str] = Field(default_factory=list)
    pronunciation_score: Score | None = None
    fluency_score: Score | None = None
    content_score: Score | None = None
    transcript_raw: str | None = None
    transcript_source: Literal["xingji_copy", "manual_correction"] | None = None
    tokens: list[Token] = Field(default_factory=list)
    pause_labels: list[PauseLabel] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tokens(self):
        expected = tokenize(self.transcript_raw or "")
        if not self.tokens and expected:
            self.tokens = [Token(index=t["index"], surface=t["surface"], normalized=t["normalized"]) for t in expected]
        if len(self.tokens) != len(expected):
            raise ValueError("token_count_does_not_match_transcript")
        for actual, source in zip(self.tokens, expected):
            if actual.index != source["index"] or actual.surface != source["surface"]:
                raise ValueError("token_order_does_not_match_transcript")
            actual.normalized = source["normalized"]
            if actual.color != "unknown" and actual.color_review_status != "confirmed":
                raise ValueError("color_requires_confirmation")
        if any(p.after_token_index is not None and not (0 <= p.after_token_index < len(expected)) for p in self.pause_labels):
            raise ValueError("pause_position_out_of_range")
        if len(set(self.color_screenshot_asset_ids)) != len(self.color_screenshot_asset_ids):
            raise ValueError("duplicate_screenshot_asset")
        return self


class ExerciseInput(BaseModel):
    question_type: str = Field(min_length=1, max_length=30)
    title: str | None = Field(default=None, max_length=200)
    source_note: str | None = None
    source_question_id: str | None = None


class ComparisonInput(BaseModel):
    exercise: ExerciseInput
    samples: list[SampleInput] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def has_both_roles(self):
        if {sample.role for sample in self.samples} != {"user", "benchmark"}:
            raise ValueError("comparison_requires_user_and_benchmark")
        return self


class SampleUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    sample: SampleInput
