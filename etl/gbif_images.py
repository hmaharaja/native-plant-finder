from __future__ import annotations

import json
import logging
import os
import re
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from dataset_columns import (
    IMAGE_ACCEPTED_AT,
    IMAGE_CREATOR,
    IMAGE_CREDIT,
    IMAGE_GBIF_ID,
    IMAGE_HEIGHT,
    IMAGE_LICENSE,
    IMAGE_PUBLISHER,
    IMAGE_RANK,
    IMAGE_REJECTION_REASON,
    IMAGE_SOURCE,
    IMAGE_SOURCE_URL,
    IMAGE_THUMBNAIL_URL,
    IMAGE_URL,
    IMAGE_USAGE_KEY,
    IMAGE_WIDTH,
    USAGE_KEY,
)
from etl.functions import normalize_key


LOGGER = logging.getLogger(__name__)

GBIF_OCCURRENCE_SEARCH_URL = "https://api.gbif.org/v1/occurrence/search"
GBIF_OCCURRENCE_URL_TEMPLATE = "https://www.gbif.org/occurrence/{gbif_id}"
DEFAULT_PLANTS_CSV_PATH = Path("datasets/gbif_species_match_cleaned.csv")
DEFAULT_PROBLEMS_CSV_PATH = Path("datasets/problems_cleaned.csv")
DEFAULT_OUTPUT_DIR = Path("datasets/app_data/plant_images")
DEFAULT_BUCKET_COUNT = 64
DEFAULT_LIMIT_PER_TAXON = 20
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_FACTOR = 0.5
DEFAULT_RETRY_AFTER_CAP_SECONDS = 120.0
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_CONTENT_LENGTH_BYTES = 10 * 1024 * 1024
DEFAULT_DELAY_BETWEEN_TAXA = 1.0
DEFAULT_DELAY_BETWEEN_URL_CHECKS = 0.25
DEFAULT_EXCLUDED_PROBLEM_MATCH_TYPES = ("HIGHERRANK",)
DEFAULT_USER_AGENT = (
    "native-plant-finder-gbif-image-etl/1.0 "
    "(set GBIF_USER_AGENT with project/contact details for production runs)"
)
DEFAULT_DWCA_CHUNKSIZE = 100_000
DWCA_OCCURRENCE_MEMBER = "occurrence.txt"
DWCA_MULTIMEDIA_MEMBER = "multimedia.txt"
MIN_IMAGE_WIDTH = 320
MIN_IMAGE_HEIGHT = 240
MIN_ASPECT_RATIO = 0.5
MAX_ASPECT_RATIO = 2.0
TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

ACCEPTED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

LIKELY_SPECIMEN_PATTERNS = (
    "herbarium",
    "specimen",
    "preserved specimen",
    "museum",
    "collection",
    "pressed",
    "scan",
    "label",
)

LICENSE_PATTERNS = (
    (re.compile(r"(?:^|/)zero/1\.0|cc0|publicdomain/zero", re.I), "CC0"),
    (re.compile(r"(?:^|/)publicdomain(?:/|$)|public domain", re.I), "Public Domain"),
    (re.compile(r"by-sa(?:/|_|-)?(?:4\.0|3\.0|2\.5|2\.0)?", re.I), "CC BY-SA"),
    (re.compile(r"by(?:/|_|-)?(?:4\.0|3\.0|2\.5|2\.0)?", re.I), "CC BY"),
)

DISALLOWED_LICENSE_PATTERN = re.compile(
    r"by-nc|by-nd|nc-|nd-|noncommercial|no.?derivatives|all rights reserved|unspecified|unknown",
    re.I,
)


@dataclass(frozen=True)
class ImageValidation:
    ok: bool
    reason: str | None = None


@dataclass(frozen=True)
class RetryResult:
    response: requests.Response | None
    transient_failure: bool = False
    exception: requests.RequestException | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_usage_keys(path: str | Path, usage_key_column: str = USAGE_KEY) -> list[str]:
    rows = pd.read_csv(path, dtype=str, usecols=[usage_key_column])
    keys = rows[usage_key_column].map(normalize_key).dropna().drop_duplicates()
    return sorted(keys, key=lambda value: int(value) if value.isdigit() else value)


