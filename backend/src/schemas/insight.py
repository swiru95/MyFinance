"""Insight schemas: the questionnaire, the ladder, and the three job kinds
(profile/digest/next_steps) built on the same pending -> done row as Report.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ..timeutils import as_utc

INSIGHT_KINDS = ("profile", "digest", "next_steps")
INSIGHT_LANGUAGES = ("en", "pl")


class InsightIn(BaseModel):
    language: str = Field("en", pattern="^(" + "|".join(INSIGHT_LANGUAGES) + ")$")
    # Required for a digest (a "YYYY-MM" month); ignored for profile/next_steps.
    period: str | None = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    kind: str
    period: str
    status: str
    language: str
    content: str
    content_en: str
    data: dict
    snapshot: dict
    ungrounded: list[str]
    model: str
    translator: str
    error: str

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)


class InsightSummary(BaseModel):
    """A history row without the text/data/snapshot bulk."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    period: str
    status: str
    language: str
    created_at: datetime

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)


class InsightStatus(BaseModel):
    configured: bool
    model: str
    translator: str


# --- Ladder ------------------------------------------------------------

class LadderRung(BaseModel):
    key: str
    order: int
    status: Literal["done", "in_progress", "todo", "not_applicable", "unknown"]
    figures: dict
    why_key: str
    feedback: dict | None = None


class LadderOut(BaseModel):
    rungs: list[LadderRung]
    # The same per-rung feedback keyed by rung, for clients that look a step
    # up by key (the next-steps cards do) rather than walking the list.
    feedback: dict[str, dict] = {}


class LadderStateIn(BaseModel):
    state: Literal["done", "dismissed", "later"]


# --- Profile questionnaire ----------------------------------------------

GOAL_CHOICES = (
    "retire_early", "buy_home", "kids_education", "financial_safety", "travel", "business",
)


class ProfileAnswers(BaseModel):
    """Settings key `profile_answers`. Every field optional so a
    half-finished questionnaire (or one never opened) still round-trips
    through GET/PUT rather than 422ing."""

    goals: list[str] = Field(default_factory=list)
    horizon_years: int | None = Field(None, ge=0, le=80)
    household: Literal["single", "couple", "family"] | None = None
    dependents: int | None = Field(None, ge=0, le=20)
    income_stability_feel: Literal["low", "medium", "high"] | None = None
    drawdown_reaction: Literal["sell_all", "sell_some", "hold", "buy_more"] | None = None
    loss_tolerance_pct: Literal[5, 10, 20, 30, 50] | None = None
    fire_interest: Literal["none", "curious", "planning", "committed"] | None = None
    experience: Literal["none", "basic", "intermediate", "advanced"] | None = None

    @field_validator("goals")
    @classmethod
    def _known_goals(cls, v: list[str]) -> list[str]:
        unknown = [g for g in v if g not in GOAL_CHOICES]
        if unknown:
            raise ValueError(f"unknown goal(s): {unknown}")
        return v


# --- Model output shapes (validated after parsing the LLM's JSON) -------

class ProfileMismatch(BaseModel):
    about: str
    stated: str
    actual: str
    why_it_matters: str


class ProfileResult(BaseModel):
    stated_tolerance: Literal["low", "medium", "high"]
    capacity: Literal["low", "medium", "high"]
    revealed: Literal["low", "medium", "high"]
    mismatches: list[ProfileMismatch] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list, max_length=3)
    suggested_style: Literal["safe", "balanced", "risky", "long_term"]
    summary_md: str


class NextStep(BaseModel):
    key: str
    title: str
    why_md: str


class NextStepsResult(BaseModel):
    steps: list[NextStep] = Field(default_factory=list, max_length=3)
