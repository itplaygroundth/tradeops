from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List

from .schema import PaperCandidate, normalize_keywords


ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
QFIN_FILTER = "(cat:q-fin.TR OR cat:q-fin.ST OR cat:q-fin.PM OR cat:q-fin.RM OR cat:q-fin.CP)"


def build_arxiv_query(keywords: List[str]) -> str:
    terms = normalize_keywords(keywords)
    if not terms:
        raise ValueError("at least one keyword is required")
    keyword_query = " OR ".join(f'all:"{term}"' for term in terms)
    return f"{QFIN_FILTER} AND ({keyword_query})"


def search_arxiv(keywords: List[str], max_results: int = 10, timeout: int = 20) -> List[PaperCandidate]:
    query = build_arxiv_query(keywords)
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max(1, min(int(max_results), 50)),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    with urllib.request.urlopen(f"{ARXIV_API}?{params}", timeout=timeout) as response:
        xml_text = response.read().decode("utf-8", "ignore")
    return parse_arxiv_response(xml_text, keywords)


def parse_arxiv_response(xml_text: str, keywords: List[str]) -> List[PaperCandidate]:
    root = ET.fromstring(xml_text)
    out = []
    normalized = normalize_keywords(keywords)
    for entry in root.findall("atom:entry", ARXIV_NS):
        paper_id = _text(entry, "atom:id")
        title = _clean(_text(entry, "atom:title"))
        abstract = _clean(_text(entry, "atom:summary"))
        authors = [
            _clean(_text(author, "atom:name"))
            for author in entry.findall("atom:author", ARXIV_NS)
        ]
        published_at = _text(entry, "atom:published")
        url = paper_id
        matched = _matched_keywords(title, abstract, normalized)
        candidate = PaperCandidate(
            paper_id=paper_id.rsplit("/", 1)[-1],
            title=title,
            source="arxiv",
            url=url,
            abstract=abstract,
            authors=[author for author in authors if author],
            published_at=published_at,
            keywords=matched or normalized,
            score=_score_candidate(title, abstract, matched),
            raw={"arxiv_id": paper_id},
        )
        if candidate.score > 0:
            out.append(candidate)
    return out


def _text(node: ET.Element, path: str) -> str:
    item = node.find(path, ARXIV_NS)
    return item.text if item is not None and item.text else ""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _matched_keywords(title: str, abstract: str, keywords: List[str]) -> List[str]:
    haystack = f"{title} {abstract}".lower()
    return [keyword for keyword in keywords if keyword in haystack]


def _score_candidate(title: str, abstract: str, matched: List[str]) -> float:
    score = float(len(matched) * 10)
    text = f"{title} {abstract}".lower()
    bonus_terms = {
        "trading": 3,
        "market": 2,
        "volatility": 3,
        "regime": 3,
        "mean reversion": 4,
        "order flow": 4,
        "grid": 2,
        "crypto": 3,
    }
    for term, bonus in bonus_terms.items():
        if term in text:
            score += bonus
    return round(score, 3)
