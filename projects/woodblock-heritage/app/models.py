"""Request contracts for heritage-review-v1.

Management fields (support/validation/review status) may be sent by a client
for compatibility, but the service always resets them on import. Unknown extra
fields are preserved inside the immutable raw_import snapshot.
"""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "heritage-review-v1"
ACCESS_POLICIES = frozenset({
    "synthetic-only",
    "local-unverified-no-publication",
    "cleared-for-publication",
})
PREDICATES = frozenset({
    "source_title",
    "source_edition_note",
    "source_category",
    "source_technique_note",
    "source_dimensions_note",
    "source_collection_note",
    "visual_description",
})


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    source_note: str = Field(min_length=1, max_length=2000)
    access_policy: str = Field(min_length=1, max_length=2000)
    physical_index: int | None = Field(default=None, ge=1, le=100000)
    printed_label: str | None = Field(default=None, max_length=64)
    image_base64: str = Field(min_length=1)

    @field_validator("access_policy")
    @classmethod
    def _known_policy(cls, value: str) -> str:
        text = value.strip()
        if text not in ACCESS_POLICIES:
            raise ValueError(f"access_policy must be one of {sorted(ACCESS_POLICIES)}")
        return text


class RegionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=64)
    kind: Literal["text", "image"]
    bbox: list[float] = Field(min_length=4, max_length=4)
    coordinate_system: Literal["normalized", "pixels"]
    text: str | None = Field(default=None, max_length=4000)
    text_kind: Literal["exact", "summary"] | None = None

    @field_validator("bbox")
    @classmethod
    def _finite_box(cls, value: list[float]) -> list[float]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("bbox values must be finite")
        return value

    @model_validator(mode="after")
    def _text_shape(self) -> "RegionIn":
        if self.kind == "image" and self.text not in (None, ""):
            raise ValueError("image region must not carry text")
        if self.kind == "text" and self.text is None:
            raise ValueError("text region needs text")
        if self.text_kind is not None and self.text is None:
            raise ValueError("text_kind requires text")
        return self


class ClaimIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=64)
    predicate: str = Field(min_length=1, max_length=64)
    object: dict[str, Any]
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)


class IssueIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    affected_claim_id: str | None = Field(default=None, max_length=64)


class WorkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    source_ids: list[str] = Field(min_length=1, max_length=4)
    regions: list[RegionIn] = Field(default_factory=list, max_length=200)
    claims: list[ClaimIn] = Field(default_factory=list, max_length=200)
    issues: list[IssueIn] = Field(default_factory=list, max_length=50)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    action: Literal["approve", "reject", "revise"]
    support_status: Literal["supported", "disputed", "insufficient"] | None = None
    predicate: str | None = Field(default=None, max_length=64)
    object: dict[str, Any] | None = None
    evidence_refs: list[str] | None = Field(default=None, max_length=50)
    reason: str | None = Field(default=None, max_length=1000)


class IssueResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    reason: str = Field(min_length=1, max_length=1000)


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    decisions: list[Decision] = Field(default_factory=list, max_length=200)
    issue_resolutions: list[IssueResolution] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _has_work(self) -> "ReviewCreate":
        if not self.decisions and not self.issue_resolutions:
            raise ValueError("review needs at least one decision or issue resolution")
        return self


class PublicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_id: str
    expected_version: int = Field(ge=1)
