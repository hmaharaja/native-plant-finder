from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString

from dataset_columns import LBJ_URL

SCIENTIFIC_NAME_PATTERN = re.compile(
    r"\b[A-Z][a-z-]+\s+[a-z][a-z-]+(?:\s+(?:var\.|subsp\.)\s+[a-z-]+)?\b"
)


def _fields(section) -> dict[str, str]:
    result: dict[str, str] = {}
    for strong in section.find_all("strong"):
        key = strong.get_text(" ", strip=True).rstrip(":")
        parts: list[str] = []
        node = strong.next_sibling
        while node is not None and getattr(node, "name", None) != "strong":
            text = str(node).strip() if isinstance(node, NavigableString) else node.get_text(" ", strip=True)
            if text:
                parts.append(text)
            node = node.next_sibling
        result[key] = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return result


def parse_sections(html: str) -> dict[str, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    sections: dict[str, dict[str, str]] = {}
    for section in soup.find_all("div", class_="section"):
        heading = section.find(["h3", "h4"])
        if heading:
            sections[heading.get_text(" ", strip=True)] = _fields(section)
    return sections


def _field_text_after(label) -> str:
    parts: list[str] = []
    node = label.next_sibling
    while node is not None and getattr(node, "name", None) != "strong":
        text = str(node).strip() if isinstance(node, NavigableString) else node.get_text(" ", strip=True)
        if text:
            parts.append(text)
        node = node.next_sibling
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _scientific_name_from_text(text: str) -> str | None:
    for parenthetical in re.findall(r"\(([^()]*)\)", text):
        match = SCIENTIFIC_NAME_PATTERN.search(parenthetical)
        if match:
            return match.group(0)
    match = SCIENTIFIC_NAME_PATTERN.search(text)
    return match.group(0) if match else None


def parse_identity(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    scientific = None
    for selector in ("h2", "h1", ".scientific-name", "i"):
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            scientific = _scientific_name_from_text(text)
            if scientific:
                break
    synonyms: list[str] = []
    for label in soup.find_all("strong"):
        if "synonym" in label.get_text(strip=True).casefold():
            value = _field_text_after(label)
            synonyms.extend(match.group(0) for match in SCIENTIFIC_NAME_PATTERN.finditer(value))
    return {"scientific_name": scientific, "synonyms": list(dict.fromkeys(synonyms))}


def scrape_page(client, url: str, html: str | None = None) -> dict[str, object]:
    if html is None:
        response = client.get(url)
        html = response.text
        url = response.url
    return {LBJ_URL: url, "sections": parse_sections(html), "identity": parse_identity(html)}
