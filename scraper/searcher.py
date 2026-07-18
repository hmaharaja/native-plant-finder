from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .http import HttpClient
from .models import Candidate, Match, MatchStatus
from .page_parser import parse_identity

LBJ_SEARCH_URL = "https://www.wildflower.org/plants/search.php"
LBJ_BASE_URL = "https://www.wildflower.org/plants/"
RESULT_MARKER = "result.php?id_plant="


def normalize_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value or "")).casefold().strip()


def _name_parts(value: str | None) -> list[str]:
    return normalize_name(value).split()


def _direct_redirect_same_epithet(candidate: Candidate, canonical_name: str) -> bool:
    candidate_parts = _name_parts(candidate.scientific_name)
    target_parts = _name_parts(canonical_name)
    return (
        candidate.direct_redirect
        and len(candidate_parts) >= 2
        and len(target_parts) >= 2
        and candidate_parts[1] == target_parts[1]
    )


def _direct_redirect_same_genus(candidate: Candidate, canonical_name: str) -> bool:
    candidate_parts = _name_parts(candidate.scientific_name)
    target_parts = _name_parts(canonical_name)
    return (
        candidate.direct_redirect
        and len(candidate_parts) >= 2
        and len(target_parts) == 1
        and candidate_parts[0] == target_parts[0]
    )


def _names_from_text(text: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", " ", text).strip()
    parenthetical = re.search(r"\(([^()]*)\)\s*$", text)
    if parenthetical:
        return text[: parenthetical.start()].strip(" ,-") or None, parenthetical.group(1).strip()
    return None, text or None


def parse_search_response(url: str, html: str) -> list[Candidate]:
    if RESULT_MARKER in url:
        identity = parse_identity(html)
        return [
            Candidate(
                url=url,
                scientific_name=identity["scientific_name"],
                synonyms=identity["synonyms"],
                direct_redirect=True,
                page_html=html,
            )
        ]
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Candidate] = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if RESULT_MARKER not in href:
            continue
        absolute = urljoin(LBJ_BASE_URL, href)
        text = link.get_text(" ", strip=True)
        common, scientific = _names_from_text(text)
        found.setdefault(
            absolute,
            Candidate(
                url=absolute,
                display_name=text or None,
                scientific_name=scientific,
                common_name=common,
            ),
        )
    return list(found.values())


def search(client: HttpClient, query: str) -> list[Candidate]:
    response = client.post(
        LBJ_SEARCH_URL,
        data={"search_field": query, "newsearch": "true", "demo": ""},
        allow_redirects=True,
    )
    return parse_search_response(response.url, response.text)


def choose_verified(
    candidates: list[Candidate],
    canonical_name: str,
    *,
    allow_vernacular_redirect: bool = False,
) -> Match:
    target = normalize_name(canonical_name)
    exact = [c for c in candidates if normalize_name(c.scientific_name) == target]
    synonyms = [c for c in candidates if target in map(normalize_name, c.synonyms)]
    if len(exact) > 1 and len({normalize_name(c.scientific_name) for c in exact}) == 1:
        return Match(
            MatchStatus.MATCHED,
            exact[0],
            "multiple LBJ candidates share the exact species-level scientific name",
            {
                "matched_field": "scientific_name",
                "matched_value": exact[0].scientific_name,
                "matching_candidate_count": len(exact),
            },
            candidates,
        )
    verified = {candidate.url for candidate in exact + synonyms}
    if len(verified) > 1:
        return Match(MatchStatus.AMBIGUOUS, reason="conflicting verified candidates", candidates=candidates)
    if len(exact) == 1:
        return Match(MatchStatus.MATCHED, exact[0], "exact scientific-name match",
                     {"matched_field": "scientific_name", "matched_value": exact[0].scientific_name}, candidates)
    if len(synonyms) == 1 and not exact:
        return Match(MatchStatus.SYNONYM_MATCHED, synonyms[0], "explicit synonym match",
                     {"matched_field": "synonym", "matched_value": canonical_name}, candidates)
    if len(exact) > 1 or len(synonyms) > 1:
        return Match(MatchStatus.AMBIGUOUS, reason="multiple verified candidates", candidates=candidates)
    if allow_vernacular_redirect:
        same_epithet = [c for c in candidates if _direct_redirect_same_epithet(c, canonical_name)]
        if len(same_epithet) == 1:
            return Match(
                MatchStatus.SYNONYM_MATCHED,
                same_epithet[0],
                "vernacular direct redirect with matching specific epithet",
                {
                    "matched_field": "specific_epithet",
                    "matched_value": same_epithet[0].scientific_name,
                    "canonical_name": canonical_name,
                },
                candidates,
            )
        same_genus = [c for c in candidates if _direct_redirect_same_genus(c, canonical_name)]
        if len(same_genus) == 1:
            return Match(
                MatchStatus.MATCHED,
                same_genus[0],
                "vernacular direct redirect within canonical genus",
                {
                    "matched_field": "genus",
                    "matched_value": same_genus[0].scientific_name,
                    "canonical_name": canonical_name,
                },
                candidates,
            )
    return Match(MatchStatus.UNMATCHED, reason="no exact scientific-name or explicit synonym match",
                 candidates=candidates)


def find_match(client: HttpClient, canonical_name: str, vernacular_name: str | None) -> Match:
    queries = [q for q in (vernacular_name, canonical_name) if q]
    all_candidates: list[Candidate] = []
    for index, query in enumerate(queries):
        candidates = search(client, query)
        all_candidates.extend(candidates)
        allow_vernacular_redirect = index == 0 and bool(vernacular_name)
        result = choose_verified(
            candidates,
            canonical_name,
            allow_vernacular_redirect=allow_vernacular_redirect,
        )
        if result.status == MatchStatus.UNMATCHED and candidates:
            # Search listings do not expose synonyms. Inspect result pages only
            # when the cheap exact-name check could not verify any candidate.
            for candidate in candidates:
                identity = parse_identity(client.get(candidate.url).text)
                candidate.scientific_name = identity["scientific_name"] or candidate.scientific_name
                candidate.synonyms = identity["synonyms"]
            result = choose_verified(
                candidates,
                canonical_name,
                allow_vernacular_redirect=allow_vernacular_redirect,
            )
        result.evidence["query"] = query
        result.evidence["query_kind"] = "vernacular" if index == 0 and vernacular_name else "canonical"
        if result.status in (MatchStatus.MATCHED, MatchStatus.SYNONYM_MATCHED, MatchStatus.AMBIGUOUS):
            return result
        # Canonical fallback is allowed only after an unverified vernacular result.
    return Match(MatchStatus.UNMATCHED, reason="no verified LBJ match", candidates=all_candidates,
                 evidence={"queries": queries})
