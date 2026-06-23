from strategy_lab.schema import validate_strategy_proposal

from research_lab.proposal_builder import build_proposals, hypothesis_to_proposal


def _hypothesis(family="volatility_regime_filter", regime="high_volatility"):
    return {
        "hypothesis_id": "hyp_unit",
        "source_paper_id": "paper_unit",
        "title": "Unit hypothesis",
        "market": "crypto",
        "regime": regime,
        "strategy_family": family,
        "entry_idea": "entry",
        "exit_idea": "exit",
        "risk_idea": "risk",
        "expected_failure_modes": ["overfit"],
        "testable_parameters": {
            "atr_period": [14],
            "max_atr_pct": [2.5],
            "vol_zscore_window": [100],
            "vol_zscore_limit": [1.5],
            "mean_window": [20],
            "entry_deviation_pct": [0.6],
            "exit_deviation_pct": [0.0],
            "max_hold_bars": [12],
        },
        "confidence": 0.5,
        "citations": [],
    }


def test_volatility_hypothesis_builds_valid_strategy_proposal():
    proposal = hypothesis_to_proposal(_hypothesis())

    validated = validate_strategy_proposal(proposal)
    assert validated.name == "generated_volatility_regime_filter_v1"
    assert validated.market == "crypto"
    assert proposal["parameters"]["source_hypothesis_id"] == "hyp_unit"


def test_mean_reversion_hypothesis_builds_valid_strategy_proposal():
    proposal = hypothesis_to_proposal(_hypothesis("mean_reversion", "range"))

    validated = validate_strategy_proposal(proposal)
    assert validated.strategy_type == "mean_reversion"
    assert proposal["parameters"]["mean_window"] == 20


def test_build_proposals_dedupes_by_name():
    rows = build_proposals([_hypothesis(), _hypothesis()])

    assert len(rows) == 1
