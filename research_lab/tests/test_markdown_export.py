from research_lab.markdown_export import paper_to_markdown, papers_to_markdown
from research_lab.schema import PaperCandidate


def test_paper_to_markdown_is_compact_and_cited():
    paper = PaperCandidate(
        paper_id="p1",
        title="Crypto Volatility Regime",
        source="unit",
        url="https://example.test/p1",
        abstract="Volatility " * 200,
        keywords=["volatility"],
        score=12,
    )

    md = paper_to_markdown(paper, abstract_chars=80)

    assert "## Crypto Volatility Regime" in md
    assert "- id: `p1`" in md
    assert "https://example.test/p1" in md
    assert len(md) < 900
    assert "volatility-regime" in md


def test_papers_to_markdown_limits_rows():
    papers = [
        PaperCandidate(
            paper_id=f"p{i}",
            title=f"Paper {i}",
            source="unit",
            url=f"https://example.test/{i}",
            score=i,
        )
        for i in range(3)
    ]

    md = papers_to_markdown(papers, limit=2)

    assert "papers: 2" in md
    assert "Paper 0" in md
    assert "Paper 1" in md
    assert "Paper 2" not in md
