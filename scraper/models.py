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


class GrowthHabit(str, Enum):
    HERB = "herb"
    SHRUB = "shrub"
    TREE = "tree"
    VINE = "vine"
    GRASS_GRASSLIKE = "grass/grass-like"
    CACTUS_SUCCULENT = "cactus/succulent"
    FERN = "fern"


class Duration(str, Enum):
    ANNUAL = "annual"
    BIENNIAL = "biennial"
    PERENNIAL = "perennial"


class Light(str, Enum):
    SUN = "sun"
    PART_SHADE = "part shade"
    SHADE = "shade"


class Moisture(str, Enum):
    DRY = "dry"
    MOIST = "moist"
    WET = "wet"


class WaterUse(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Candidate:
    url: str
    display_name: str | None = None
    scientific_name: str | None = None
    common_name: str | None = None
    synonyms: list[str] = field(default_factory=list)
    direct_redirect: bool = False
    page_html: str | None = field(default=None, repr=False)


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
        if value["candidate"]:
            value["candidate"].pop("page_html", None)
        for candidate in value["candidates"]:
            candidate.pop("page_html", None)
        return value
