# TradeOps Research Lab

Research Lab discovers paper metadata and stores source candidates before any
idea is converted into a strategy proposal.

Run a scout search:

```bash
python3 -m research_lab.run_scout \
  --keywords-file research_lab/config/keywords.json \
  --max-results 10 \
  --store research_lab/data/paper_store.jsonl \
  --out research_lab/reports/latest_papers.json
```

Phase 1 is metadata-only. It does not edit strategy code and does not touch the
trading engines.

