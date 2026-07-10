from __future__ import annotations

import unittest

from scraper.page_parser import parse_identity, parse_sections, scrape_page

from helpers import PAGE


class PageParserTests(unittest.TestCase):
    def test_synonym_parsing_preserves_infraspecific_names_and_ignores_other_fields(self):
        html = """
        <html><h2>Example plant (New name)</h2>
        <p><strong>Synonym(s):</strong> Old name var. minor; Other name subsp. major
        <strong>Family:</strong> Notasynonym plantus</p></html>
        """
        identity = parse_identity(html)
        self.assertEqual(identity["synonyms"], ["Old name var. minor", "Other name subsp. major"])

    def test_scrape_page_reuses_supplied_html(self):
        class FailingClient:
            def get(self, url):
                raise AssertionError("scrape_page should not fetch when html is supplied")

        page = scrape_page(FailingClient(), "https://example.test/result.php?id_plant=X", PAGE)
        self.assertEqual(page["lbj_url"], "https://example.test/result.php?id_plant=X")
        self.assertEqual(page["identity"]["scientific_name"], "Trillium grandiflorum")

    def test_parse_sections(self):
        sections = parse_sections(PAGE)
        self.assertEqual(sections["Plant Characteristics"]["Duration"], "Perennial")
        self.assertEqual(sections["Growing Conditions"]["Water Use"], "Medium")


if __name__ == "__main__":
    unittest.main()
