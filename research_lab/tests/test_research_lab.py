import json

from research_lab.paper_scout import build_arxiv_query, parse_arxiv_response
from research_lab.schema import PaperCandidate, normalize_keywords
from research_lab.store import PaperStore


ARXIV_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <updated>2024-01-01T00:00:00Z</updated>
    <published>2024-01-01T00:00:00Z</published>
    <title>Crypto Mean Reversion with Volatility Regime Filters</title>
    <summary>We study trading signals for crypto markets using volatility regime detection.</summary>
    <author><name>Alice Quant</name></author>
  </entry>
</feed>
"""


def test_normalize_keywords_dedupes_lowercase():
    assert normalize_keywords(["Crypto", " crypto ", "Grid"]) == ["crypto", "grid"]


def test_build_arxiv_query_quotes_terms():
    query = build_arxiv_query(["crypto mean reversion", "order flow"])

    assert 'all:"crypto mean reversion"' in query
    assert ' OR ' in query


def test_parse_arxiv_response_returns_candidates():
    rows = parse_arxiv_response(ARXIV_SAMPLE, ["crypto", "volatility regime"])

    assert len(rows) == 1
    assert rows[0].source == "arxiv"
    assert rows[0].paper_id == "2401.00001v1"
    assert rows[0].score > 0
    assert "crypto" in rows[0].keywords


def test_paper_store_upserts_by_paper_id(tmp_path):
    store = PaperStore(tmp_path / "papers.jsonl")
    first = PaperCandidate(
        paper_id="p1",
        title="A",
        source="unit",
        url="https://example.test/a",
        score=1,
    )
    second = PaperCandidate(
        paper_id="p1",
        title="A updated",
        source="unit",
        url="https://example.test/a",
        score=2,
    )

    rows = store.upsert_many([first])
    rows = store.upsert_many([second])

    assert len(rows) == 1
    assert rows[0].title == "A updated"
    assert json.loads(store.path.read_text().splitlines()[0])["score"] == 2
