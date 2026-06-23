from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List

from .hypothesis import StrategyHypothesis
from .schema import PaperCandidate


def digest_paper(paper: PaperCandidate) -> StrategyHypothesis:
    text = f"{paper.title} {paper.abstract}".lower()
    regime = _infer_regime(text)
    family = _infer_strategy_family(text, regime)
    params = _parameters_for(family, regime)
    failure_modes = _failure_modes_for(family, regime)
    hypothesis_id = _stable_id(paper.paper_id, family, regime)
    confidence = _confidence(paper.score, family, regime)
    return StrategyHypothesis(
        hypothesis_id=hypothesis_id,
        source_paper_id=paper.paper_id,
        title=f"{family} hypothesis from {paper.title}",
        market="crypto" if "crypto" in text or "bitcoin" in text or "ethereum" in text else "multi_asset",
        regime=regime,
        strategy_family=family,
        entry_idea=_entry_idea_for(family, regime),
        exit_idea=_exit_idea_for(family, regime),
        risk_idea=_risk_idea_for(family, regime),
        expected_failure_modes=failure_modes,
        testable_parameters=params,
        confidence=confidence,
        citations=[{"paper_id": paper.paper_id, "title": paper.title, "url": paper.url}],
    )


def digest_papers(papers: Iterable[PaperCandidate]) -> List[StrategyHypothesis]:
    return [digest_paper(paper) for paper in papers]


def write_hypotheses(hypotheses: Iterable[StrategyHypothesis], directory: str | Path) -> List[Path]:
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for hypothesis in hypotheses:
        path = out_dir / f"{hypothesis.hypothesis_id}.json"
        path.write_text(json.dumps(hypothesis.to_dict(), indent=2, sort_keys=True))
        paths.append(path)
    return paths


def _infer_regime(text: str) -> str:
    if "microstructure" in text or "order book" in text or "market impact" in text or "adverse selection" in text:
        return "market_microstructure"
    if "volatility" in text or "crash" in text or "flash crash" in text:
        return "high_volatility"
    if "trend" in text or "momentum" in text:
        return "trend"
    if "mean reversion" in text or "range" in text:
        return "range"
    return "unknown"


def _infer_strategy_family(text: str, regime: str) -> str:
    if "mean reversion" in text:
        return "mean_reversion"
    if "order book" in text or "order flow" in text or "market impact" in text or "adverse selection" in text:
        return "order_flow_liquidity"
    if "volatility" in text or "surface" in text or regime == "high_volatility":
        return "volatility_regime_filter"
    if "trend" in text or "momentum" in text:
        return "trend_risk_model"
    return "research_filter"


def _parameters_for(family: str, regime: str) -> Dict[str, List]:
    if family == "mean_reversion":
        return {
            "mean_window": [14, 20, 34],
            "entry_deviation_pct": [0.4, 0.6, 0.9],
            "exit_deviation_pct": [-0.1, 0.0, 0.15],
            "max_hold_bars": [8, 12, 20],
        }
    if family == "order_flow_liquidity":
        return {
            "imbalance_window": [10, 20, 40],
            "min_depth_imbalance": [0.15, 0.25, 0.35],
            "max_spread_bps": [3, 5, 8],
            "max_hold_bars": [4, 8, 12],
        }
    if family == "volatility_regime_filter":
        return {
            "atr_period": [14, 21],
            "max_atr_pct": [1.5, 2.5, 4.0],
            "vol_zscore_window": [50, 100],
            "vol_zscore_limit": [1.0, 1.5, 2.0],
        }
    if family == "trend_risk_model":
        return {
            "trend_window": [20, 50, 100],
            "risk_scale": [0.25, 0.5, 1.0],
            "volatility_cap": [1.5, 2.5, 4.0],
        }
    return {"lookback": [20, 50, 100], "threshold": [0.5, 1.0, 1.5]}


def _entry_idea_for(family: str, regime: str) -> str:
    if family == "mean_reversion":
        return "Enter when price deviates below a rolling mean in a confirmed range regime."
    if family == "order_flow_liquidity":
        return "Enter only when liquidity imbalance supports the direction and spread is below cap."
    if family == "volatility_regime_filter":
        return "Use volatility anomaly as a filter; avoid entries during unstable high-error regimes."
    if family == "trend_risk_model":
        return "Enter trend strategies only when trend strength is positive and volatility risk is acceptable."
    return "Use paper signal as a filter candidate; no direct entry until backtested."


def _exit_idea_for(family: str, regime: str) -> str:
    if family == "mean_reversion":
        return "Exit at mean reversion, time stop, or regime flip to trend."
    if family == "order_flow_liquidity":
        return "Exit when imbalance fades, spread expands, or adverse selection risk rises."
    if family == "volatility_regime_filter":
        return "Exit or block entries when volatility regime moves outside calibrated bounds."
    return "Exit on signal decay, risk stop, or time stop."


def _risk_idea_for(family: str, regime: str) -> str:
    if family == "mean_reversion":
        return "Cap basket exposure and disable the model during breakout or expanding ATR."
    if family == "order_flow_liquidity":
        return "Reduce size when spread, slippage, or permanent impact proxy rises."
    if family == "volatility_regime_filter":
        return "Use as a global risk throttle for strategies during high-volatility regimes."
    return "Use conservative sizing until walk-forward validates the edge."


def _failure_modes_for(family: str, regime: str) -> List[str]:
    if family == "mean_reversion":
        return ["range breaks into trend", "grid exposure accumulates", "volatility expands faster than exit"]
    if family == "order_flow_liquidity":
        return ["order book spoofing/noise", "execution cost exceeds edge", "liquidity disappears"]
    if family == "volatility_regime_filter":
        return ["volatility model overfits", "regime shift not detected quickly", "options-derived signal unavailable"]
    return ["overfit backtest", "insufficient trades", "market regime mismatch"]


def _confidence(score: float, family: str, regime: str) -> float:
    base = min(0.8, max(0.1, float(score) / 40.0))
    if family in {"mean_reversion", "volatility_regime_filter", "order_flow_liquidity"}:
        base += 0.1
    if regime == "unknown":
        base -= 0.1
    return round(max(0.05, min(base, 0.95)), 3)


def _stable_id(paper_id: str, family: str, regime: str) -> str:
    digest = hashlib.sha1(f"{paper_id}:{family}:{regime}".encode()).hexdigest()[:10]
    return f"hyp_{digest}"