def read_problem_usage_keys(
    path: str | Path,
    *,
    match_types: Iterable[str] = DEFAULT_EXCLUDED_PROBLEM_MATCH_TYPES,
    usage_key_column: str = USAGE_KEY,
    match_type_column: str = "matchType",
) -> set[str]:
    problems_path = Path(path)
    if not problems_path.exists():
        LOGGER.warning("Problems CSV not found; no usageKeys excluded path=%s", problems_path)
        return set()

    rows = pd.read_csv(problems_path, dtype=str)
    missing = {usage_key_column, match_type_column} - set(rows.columns)
    if missing:
        raise ValueError(f"Problems CSV missing required columns: {', '.join(sorted(missing))}")

    excluded_match_types = {str(match_type).upper() for match_type in match_types}
    mask = rows[match_type_column].fillna("").str.upper().isin(excluded_match_types)
    return {
        key
        for key in rows.loc[mask, usage_key_column].map(normalize_key).dropna().drop_duplicates()
        if key is not None
    }


def filter_usage_keys(
    usage_keys: Iterable[str],
    *,
    excluded_usage_keys: Iterable[str] = (),
    offset: int = 0,
    limit: int | None = None,
) -> list[str]:
    keys = [key for key in (normalize_key(key) for key in usage_keys) if key is not None]
    excluded = {key for key in (normalize_key(key) for key in excluded_usage_keys) if key is not None}
    filtered = [key for key in keys if key not in excluded]
    if offset:
        filtered = filtered[offset:]
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


def default_user_agent() -> str:
    return os.environ.get("GBIF_USER_AGENT") or DEFAULT_USER_AGENT


def configure_http_session(
    session: requests.Session | None = None,
    *,
    user_agent: str | None = None,
) -> requests.Session:
    active_session = session or requests.Session()
    headers = getattr(active_session, "headers", None)
    if headers is None:
        active_session.headers = {}
        headers = active_session.headers
    headers.update({"User-Agent": user_agent or default_user_agent()})

    mount = getattr(active_session, "mount", None)
    if callable(mount):
        adapter = HTTPAdapter(pool_connections=2, pool_maxsize=2)
        active_session.mount("https://", adapter)
        active_session.mount("http://", adapter)
    return active_session


