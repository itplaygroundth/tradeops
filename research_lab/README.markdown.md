# Research Lab Markdown Briefs

Export paper metadata to compact Markdown before sending it to LLM/research
agents. This keeps token usage low and avoids feeding raw HTML/PDF text into the
agent loop.

```bash
python3 -m research_lab.run_markdown_export \
  --store research_lab/data/paper_store.jsonl \
  --out research_lab/reports/latest_papers.md \
  --limit 20 \
  --abstract-chars 650
```

Each paper brief includes citation fields, a shortened abstract, and a first-pass
research-use note. Full papers should only be fetched when the markdown brief is
worth deeper review.

