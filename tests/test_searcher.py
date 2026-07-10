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
