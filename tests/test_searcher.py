from __future__ import annotations

import unittest
from unittest.mock import patch

from scraper.models import Candidate, MatchStatus
from scraper.searcher import choose_verified, find_match, parse_search_response

from helpers import PAGE


class SearcherTests(unittest.TestCase):
    def test_redirect_and_result_list(self):
        direct = parse_search_response(
            "https://www.wildflower.org/plants/result.php?id_plant=TRGR4", PAGE
        )
        self.assertTrue(direct[0].direct_redirect)
        self.assertEqual(direct[0].scientific_name, "Trillium grandiflorum")
        self.assertIn("<html>", direct[0].page_html)
        match = choose_verified(direct, "Trillium grandiflorum")
        self.assertNotIn("page_html", match.as_dict()["candidate"])

        html = '<a href="result.php?id_plant=SOCA6">Canada Goldenrod (Solidago canadensis)</a>'
        candidates = parse_search_response("https://www.wildflower.org/plants/search.php", html)
        self.assertEqual(candidates[0].scientific_name, "Solidago canadensis")
        self.assertEqual(choose_verified(candidates, "Solidago canadensis").status, MatchStatus.MATCHED)

    def test_conservative_and_synonym_matching(self):
        fuzzy = Candidate("x", scientific_name="Solidago canadensis var. canadensis")
        self.assertEqual(choose_verified([fuzzy], "Solidago canadensis").status, MatchStatus.UNMATCHED)

        synonym = Candidate("x", scientific_name="New name", synonyms=["Old name"])
        self.assertEqual(choose_verified([synonym], "Old name").status, MatchStatus.SYNONYM_MATCHED)

    def test_vernacular_redirect_allows_same_epithet_taxonomy_update(self):
        candidate = Candidate(
            "https://www.wildflower.org/plants/result.php?id_plant=CEMU2",
            scientific_name="Centaurium muehlenbergii",
            direct_redirect=True,
        )

        result = choose_verified(
            [candidate],
            "Zeltnera muehlenbergii",
            allow_vernacular_redirect=True,
        )

        self.assertEqual(result.status, MatchStatus.SYNONYM_MATCHED)
        self.assertEqual(result.evidence["matched_field"], "specific_epithet")

    def test_vernacular_redirect_allows_genus_only_canonical(self):
        candidate = Candidate(
            "https://www.wildflower.org/plants/result.php?id_plant=GABR6",
            scientific_name="Galium brevipes",
            direct_redirect=True,
        )

        result = choose_verified([candidate], "Galium", allow_vernacular_redirect=True)

        self.assertEqual(result.status, MatchStatus.MATCHED)
        self.assertEqual(result.evidence["matched_field"], "genus")

    def test_vernacular_redirect_rejects_different_genus_and_epithet(self):
        candidate = Candidate(
            "https://www.wildflower.org/plants/result.php?id_plant=MECA",
            scientific_name="Meconella californica",
            direct_redirect=True,
        )

        result = choose_verified(
            [candidate],
            "Mentha canadensis",
            allow_vernacular_redirect=True,
        )

        self.assertEqual(result.status, MatchStatus.UNMATCHED)

    def test_multiple_lbj_varieties_can_match_same_species_level_name(self):
        candidates = [
            Candidate(
                "https://www.wildflower.org/plants/result.php?id_plant=PYINI",
                display_name="Pycnanthemum incanum var. incanum",
                scientific_name="Pycnanthemum incanum",
            ),
            Candidate(
                "https://www.wildflower.org/plants/result.php?id_plant=PYINP",
                display_name="Pycnanthemum incanum var. puberulum",
                scientific_name="Pycnanthemum incanum",
            ),
        ]

        result = choose_verified(candidates, "Pycnanthemum incanum")

        self.assertEqual(result.status, MatchStatus.MATCHED)
        self.assertEqual(result.candidate.url, candidates[0].url)
        self.assertEqual(result.evidence["matching_candidate_count"], 2)

    def test_conflicting_verified_candidates_are_ambiguous(self):
        exact = Candidate("exact", scientific_name="Old name")
        synonym = Candidate("synonym", scientific_name="New name", synonyms=["Old name"])
        result = choose_verified([exact, synonym], "Old name")
        self.assertEqual(result.status, MatchStatus.AMBIGUOUS)
        self.assertEqual(result.reason, "conflicting verified candidates")

    def test_falls_back_to_canonical_search_after_unverified_vernacular(self):
        calls: list[str] = []

        def fake_search(client, query):
            calls.append(query)
            if query == "common name":
                return [Candidate("vernacular-result", scientific_name="Different plant")]
            return [Candidate("canonical-result", scientific_name="Target species")]

        class FakeClient:
            class Response:
                text = "<html><h2>Different plant</h2></html>"

            def get(self, url):
                return self.Response()

        with patch("scraper.searcher.search", fake_search):
            result = find_match(FakeClient(), "Target species", "common name")

        self.assertEqual(calls, ["common name", "Target species"])
        self.assertEqual(result.status, MatchStatus.MATCHED)
        self.assertEqual(result.candidate.url, "canonical-result")
        self.assertEqual(result.evidence["query_kind"], "canonical")


if __name__ == "__main__":
    unittest.main()
