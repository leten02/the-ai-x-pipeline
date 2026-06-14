---
name: the-ai-x-pipeline
description: >
  Drives The AI [X] Pipeline — an autonomous multi-agent system that discovers
  startup business ideas, debates them with 15+ AI personas, researches real
  market data via Google NotebookLM, and generates a 12-slide investor deck.
  Use this skill when the user wants to brainstorm or validate a new business
  idea, run an adversarial idea debate, turn a topic or a research paper into a
  pitch deck, or auto-generate presentation slides. Triggers on "신사업 발굴",
  "사업 아이디어", "아이디어 토론", "발표자료 생성", "pitch deck", "business idea",
  "idea debate", "The AI X", "AI [X] pipeline", or any request to autonomously
  invent and pitch a startup.
---

# The AI [X] Pipeline

Autonomous business-idea engine: **discover → debate → research → design deck**.
Claude runs the multi-agent debate; Google NotebookLM gathers real market data
and renders the slides. Source repo: https://github.com/leten02/the-ai-x-pipeline

## Critical Rules (read first)

1. **Do NOT launch `run.py`.** It is an interactive TUI that an AI agent cannot
   drive. Always call `pipeline.py` directly with flags (see Modes below).
2. **API key required.** `ANTHROPIC_API_KEY` must be exported before running, or
   `pipeline.py` exits immediately. Never print or log the key.
3. **NotebookLM is optional.** If the user is not logged into NLM, or you cannot
   confirm a session, pass `--no-nlm` (Claude-only). Don't block on NLM.
4. **Warn about cost once.** Each full run costs ~$0.05–0.20 in Anthropic API.
   Mention this before the first run, then proceed.
5. **A run takes minutes, not seconds.** `--mode deep` NLM research alone is ~5
   min. Set a generous timeout; do not assume it hung.
6. **Outputs land in `output/`.** After a run, point the user to the HTML debate
   viewer and the NotebookLM notebook — don't try to parse slides yourself.
7. **Pick the mode from intent**, don't ask redundant questions. See decision
   tree. Default to autonomous discovery only when the user gives no topic.

## Setup (run once)

```bash
git clone https://github.com/leten02/the-ai-x-pipeline
cd the-ai-x-pipeline
python3 -m venv .venv                 # Python 3.10+
.venv/bin/pip install anthropic notebooklm-cli pymupdf keyring
export ANTHROPIC_API_KEY="sk-ant-..." # ask the user if unset
# optional, only if using NLM web research:
.venv/bin/nlm login                   # needs Chrome logged into Google
```

Verify before first run: `test -n "$ANTHROPIC_API_KEY"` and that `.venv` exists.

## Mode decision tree

```
User wants to...
│
├─► invent a business idea from scratch (no topic given)
│   └─► pipeline.py --innovative-ai --rounds 3 --mode fast
│
├─► explore a business in a SPECIFIC domain they named
│   └─► pipeline.py --innovative-ai --user-topic "<domain>" [--user-problem "<pain>"]
│
├─► turn a research PAPER into a startup
│   └─► pipeline.py --innovative-ai --pdf path/to/paper.pdf
│
├─► research / make a deck about a TOPIC (not a new startup)
│   └─► pipeline.py "<topic>"          # topic is positional, no --innovative-ai
│
└─► run WITHOUT NotebookLM (no Google login)
    └─► append --no-nlm to any of the above
```

Always run with the venv python: `.venv/bin/python3 pipeline.py ...`.
Full flag reference: `references/modes.md`.

## After a run

Tell the user where results are:
- 📑 **Slides** → `notebooklm.google.com` (the notebook the run created)
- 🌐 **Debate viewer** → the `output/*_토론뷰어.html` file (auto-opens on macOS)
- 📋 **Deck structure** → `output/*_design_*.json`
- 💬 **Full debate** → `output/*_debate_*.txt`

If the run failed, check `references/troubleshooting.md` (auth, NLM session,
JSON parse, cost). The personas and what each contributes: `references/personas.md`.
