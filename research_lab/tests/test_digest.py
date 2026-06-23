from research_lab.digest import digest_paper, digest_papers, write_hypotheses
from research_lab.schema import PaperCandidate


def test_digest_volatility_paper_to_hypothesis(tmp_path):
    paper = PaperCandidate(
        paper_id="p1",
        title="Crypto Volatility Regime Filters",
        source="unit",
        url="https://example.test/p1",
        abstract="We study volatility regime detection in crypto markets.",
        keywords=["volatility"],
        score=20,
    )

    hypothesis = digest_paper(paper)

    assert hypothesis.source_paper_id == "p1"
    assert hypothesis.regime == "high_volatility"
    assert hypothesis.strategy_family == "volatility_regime_filter"
    assert hypothesis.confidence > 0
    assert "atr_period" in hypothesis.testable_parameters

    paths = write_hypotheses([hypothesis], tmp_path)
    assert paths[0].exists()


def test_digest_order_flow_paper_to_liquidity_hypothesis():
    paper = PaperCandidate(
        paper_id="p2",
        title="Market Impact and Adverse Selection on a Limit Order Book",
        source="unit",
        url="https://example.test/p2",
        abstract="Order book liquidity and adverse selection affect execution costs.",
        keywords=["trading"],
        score=18,
    )

    hypothesis = digest_paper(paper)

    assert hypothesis.regime == "market_microstructure"
    assert hypothesis.strategy_family == "order_flow_liquidity"
    assert "max_spread_bps" in hypothesis.testable_parameters


def test_digest_papers_returns_list():
    paper = PaperCandidate(
        paper_id="p3",
        title="Mean Reversion Trading",
        source="unit",
        url="https://example.test/p3",
        abstract="Mean reversion works in range markets.",
        score=15,
    )

    rows = digest_papers([paper])

    assert len(rows) == 1
    assert rows[0].strategy_family == "mean_reversion"
