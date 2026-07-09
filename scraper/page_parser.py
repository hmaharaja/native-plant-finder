from __future__ import annotations

import re
from bs4 import BeautifulSoup, NavigableString


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


def parse_identity(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    scientific = None
    for selector in ("h2", "h1", ".scientific-name", "i"):
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            match = re.search(r"([A-Z][a-z-]+\s+[a-z][a-z-]+(?:\s+(?:var\.|subsp\.)\s+[a-z-]+)?)", text)
            if match:
                scientific = match.group(1)
                break
    synonyms: list[str] = []
    for label in soup.find_all("strong"):
        if "synonym" in label.get_text(strip=True).casefold():
            value = label.parent.get_text(" ", strip=True)
            synonyms.extend(re.findall(r"[A-Z][a-z-]+\s+[a-z][a-z-]+", value))
    return {"scientific_name": scientific, "synonyms": list(dict.fromkeys(synonyms))}


def scrape_page(client, url: str) -> dict[str, object]:
    response = client.get(url)
    return {"lbj_url": response.url, "sections": parse_sections(response.text),
            "identity": parse_identity(response.text)}
