"""Pydantic contracts: brief, claim ledger, gate decisions and content_package.json (§5)."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

# Brief §07 script shapes: SHORT 45–75 s, LONG 3–5 min.
DURATION_LIMITS = {"short": (45, 75), "long": (180, 300)}


class Brief(BaseModel):
    topic: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    learning_outcome: str = Field(min_length=1)
    language: str = Field(min_length=2)
    format: Literal["short", "long"]
    target_seconds: int
    cta: str = Field(min_length=1)
    brand_profile: str = "Ziro"

    @model_validator(mode="after")
    def _duration_fits_format(self) -> Self:
        low, high = DURATION_LIMITS[self.format]
        if not low <= self.target_seconds <= high:
            raise ValueError(f"{self.format} videos must be {low}-{high}s")
        return self


class Claim(BaseModel):
    id: str
    claim: str
    url: str
    title: str
    quote: str
    accessed_at: datetime
    published_at: datetime | None = None
    verification_status: Literal["verified", "unverified"]


class Hook(BaseModel):
    text: str
    score: float
    explanation: str


class Chapter(BaseModel):
    start_seconds: int = Field(ge=0)
    title: str


class ContentPackage(BaseModel):
    """The reviewed boundary between the content half and the execution half (D-13)."""

    schema_version: Literal["1.0"] = "1.0"
    brief: Brief
    claims: list[Claim]
    script: str
    hooks: list[Hook] = Field(min_length=5, max_length=5)
    titles: list[str] = Field(min_length=10, max_length=10)
    top_titles: list[str] = Field(min_length=3, max_length=3)
    thumbnail_text: str
    description: str
    tags: list[str] = Field(max_length=15)
    target_queries: list[str] = Field(min_length=3, max_length=3)
    chapters: list[Chapter]

    @model_validator(mode="after")
    def _thumbnail_text_short(self) -> Self:
        if len(self.thumbnail_text.split()) > 3:
            raise ValueError("thumbnail text must be at most 3 words")
        return self


class AiDisclosure(BaseModel):
    synthetic: bool
    reason: str = Field(min_length=1)


class Decision(BaseModel):
    """A gate decision, as passed to Command(resume=...) and recorded in approvals."""

    decision_id: str
    gate: str
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)
    notes: str = ""
    target: str | None = None
    ai_disclosure: AiDisclosure | None = None
    decided_at: datetime

    @model_validator(mode="after")
    def _reject_needs_target_and_notes(self) -> Self:
        if self.decision == "reject" and not (self.target and self.notes.strip()):
            raise ValueError("reject requires a target stage and notes")
        if self.gate == "qa_review" and self.decision == "approve" and self.ai_disclosure is None:
            raise ValueError("qa_review approval requires ai_disclosure")
        return self
