from __future__ import annotations

import logging
import re
from enum import EnumMeta

from .models import Duration, GrowthHabit, Light, Moisture, WaterUse

LOGGER = logging.getLogger(__name__)


def _field(sections: dict, section: str, *names: str) -> str | None:
    values = sections.get(section, {})
    lowered = {k.casefold(): v for k, v in values.items()}
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

    tokens = re.findall(r"\d+-\d+/\d+|\d+/\d+|\d+(?:\.\d+)?", value)
    nums = [number(token) for token in tokens]
    if not nums:
        return None, None
    explicit_range = re.search(
        r"(?:\d+-\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*(?:-|–|to)\s*"
        r"(?:\d+-\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)",
        lower,
    )
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
        known = [x for x in ("clay", "loam", "sand", "gravel", "rock", "caliche") if x in soil_description.casefold()]
        soil_categories = "|".join(known) or None
    return {
        "matched_scientific_name": matched_name,
        "lbj_url": url,
        "growth_habit": _list(_field(sections, plant, "Habit"), GrowthHabit, "growth_habit"),
        "duration": _list(_field(sections, plant, "Duration"), Duration, "duration"),
        "mature_height_min_ft": low,
        "mature_height_max_ft": high,
        "light": _list(_field(sections, growing, "Light Requirement"), Light, "light"),
        "moisture": _list(_field(sections, growing, "Soil Moisture"), Moisture, "moisture"),
        "water_use": _list(_field(sections, growing, "Water Use"), WaterUse, "water_use"),
        "soil_categories": soil_categories,
        "soil_description": soil_description,
        "bloom_time": _list(_field(sections, bloom, "Bloom Time")),
        "bloom_color": _list(_field(sections, bloom, "Bloom Color")),
    }
