# Research Lab Digest

Digest converts stored paper metadata into testable strategy hypotheses.

```bash
python3 -m research_lab.run_digest \
  --store research_lab/data/paper_store.jsonl \
  --hypotheses-dir research_lab/hypotheses \
  --out research_lab/reports/latest_hypotheses.json
```

Current digest is rule-based. It extracts:

- market/regime assumption
- strategy family
- entry/exit/risk ideas
- expected failure modes
- testable parameter ranges
- citation back to the source paper

The output is not executable strategy code. It must be converted into a Strategy
Lab proposal and pass backtest/optimizer/walk-forward gates first.

