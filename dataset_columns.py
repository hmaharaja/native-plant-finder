from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

with Path(__file__).with_name("recommendation_categories.json").open(
    encoding="utf-8"
) as recommendation_categories_file:
    RECOMMENDATION_CATEGORY_DEFINITIONS = json.load(
        recommendation_categories_file
    )["categories"]

RecommendationCategory = Enum(
    "RecommendationCategory",
    {
        category.upper(): category
        for category in RECOMMENDATION_CATEGORY_DEFINITIONS
    },
    type=str,
)

USAGE_KEY = "usageKey"
CANONICAL_NAME = "canonicalName"
VERNACULAR_NAME = "vernacularName"
INPUT_NAME = "input_name"

MATCH_STATUS = "match_status"
MATCHED_SCIENTIFIC_NAME = "matched_scientific_name"
LBJ_URL = "lbj_url"
GROWTH_HABIT = "growth_habit"
DURATION = "duration"
MATURE_HEIGHT_MIN_FT = "mature_height_min_ft"
MATURE_HEIGHT_MAX_FT = "mature_height_max_ft"
LIGHT = "light"
MOISTURE = "moisture"
WATER_USE = "water_use"
SOIL_CATEGORIES = "soil_categories"
SOIL_DESCRIPTION = "soil_description"
BLOOM_TIME = "bloom_time"
BLOOM_COLOR = "bloom_color"
RECOMMENDATION_CATEGORY = "recommendation_category"

IMAGE_USAGE_KEY = "usageKey"
IMAGE_SOURCE = "source"
IMAGE_GBIF_ID = "gbifId"
IMAGE_URL = "imageUrl"
IMAGE_THUMBNAIL_URL = "thumbnailUrl"
IMAGE_SOURCE_URL = "sourceUrl"
IMAGE_LICENSE = "license"
IMAGE_CREATOR = "creator"
IMAGE_CREDIT = "credit"
IMAGE_PUBLISHER = "publisher"
IMAGE_WIDTH = "width"
IMAGE_HEIGHT = "height"
IMAGE_ACCEPTED_AT = "acceptedAt"
IMAGE_RANK = "rank"
IMAGE_REJECTION_REASON = "rejectionReason"

ECOREGION_ID = "ecoregion_id"
ECOREGION_NAME = "ecoregion_name"
OCCURRENCE_COUNT = "occurrence_count"
HUMAN_OBSERVATION_COUNT = "human_observation_count"
PRESERVED_SPECIMEN_COUNT = "preserved_specimen_count"
COORDINATE_UNCERTAINTY_MIN_M = "coordinate_uncertainty_min_m"
COORDINATE_UNCERTAINTY_MEDIAN_M = "coordinate_uncertainty_median_m"
COORDINATE_UNCERTAINTY_MAX_M = "coordinate_uncertainty_max_m"
FIRST_YEAR = "first_year"
LAST_YEAR = "last_year"
DATASET_COUNT = "dataset_count"

LBJ_TRAIT_FIELDS = [
    MATCHED_SCIENTIFIC_NAME,
    LBJ_URL,
    GROWTH_HABIT,
    DURATION,
    MATURE_HEIGHT_MIN_FT,
    MATURE_HEIGHT_MAX_FT,
    LIGHT,
    MOISTURE,
    WATER_USE,
    SOIL_CATEGORIES,
    SOIL_DESCRIPTION,
    BLOOM_TIME,
    BLOOM_COLOR,
]
LBJ_TRAIT_HEADERS = [USAGE_KEY, CANONICAL_NAME, VERNACULAR_NAME, MATCH_STATUS] + LBJ_TRAIT_FIELDS
LBJ_REVIEW_HEADERS = [
    USAGE_KEY,
    CANONICAL_NAME,
    VERNACULAR_NAME,
    "status",
    "reason",
    "error",
    "candidates",
]

PLANT_ECOREGION_COLUMNS = [
    USAGE_KEY,
    ECOREGION_ID,
    OCCURRENCE_COUNT,
    HUMAN_OBSERVATION_COUNT,
    PRESERVED_SPECIMEN_COUNT,
    COORDINATE_UNCERTAINTY_MIN_M,
    COORDINATE_UNCERTAINTY_MEDIAN_M,
    COORDINATE_UNCERTAINTY_MAX_M,
    FIRST_YEAR,
    LAST_YEAR,
    DATASET_COUNT,
    INPUT_NAME,
    CANONICAL_NAME,
    VERNACULAR_NAME,
    ECOREGION_NAME,
]

APP_DATA_LBJ_TRAIT_COLUMNS = [
    USAGE_KEY,
    GROWTH_HABIT,
    DURATION,
    MATURE_HEIGHT_MIN_FT,
    MATURE_HEIGHT_MAX_FT,
    LIGHT,
    MOISTURE,
    WATER_USE,
    SOIL_CATEGORIES,
    BLOOM_TIME,
    BLOOM_COLOR,
    LBJ_URL,
]

APP_DATA_FIELD_MAP = {
    USAGE_KEY: "usageKey",
    CANONICAL_NAME: "canonicalName",
    VERNACULAR_NAME: "vernacularName",
    OCCURRENCE_COUNT: "occurrenceCount",
    HUMAN_OBSERVATION_COUNT: "humanObservationCount",
    PRESERVED_SPECIMEN_COUNT: "preservedSpecimenCount",
    COORDINATE_UNCERTAINTY_MEDIAN_M: "coordinateUncertaintyMedianM",
    FIRST_YEAR: "firstYear",
    LAST_YEAR: "lastYear",
    GROWTH_HABIT: "growthHabit",
    DURATION: "duration",
    MATURE_HEIGHT_MIN_FT: "matureHeightMinFt",
    MATURE_HEIGHT_MAX_FT: "matureHeightMaxFt",
    LIGHT: "light",
    MOISTURE: "moisture",
    WATER_USE: "waterUse",
    SOIL_CATEGORIES: "soilCategories",
    BLOOM_TIME: "bloomTime",
    BLOOM_COLOR: "bloomColor",
    LBJ_URL: "lbjUrl",
    RECOMMENDATION_CATEGORY: "recommendationCategory",
}

APP_DATA_ARRAY_FIELDS = {
    "growthHabit",
    "light",
    "moisture",
    "soilCategories",
    "bloomTime",
    "bloomColor",
}

APP_DATA_INT_FIELDS = {
    "usageKey",
    "occurrenceCount",
    "humanObservationCount",
    "preservedSpecimenCount",
    "firstYear",
    "lastYear",
}

APP_DATA_FLOAT_FIELDS = {
    "coordinateUncertaintyMedianM",
    "matureHeightMinFt",
    "matureHeightMaxFt",
}
