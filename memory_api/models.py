from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class MemoryType(str, Enum):
    profile = "profile"
    preferences = "preferences"
    active_projects = "active_projects"
    routines = "routines"
    short_term = "short_term"


class ProposalStatus(str, Enum):
    queued = "queued"
    committed = "committed"
    needs_review = "needs_review"
    rejected = "rejected"


@dataclass
class ReadResponse:
    user_id: str
    source: str
    updated_at: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    memory_type: str
    source: str
    snippet: str
    score: float
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResponse:
    user_id: str
    query: str
    results: list[SearchResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "query": self.query,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass
class ProposeMemoryUpdateRequest:
    user_id: str
    request_id: str
    proposed_by: str = "openclaw"
    memory_type: MemoryType = MemoryType.preferences
    operation: Literal["append", "update"] = "update"
    target_path: str = ""
    evidence: list[str] = field(default_factory=list)
    candidate_value: str | list[str] = ""
    confidence: Confidence = Confidence.medium
    reason: str = ""
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if isinstance(self.memory_type, str):
            self.memory_type = MemoryType(self.memory_type)
        if isinstance(self.confidence, str):
            self.confidence = Confidence(self.confidence)

    def model_dump(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_type"] = self.memory_type.value
        payload["confidence"] = self.confidence.value
        return payload


@dataclass
class ProposeMemoryUpdateResponse:
    proposal_id: str
    status: ProposalStatus
    stored_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass
class CommitMemoryUpdateRequest:
    proposal_id: str
    approved_by: str = "memory-policy-engine"
    commit_mode: Literal["merge", "replace"] = "merge"


@dataclass
class CommitMemoryUpdateResponse:
    proposal_id: str
    status: ProposalStatus
    written_files: list[str]
    conflicts: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