def normalize_license(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or DISALLOWED_LICENSE_PATTERN.search(text):
        return None
    for pattern, normalized in LICENSE_PATTERNS:
        if pattern.search(text):
            return normalized
    return None


def _candidate_license(occurrence: Mapping[str, object], media: Mapping[str, object]) -> str | None:
    return normalize_license(media.get("license") or occurrence.get("license"))


def _is_url_safe(url: object) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _media_identifier(media: Mapping[str, object]) -> str | None:
    for key in ("identifier", "references", "source"):
        value = media.get(key)
        if _is_url_safe(value):
            return str(value).strip()
    return None


def _to_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        number = int(float(str(value)))
    except ValueError:
        return None
    return number if number >= 0 else None


def _image_dimensions(media: Mapping[str, object]) -> tuple[int | None, int | None]:
    width = _to_int(media.get("width") or media.get("pixelXDimension"))
    height = _to_int(media.get("height") or media.get("pixelYDimension"))
    return width, height


def _has_unknown_dimensions(width: int | None, height: int | None) -> bool:
    return width is None or height is None


def _has_useful_dimensions(width: int | None, height: int | None) -> bool:
    if _has_unknown_dimensions(width, height):
        return True
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT or height == 0:
        return False
    aspect_ratio = width / height
    return MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO


def _media_type(media: Mapping[str, object]) -> str:
    return str(media.get("type") or media.get("format") or "").casefold()


def _has_still_image_media(media: Mapping[str, object]) -> bool:
    media_type = _media_type(media)
    return "stillimage" in media_type or media_type.startswith("image/")


def _matches_requested_taxon(usage_key: str, occurrence: Mapping[str, object]) -> bool:
    requested = normalize_key(usage_key)
    if requested is None:
        return False
    for key in ("taxonKey", "acceptedTaxonKey", "speciesKey"):
        if normalize_key(occurrence.get(key)) == requested:
            return True
    return False


def _has_major_issues(occurrence: Mapping[str, object]) -> bool:
    raw = occurrence.get("issues")
    if raw is None:
        return False
    values = raw if isinstance(raw, list) else str(raw).split(";")
    issue_text = " ".join(str(value) for value in values).casefold()
    return any(
        marker in issue_text
        for marker in (
            "taxon_match_fuzzy",
            "taxon_match_higherrank",
            "country_coordinate_mismatch",
            "zero_coordinate",
            "coordinate_invalid",
            "coordinate_out_of_range",
            "geospatial_issue",
        )
    )


def _is_likely_specimen(occurrence: Mapping[str, object], media: Mapping[str, object]) -> bool:
    if str(occurrence.get("basisOfRecord") or "").upper() == "PRESERVED_SPECIMEN":
        return True
    text = " ".join(
        str(value)
        for value in (
            occurrence.get("datasetName"),
            occurrence.get("datasetTitle"),
            occurrence.get("institutionCode"),
            occurrence.get("collectionCode"),
            media.get("title"),
            media.get("description"),
            media.get("identifier"),
            media.get("references"),
        )
        if value
    ).casefold()
    return any(pattern in text for pattern in LIKELY_SPECIMEN_PATTERNS)


def _content_type_allowed(content_type: str | None) -> bool:
    if not content_type:
        return False
    media_type = content_type.split(";", 1)[0].strip().casefold()
    return media_type in ACCEPTED_CONTENT_TYPES


def _is_transient_exception(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    response = getattr(exc, "response", None)
    return bool(response is not None and response.status_code in TRANSIENT_STATUS_CODES)


def _retry_after_seconds(response: requests.Response, *, cap_seconds: float = DEFAULT_RETRY_AFTER_CAP_SECONDS) -> float | None:
    raw_retry_after = response.headers.get("Retry-After")
    if raw_retry_after is None:
        return None

    try:
        seconds = float(raw_retry_after)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw_retry_after)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()

    if seconds < 0:
        seconds = 0
    return min(seconds, cap_seconds)


def _retry_sleep_seconds(
    attempt: int,
    *,
    response: requests.Response | None,
    backoff_factor: float,
    retry_after_cap_seconds: float = DEFAULT_RETRY_AFTER_CAP_SECONDS,
) -> float:
    if response is not None and response.status_code == 429:
        retry_after = _retry_after_seconds(response, cap_seconds=retry_after_cap_seconds)
        if retry_after is not None:
            return retry_after
    return backoff_factor * (2**attempt)


def _request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    timeout: float = DEFAULT_TIMEOUT,
    transient_status_codes: frozenset[int] = TRANSIENT_STATUS_CODES,
    retry_after_cap_seconds: float = DEFAULT_RETRY_AFTER_CAP_SECONDS,
    **kwargs,
) -> RetryResult:
    attempts = max(0, retries) + 1
    last_exception: requests.RequestException | None = None

    for attempt in range(attempts):
        response: requests.Response | None = None
        try:
            response = getattr(session, method)(url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_exception = exc
            if not _is_transient_exception(exc) or attempt == attempts - 1:
                return RetryResult(None, transient_failure=_is_transient_exception(exc), exception=exc)
        else:
            if response.status_code not in transient_status_codes:
                return RetryResult(response)
            if attempt == attempts - 1:
                return RetryResult(response, transient_failure=True)

        sleep_seconds = _retry_sleep_seconds(
            attempt,
            response=response,
            backoff_factor=backoff_factor,
            retry_after_cap_seconds=retry_after_cap_seconds,
        )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return RetryResult(None, transient_failure=True, exception=last_exception)


def validate_image_url(
    session: requests.Session,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_content_length_bytes: int = DEFAULT_MAX_CONTENT_LENGTH_BYTES,
) -> ImageValidation:
    if not _is_url_safe(url):
        return ImageValidation(False, "unsafe_url")

    original_redirects = session.max_redirects
    session.max_redirects = max_redirects
    try:
        result = _request_with_retries(
            session,
            "head",
            url,
            allow_redirects=True,
            timeout=timeout,
            retries=retries,
            backoff_factor=backoff_factor,
        )
        if result.transient_failure:
            return ImageValidation(False, "transient_image_url_failure")
        if result.response is None:
            return ImageValidation(False, "image_url_unreachable")

        response = result.response
        if response.status_code in {405, 403}:
            result = _request_with_retries(
                session,
                "get",
                url,
                allow_redirects=True,
                stream=True,
                timeout=timeout,
                retries=retries,
                backoff_factor=backoff_factor,
            )
            if result.transient_failure:
                return ImageValidation(False, "transient_image_url_failure")
            if result.response is None:
                return ImageValidation(False, "image_url_unreachable")
            response = result.response
        response.raise_for_status()
    except requests.RequestException:
        return ImageValidation(False, "image_url_unreachable")
    finally:
        session.max_redirects = original_redirects

    if len(response.history) > max_redirects:
        return ImageValidation(False, "too_many_redirects")
    if not _is_url_safe(response.url):
        return ImageValidation(False, "unsafe_redirect")
    if not _content_type_allowed(response.headers.get("Content-Type")):
        return ImageValidation(False, "non_image_content_type")

    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        length = _to_int(content_length)
        if length is not None and length > max_content_length_bytes:
            return ImageValidation(False, "image_too_large")

    return ImageValidation(True)


def _cheap_rejection_reason(
    usage_key: str,
    occurrence: Mapping[str, object],
    media: Mapping[str, object],
    *,
    validate_url: bool,
) -> str | None:
    if not _has_still_image_media(media):
        return "non_image_media"
    image_url = _media_identifier(media)
    if image_url is None:
        return "missing_image_url"
    if _candidate_license(occurrence, media) is None:
        return "disallowed_or_missing_license"
    if not _matches_requested_taxon(usage_key, occurrence):
        return "taxon_mismatch"
    if str(occurrence.get("occurrenceStatus") or "PRESENT").upper() != "PRESENT":
        return "not_present"
    if _has_major_issues(occurrence):
        return "major_gbif_issue"
    if _is_likely_specimen(occurrence, media):
        return "likely_specimen_image"

    width, height = _image_dimensions(media)
    if not _has_useful_dimensions(width, height):
        return "low_resolution"
    if _has_unknown_dimensions(width, height) and not validate_url:
        return "unknown_dimensions_unvalidated"

    return None


def rejection_reason(
    usage_key: str,
    occurrence: Mapping[str, object],
    media: Mapping[str, object],
    *,
    validate_url: bool = True,
    session: requests.Session | None = None,
) -> str | None:
    reason = _cheap_rejection_reason(usage_key, occurrence, media, validate_url=validate_url)
    if reason:
        return reason

    if validate_url:
        image_url = _media_identifier(media)
        active_session = session or requests.Session()
        validation = validate_image_url(active_session, image_url or "")
        if not validation.ok:
            return validation.reason or "image_url_invalid"

    return None


def _license_score(license_name: str | None) -> int:
    return {"CC0": 0, "Public Domain": 0, "CC BY": 1, "CC BY-SA": 2}.get(license_name or "", 9)


def _candidate_score(usage_key: str, occurrence: Mapping[str, object], media: Mapping[str, object]) -> tuple:
    width, height = _image_dimensions(media)
    exact_taxon = normalize_key(occurrence.get("acceptedTaxonKey") or occurrence.get("taxonKey")) == usage_key
    human_observation = str(occurrence.get("basisOfRecord") or "").upper() == "HUMAN_OBSERVATION"
    area = (width or 0) * (height or 0)
    license_name = _candidate_license(occurrence, media)
    return (
        0 if exact_taxon else 1,
        0 if human_observation else 1,
        _license_score(license_name),
        -area,
        str(occurrence.get("datasetKey") or ""),
        str(occurrence.get("gbifID") or ""),
    )


def _credit(occurrence: Mapping[str, object], media: Mapping[str, object]) -> str | None:
    creator = _first_text(media, "creator", "createdBy", "rightsHolder")
    publisher = _first_text(occurrence, "publisher", "datasetName", "datasetTitle")
    if creator and publisher:
        return f"{creator} / {publisher}"
    return creator or publisher


def _first_text(source: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def image_record(
    usage_key: str,
    occurrence: Mapping[str, object],
    media: Mapping[str, object],
    *,
    rank: int,
    accepted_at: str,
) -> dict:
    image_url = _media_identifier(media)
    width, height = _image_dimensions(media)
    gbif_id = _first_text(occurrence, "gbifID", "key")
    return {
        IMAGE_SOURCE: "gbif",
        IMAGE_GBIF_ID: gbif_id,
        IMAGE_URL: image_url,
        IMAGE_THUMBNAIL_URL: image_url,
        IMAGE_SOURCE_URL: GBIF_OCCURRENCE_URL_TEMPLATE.format(gbif_id=gbif_id) if gbif_id else None,
        IMAGE_LICENSE: _candidate_license(occurrence, media),
        IMAGE_CREATOR: _first_text(media, "creator", "createdBy", "rightsHolder"),
        IMAGE_CREDIT: _credit(occurrence, media),
        IMAGE_PUBLISHER: _first_text(occurrence, "publisher", "datasetName", "datasetTitle"),
        IMAGE_WIDTH: width,
        IMAGE_HEIGHT: height,
        IMAGE_ACCEPTED_AT: accepted_at,
        IMAGE_RANK: rank,
    }


def _rejection_row(
    usage_key: str,
    occurrence: Mapping[str, object],
    media: Mapping[str, object],
    reason: str,
) -> dict:
    return {
        IMAGE_USAGE_KEY: usage_key,
        IMAGE_GBIF_ID: _first_text(occurrence, "gbifID", "key"),
        IMAGE_URL: _media_identifier(media),
        IMAGE_LICENSE: str(media.get("license") or occurrence.get("license") or ""),
        IMAGE_REJECTION_REASON: reason,
    }


def select_images_for_usage_key(
    usage_key: str,
    occurrences: Iterable[Mapping[str, object]],
    *,
    max_images: int = 2,
    validate_url: bool = True,
    session: requests.Session | None = None,
    accepted_at: str | None = None,
    delay_between_url_checks: float = 0,
    qa_counters: Counter | None = None,
) -> tuple[list[dict], list[dict]]:
    accepted_at = accepted_at or _utc_now()
    active_session = session or requests.Session()
    candidates: list[tuple[tuple, Mapping[str, object], Mapping[str, object]]] = []
    rejected: list[dict] = []

    for occurrence in occurrences:
        media_items = occurrence.get("media") or []
        if not isinstance(media_items, list):
            media_items = []
        for media in media_items:
            if not isinstance(media, Mapping):
                rejected.append({IMAGE_USAGE_KEY: usage_key, IMAGE_REJECTION_REASON: "invalid_media_record"})
                continue
            reason = _cheap_rejection_reason(usage_key, occurrence, media, validate_url=validate_url)
            if reason:
                rejected.append(_rejection_row(usage_key, occurrence, media, reason))
                continue
            candidates.append((_candidate_score(usage_key, occurrence, media), occurrence, media))

    candidates.sort(key=lambda item: item[0])
    records: list[dict] = []
    url_checks = 0
    skipped_lower_rank = 0
    for candidate_index, (_, occurrence, media) in enumerate(candidates):
        if len(records) >= max_images:
            skipped_lower_rank = len(candidates) - candidate_index
            break

        if validate_url:
            image_url = _media_identifier(media)
            if url_checks and delay_between_url_checks > 0:
                time.sleep(delay_between_url_checks)
            url_checks += 1
            validation = validate_image_url(active_session, image_url or "")
            if not validation.ok:
                rejected.append(
                    _rejection_row(
                        usage_key,
                        occurrence,
                        media,
                        validation.reason or "image_url_invalid",
                    )
                )
                continue

        records.append(
            image_record(
                usage_key,
                occurrence,
                media,
                rank=len(records) + 1,
                accepted_at=accepted_at,
            )
        )

    if skipped_lower_rank and qa_counters is not None:
        qa_counters["skipped_lower_rank_after_slots_filled"] += skipped_lower_rank
    return records, rejected


def _dwca_member_names(dwca: zipfile.ZipFile) -> set[str]:
    return {Path(name).name for name in dwca.namelist() if not name.endswith("/")}


def _dwca_member_path(dwca: zipfile.ZipFile, filename: str) -> str:
    for name in dwca.namelist():
        if Path(name).name == filename:
            return name
    raise ValueError(f"DWCA zip must contain {filename}")


def _dwca_delimiter(dwca: zipfile.ZipFile, filename: str) -> str:
    member_path = _dwca_member_path(dwca, filename)
    with dwca.open(member_path) as raw:
        header = raw.readline().decode("utf-8-sig")
    return "\t" if "\t" in header else ","


def _dwca_table_columns(dwca: zipfile.ZipFile, filename: str) -> set[str]:
    member_path = _dwca_member_path(dwca, filename)
    delimiter = _dwca_delimiter(dwca, filename)
    with dwca.open(member_path) as raw:
        return set(pd.read_csv(raw, sep=delimiter, nrows=0).columns.tolist())


def _stream_dwca_table_chunks(
    dwca_path: str | Path,
    filename: str,
    *,
    chunksize: int = DEFAULT_DWCA_CHUNKSIZE,
) -> Iterable[pd.DataFrame]:
    with zipfile.ZipFile(dwca_path) as dwca:
        member_path = _dwca_member_path(dwca, filename)
        delimiter = _dwca_delimiter(dwca, filename)
        with dwca.open(member_path) as raw:
            try:
                yield from pd.read_csv(
                    raw,
                    sep=delimiter,
                    dtype=str,
                    keep_default_na=False,
                    chunksize=chunksize,
                )
            except pd.errors.EmptyDataError:
                return


def _require_any_column(columns: set[str], groups: Iterable[tuple[str, ...]], table_name: str) -> None:
    missing = ["/".join(group) for group in groups if not any(column in columns for column in group)]
    if missing:
        raise ValueError(f"{table_name} missing required columns: {', '.join(missing)}")


def _dwca_row_id(row: Mapping[str, object]) -> str | None:
    return _first_text(row, "id", "gbifID", "occurrenceID")


def _dwca_media_core_id(row: Mapping[str, object]) -> str | None:
    return _first_text(row, "coreid", "coreId", "occurrenceID", "gbifID")


def _normalize_dwca_occurrence(row: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(row)
    if not normalized.get("gbifID"):
        normalized["gbifID"] = _first_text(row, "id", "occurrenceID")
    return normalized


def _normalize_dwca_media(row: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(row)
    if not normalized.get("type"):
        normalized["type"] = "StillImage"
    return normalized


def read_dwca_occurrences(
    dwca_path: str | Path,
    usage_keys: Iterable[str] | None = None,
    *,
    chunksize: int = DEFAULT_DWCA_CHUNKSIZE,
) -> dict[str, list[dict]]:
    requested_keys = None
    if usage_keys is not None:
        requested_keys = {key for key in (normalize_key(key) for key in usage_keys) if key is not None}

    with zipfile.ZipFile(dwca_path) as dwca:
        names = _dwca_member_names(dwca)
        for filename in (DWCA_OCCURRENCE_MEMBER, DWCA_MULTIMEDIA_MEMBER):
            if filename not in names:
                raise ValueError(f"DWCA zip must contain {filename}")

        occurrence_columns = _dwca_table_columns(dwca, DWCA_OCCURRENCE_MEMBER)
        multimedia_columns = _dwca_table_columns(dwca, DWCA_MULTIMEDIA_MEMBER)
    _require_any_column(
        occurrence_columns,
        (
            ("id", "gbifID", "occurrenceID"),
            ("taxonKey", "acceptedTaxonKey", "speciesKey"),
        ),
        "occurrence.txt",
    )
    _require_any_column(
        multimedia_columns,
        (
            ("coreid", "coreId", "gbifID", "occurrenceID"),
            ("identifier", "references", "source"),
        ),
        "multimedia.txt",
    )

    occurrences_by_id = {}
    for occurrence_chunk in _stream_dwca_table_chunks(
        dwca_path,
        DWCA_OCCURRENCE_MEMBER,
        chunksize=chunksize,
    ):
        for occurrence_row in occurrence_chunk.to_dict("records"):
            row_id = _dwca_row_id(occurrence_row)
            if row_id is None:
                continue
            candidate_usage_keys = {
                key
                for key in (
                    normalize_key(occurrence_row.get("acceptedTaxonKey")),
                    normalize_key(occurrence_row.get("taxonKey")),
                    normalize_key(occurrence_row.get("speciesKey")),
                )
                if key is not None
            }
            if requested_keys is not None and not (candidate_usage_keys & requested_keys):
                continue
            occurrences_by_id[row_id] = _normalize_dwca_occurrence(occurrence_row)

    grouped: dict[str, list[dict]] = defaultdict(list)
    occurrence_by_usage_and_id: dict[tuple[str, str], dict] = {}

    for multimedia_chunk in _stream_dwca_table_chunks(
        dwca_path,
        DWCA_MULTIMEDIA_MEMBER,
        chunksize=chunksize,
    ):
        for media_row in multimedia_chunk.to_dict("records"):
            occurrence_id = _dwca_media_core_id(media_row)
            if occurrence_id is None or occurrence_id not in occurrences_by_id:
                continue

            occurrence = occurrences_by_id[occurrence_id]
            candidate_usage_keys = {
                key
                for key in (
                    normalize_key(occurrence.get("acceptedTaxonKey")),
                    normalize_key(occurrence.get("taxonKey")),
                    normalize_key(occurrence.get("speciesKey")),
                )
                if key is not None
            }
            if requested_keys is not None:
                candidate_usage_keys &= requested_keys

            for usage_key in candidate_usage_keys:
                key = (usage_key, occurrence_id)
                occurrence_with_media = occurrence_by_usage_and_id.get(key)
                if occurrence_with_media is None:
                    occurrence_with_media = dict(occurrence)
                    occurrence_with_media["media"] = []
                    occurrence_by_usage_and_id[key] = occurrence_with_media
                    grouped[usage_key].append(occurrence_with_media)
                occurrence_with_media["media"].append(_normalize_dwca_media(media_row))

    return dict(grouped)


def fetch_gbif_occurrences(
    session: requests.Session,
    usage_key: str,
    *,
    limit: int = DEFAULT_LIMIT_PER_TAXON,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
) -> list[dict]:
    result = _request_with_retries(
        session,
        "get",
        GBIF_OCCURRENCE_SEARCH_URL,
        params={"taxonKey": usage_key, "mediaType": "StillImage", "limit": limit},
        timeout=timeout,
        retries=retries,
        backoff_factor=backoff_factor,
    )
    if result.transient_failure:
        raise requests.Timeout("transient GBIF API failure after retries")
    if result.response is None:
        raise result.exception or requests.RequestException("GBIF API request failed")
    response = result.response
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results", [])
    return results if isinstance(results, list) else []


def bucket_for_usage_key(usage_key: str | int, bucket_count: int = DEFAULT_BUCKET_COUNT) -> str:
    normalized = normalize_key(usage_key)
    if normalized is None or not normalized.isdigit():
        raise ValueError(f"usageKey must be numeric for image buckets: {usage_key!r}")
    return f"{int(normalized) % bucket_count:02d}"


def image_index_record(usage_key: str, records: list[dict]) -> dict:
    primary = records[0] if records else None
    secondary = records[1] if len(records) > 1 else None
    return {
        IMAGE_USAGE_KEY: int(usage_key) if usage_key.isdigit() else usage_key,
        "primaryImage": primary,
        "secondaryImage": secondary,
    }


def write_bucketed_index(
    image_index: Mapping[str, dict],
    output_dir: str | Path,
    *,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
) -> dict:
    output = Path(output_dir)
    bucket_dir = output / "buckets"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    buckets: dict[str, dict] = {f"{index:02d}": {} for index in range(bucket_count)}
    for usage_key, record in image_index.items():
        buckets[bucket_for_usage_key(usage_key, bucket_count)][str(usage_key)] = record

    manifest_entries = []
    for bucket, records in buckets.items():
        path = bucket_dir / f"{bucket}.json"
        path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_entries.append(
            {
                "bucket": bucket,
                "path": f"buckets/{bucket}.json",
                "plantCount": len(records),
            }
        )

    manifest = {
        "bucketCount": bucket_count,
        "bucketStrategy": f"usageKey % {bucket_count}",
        "buckets": manifest_entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_qa_report(
    usage_keys: Iterable[str],
    image_index: Mapping[str, dict],
    rejected: Iterable[Mapping[str, object]],
    *,
    qa_counters: Mapping[str, int] | None = None,
) -> dict:
    usage_key_list = list(usage_keys)
    rejected_rows = list(rejected)
    rejection_counter = Counter(str(row.get(IMAGE_REJECTION_REASON) or "unknown") for row in rejected_rows)
    qa_counters = qa_counters or {}
    accepted_records = [
        image
        for record in image_index.values()
        for image in (record.get("primaryImage"), record.get("secondaryImage"))
        if image
    ]
    return {
        "uniqueUsageKeysChecked": len(usage_key_list),
        "usageKeysWithAcceptedImage": len(image_index),
        "usageKeysWithoutAcceptedImage": len(usage_key_list) - len(image_index),
        "acceptedByLicense": dict(Counter(image.get(IMAGE_LICENSE) for image in accepted_records)),
        "acceptedBySourceDataset": dict(Counter(image.get(IMAGE_PUBLISHER) for image in accepted_records)),
        "rejectedByReason": dict(rejection_counter),
        "brokenUrlCount": rejection_counter.get("image_url_unreachable", 0),
        "lowResolutionCount": rejection_counter.get("low_resolution", 0),
        "missingLicenseCount": rejection_counter.get("disallowed_or_missing_license", 0),
        "specimenRejectedCount": rejection_counter.get("likely_specimen_image", 0),
        "skippedLowerRankCandidateCount": int(qa_counters.get("skipped_lower_rank_after_slots_filled") or 0),
    }


def write_reports(
    output_dir: str | Path,
    usage_keys: Iterable[str],
    image_index: Mapping[str, dict],
    rejected: Iterable[Mapping[str, object]],
    *,
    qa_counters: Mapping[str, int] | None = None,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rejected_rows = list(rejected)
    report = build_qa_report(usage_keys, image_index, rejected_rows, qa_counters=qa_counters)
    (output / "qa_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    review_rows = []
    for usage_key, record in image_index.items():
        for field in ("primaryImage", "secondaryImage"):
            image = record.get(field)
            if image:
                review_row = {IMAGE_USAGE_KEY: usage_key, "slot": field, **image}
                if image.get(IMAGE_WIDTH) is None or image.get(IMAGE_HEIGHT) is None:
                    review_row["manualReviewReason"] = "unknown_dimensions"
                review_rows.append(review_row)
    review_rows.extend(rejected_rows)
    pd.DataFrame(review_rows).to_csv(output / "manual_review.csv", index=False)
    return report


def build_gbif_image_index(
    usage_keys: Iterable[str],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    session: requests.Session | None = None,
    limit_per_taxon: int = DEFAULT_LIMIT_PER_TAXON,
    validate_urls: bool = True,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    delay_between_taxa: float = DEFAULT_DELAY_BETWEEN_TAXA,
    delay_between_url_checks: float = DEFAULT_DELAY_BETWEEN_URL_CHECKS,
    user_agent: str | None = None,
) -> dict:
    active_session = configure_http_session(session, user_agent=user_agent)
    keys = [key for key in (normalize_key(key) for key in usage_keys) if key is not None]
    image_index: dict[str, dict] = {}
    rejected: list[dict] = []
    qa_counters: Counter = Counter()
    accepted_at = _utc_now()

    for index, usage_key in enumerate(keys, start=1):
        if index > 1 and delay_between_taxa > 0:
            time.sleep(delay_between_taxa)
        LOGGER.info("Fetching GBIF images usageKey=%s progress=%s/%s", usage_key, index, len(keys))
        try:
            occurrences = fetch_gbif_occurrences(
                active_session,
                usage_key,
                limit=limit_per_taxon,
                retries=retries,
                backoff_factor=backoff_factor,
            )
        except requests.RequestException as exc:
            reason = "gbif_api_transient_failure" if _is_transient_exception(exc) else "gbif_api_error"
            rejected.append(
                {
                    IMAGE_USAGE_KEY: usage_key,
                    IMAGE_REJECTION_REASON: reason,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        records, rejected_rows = select_images_for_usage_key(
            usage_key,
            occurrences,
            validate_url=validate_urls,
            session=active_session,
            accepted_at=accepted_at,
            delay_between_url_checks=delay_between_url_checks,
            qa_counters=qa_counters,
        )
        rejected.extend(rejected_rows)
        if records:
            image_index[usage_key] = image_index_record(usage_key, records)

    write_bucketed_index(image_index, output_dir, bucket_count=bucket_count)
    report = write_reports(output_dir, keys, image_index, rejected, qa_counters=qa_counters)
    LOGGER.info(
        "GBIF image index complete accepted_usage_keys=%s checked_usage_keys=%s",
        report["usageKeysWithAcceptedImage"],
        report["uniqueUsageKeysChecked"],
    )
    return report


def build_gbif_image_index_from_dwca(
    usage_keys: Iterable[str],
    dwca_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    session: requests.Session | None = None,
    validate_urls: bool = True,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
    delay_between_url_checks: float = DEFAULT_DELAY_BETWEEN_URL_CHECKS,
    user_agent: str | None = None,
) -> dict:
    active_session = configure_http_session(session, user_agent=user_agent)
    keys = [key for key in (normalize_key(key) for key in usage_keys) if key is not None]
    occurrences_by_usage_key = read_dwca_occurrences(dwca_path, keys)
    image_index: dict[str, dict] = {}
    rejected: list[dict] = []
    qa_counters: Counter = Counter()
    accepted_at = _utc_now()

    for usage_key in keys:
        records, rejected_rows = select_images_for_usage_key(
            usage_key,
            occurrences_by_usage_key.get(usage_key, []),
            validate_url=validate_urls,
            session=active_session,
            accepted_at=accepted_at,
            delay_between_url_checks=delay_between_url_checks,
            qa_counters=qa_counters,
        )
        rejected.extend(rejected_rows)
        if records:
            image_index[usage_key] = image_index_record(usage_key, records)

    write_bucketed_index(image_index, output_dir, bucket_count=bucket_count)
    report = write_reports(output_dir, keys, image_index, rejected, qa_counters=qa_counters)
    LOGGER.info(
        "GBIF DWCA image index complete accepted_usage_keys=%s checked_usage_keys=%s",
        report["usageKeysWithAcceptedImage"],
        report["uniqueUsageKeysChecked"],
    )
    return report


def summarize_bucket_sizes(manifest: Mapping[str, object]) -> dict[str, int]:
    counts = defaultdict(int)
    for entry in manifest.get("buckets", []):
        if isinstance(entry, Mapping):
            counts[str(entry.get("bucket"))] = int(entry.get("plantCount") or 0)
    return dict(counts)
