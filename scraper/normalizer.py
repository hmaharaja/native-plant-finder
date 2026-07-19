from __future__ import annotations

import logging
import re
from enum import EnumMeta

from dataset_columns import (
    BLOOM_COLOR,
    BLOOM_TIME,
    DURATION,
    GROWTH_HABIT,
    LBJ_URL,
    LIGHT,
    MATCHED_SCIENTIFIC_NAME,
    MATURE_HEIGHT_MAX_FT,
    MATURE_HEIGHT_MIN_FT,
    MOISTURE,
    SOIL_CATEGORIES,
    SOIL_DESCRIPTION,
    WATER_USE,
)

from .models import Duration, GrowthHabit, Light, Moisture, WaterUse

LOGGER = logging.getLogger(__name__)


def _field(sections: dict, section: str, *names: str) -> str | None:
    values = sections.get(section, {})
    lowered = {key.casefold(): value for key, value in values.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value:
            return value.strip() or None
    return None


def _list(value: str | None, enum: EnumMeta | None = None, field_name: str = "value") -> str | None:
    if not value:
        return None
    known = {item.value: item.value for item in enum} if enum else {}
    items: list[str] = []
    for raw_item in re.split(r"[,;]|\band\b", value):
        item = raw_item.strip()
        if not item:
            continue
        normalized = item.casefold()
        if enum and normalized not in known:
            LOGGER.warning("Unmapped LBJ %s value: %r", field_name, item)
            items.append(item)
        else:
            items.append(known.get(normalized, normalized))
    return "|".join(dict.fromkeys(items)) or None


def _height(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    lower = value.casefold()
    factor = 1.0
    if "inch" in lower or re.search(r"\bin\b", lower):
        factor = 1 / 12
    elif "meter" in lower:
        factor = 3.28084

    def number(token: str) -> float:
        mixed = re.fullmatch(r"(\d+)-(\d+)/(\d+)", token)
        if mixed:
            return float(mixed.group(1)) + float(mixed.group(2)) / float(mixed.group(3))
        fraction = re.fullmatch(r"(\d+)/(\d+)", token)
        if fraction:
            return float(fraction.group(1)) / float(fraction.group(2))
        return float(token)

    numeric_token = r"\d+-\d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
    tokens = re.findall(numeric_token, value)
    nums = [number(token) for token in tokens]
    if not nums:
        return None, None
    explicit_range = re.search(rf"(?:{numeric_token})\s*(?:[-–—]|to)\s*(?:{numeric_token})", lower)
    if explicit_range and len(nums) >= 2:
        return min(nums[0], nums[1]) * factor, max(nums[0], nums[1]) * factor
    return None, nums[0] * factor


def normalize_traits(sections: dict, matched_name: str | None, url: str) -> dict:
    plant = "Plant Characteristics"
    growing = "Growing Conditions"
    bloom = "Bloom Information"
    size = _field(sections, plant, "Size Notes", "Height")
    low, high = _height(size)
    soil_description = _field(sections, growing, "Soil Description")
    soil_categories = None
    if soil_description:
        known = [item for item in ("clay", "loam", "sand", "gravel", "rock", "caliche")
                 if item in soil_description.casefold()]
        soil_categories = "|".join(known) or None
    return {
        MATCHED_SCIENTIFIC_NAME: matched_name,
        LBJ_URL: url,
        GROWTH_HABIT: _list(_field(sections, plant, "Habit"), GrowthHabit, GROWTH_HABIT),
        DURATION: _list(_field(sections, plant, "Duration"), Duration, DURATION),
        MATURE_HEIGHT_MIN_FT: low,
        MATURE_HEIGHT_MAX_FT: high,
        LIGHT: _list(_field(sections, growing, "Light Requirement"), Light, LIGHT),
        MOISTURE: _list(_field(sections, growing, "Soil Moisture"), Moisture, MOISTURE),
        WATER_USE: _list(_field(sections, growing, "Water Use"), WaterUse, WATER_USE),
        SOIL_CATEGORIES: soil_categories,
        SOIL_DESCRIPTION: soil_description,
        BLOOM_TIME: _list(_field(sections, bloom, "Bloom Time")),
        BLOOM_COLOR: _list(_field(sections, bloom, "Bloom Color")),
    }
