# Research Lab Proposal Builder

Convert Research Lab hypotheses into Strategy Lab proposal JSON files.

```bash
python3 -m research_lab.run_proposal_builder \
  --hypotheses-dir research_lab/hypotheses \
  --out-dir strategy_lab/strategies/generated \
  --report research_lab/reports/latest_generated_proposals.json
```

The builder validates every generated proposal with `strategy_lab.schema`.
Generated files remain `draft` and must pass Strategy Lab backtest, optimizer,
and walk-forward gates before they can be considered for execution.

