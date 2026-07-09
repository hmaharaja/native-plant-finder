from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MatchStatus(str, Enum):
    MATCHED = "matched"
    SYNONYM_MATCHED = "synonym_matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


@dataclass
class Candidate:
    url: str
    display_name: str | None = None
    scientific_name: str | None = None
    common_name: str | None = None
    synonyms: list[str] = field(default_factory=list)
    direct_redirect: bool = False


@dataclass
class Match:
    status: MatchStatus
    candidate: Candidate | None = None
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value
