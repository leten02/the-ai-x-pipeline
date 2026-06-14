# Modes & Flags

Run everything with the venv python from the repo root:
`.venv/bin/python3 pipeline.py [topic] [flags]`

## The four modes

### 1. Autonomous discovery
AI invents 10 ideas, debates them down to 1, then builds a 12-slide deck.
```bash
.venv/bin/python3 pipeline.py --innovative-ai --rounds 3 --mode fast
```

### 2. Topic-seeded discovery
User names a domain; AI generates ideas inside it. `--user-problem` is optional
and sharpens the idea generation around a specific pain point.
```bash
.venv/bin/python3 pipeline.py --innovative-ai \
  --user-topic "노인 돌봄" --user-problem "야간 돌봄 공백"
```

### 3. PDF-seeded discovery
Extracts a commercializable domain from a tech paper (Phase 0, first 12 pages).
```bash
.venv/bin/python3 pipeline.py --innovative-ai --pdf paper.pdf
# multiple papers: --pdf a.pdf b.pdf
```

### 4. Topic research (not a new startup)
Positional `topic`, no `--innovative-ai`. Analyzes → researches → debates →
designs a 9-slide research presentation.
```bash
.venv/bin/python3 pipeline.py "전기차 충전 인프라"
```

## Flags

| Flag | Meaning | Default |
|------|---------|---------|
| `topic` (positional) | research target; omit in discovery modes | — |
| `--innovative-ai` | new-business discovery mode | off |
| `--user-topic` | domain to seed discovery | — |
| `--user-problem` | user-defined pain point fed into ideation | — |
| `--pdf FILE...` | paper(s) to mine for a domain | — |
| `--rounds N` | deep-debate rounds (clamped 1–5 in `run.py`) | 2 |
| `--mode fast\|deep` | NLM search: fast ~30s / deep ~5min | fast |
| `--no-nlm` | skip NotebookLM, Claude only (no slides) | off |
| `--lang` | NLM report language | ko |
| `--out DIR` | output directory | output |

## Notes
- `--no-nlm` skips Phase 3 research **and** Phase 6 slide generation. You still
  get the debate, the design JSON, and the HTML viewer — just no NLM deck.
- `--mode deep` is much slower; only use when the user wants thorough research.
- Discovery deck = 12 slides (incl. `lean_canvas`); research deck = 9 slides.
- Model used: `claude-sonnet-4-6`.
