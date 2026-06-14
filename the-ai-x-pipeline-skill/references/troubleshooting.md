# Troubleshooting

## `[ERROR] ANTHROPIC_API_KEY 환경변수를 설정하세요`
The key isn't in the environment. Export it before running:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
`run.py` can also read it from the macOS Keychain (service `ai-pipeline`), but
when you invoke `pipeline.py` directly you must export it. Ask the user for the
key if it's missing — never invent or hardcode one.

## NotebookLM commands fail / `nlm auth status` non-zero
NLM sessions expire after ~20 minutes and need a Chrome window logged into the
Google account.
- Re-run `.venv/bin/nlm login`, **or**
- Drop NLM entirely with `--no-nlm` (Claude-only; no slides, but debate + design
  JSON + HTML viewer still generate).

## `PyMuPDF 없음` on PDF mode
```bash
.venv/bin/pip install pymupdf
```
Only needed for `--pdf`. PDF text is capped at the first 12 pages / 4000 chars
per file by design.

## Run seems stuck
It isn't fast. `--mode deep` NLM research is ~5 minutes; the full pipeline runs
multiple multi-turn debates. Use a long timeout (10+ min for deep). Output is
streamed live to stdout — watch for the `Phase N` banners to confirm progress.

## Empty / malformed result
`safe_json()` already repairs truncated JSON (closes open braces/brackets). If a
phase still returns nothing (`아이디어 생성 실패`), re-run — model variance. Lower
`--rounds` if you want a faster, cheaper retry.

## No slides appeared
Slides only generate when an NLM notebook exists. If you ran `--no-nlm`, that's
expected — there is no deck. Otherwise confirm NLM login succeeded and the run
reached Phase 6.

## Cost control
~$0.05–0.20 per full run. To minimize: fewer `--rounds`, `--mode fast`, or
`--no-nlm` for a debate-only dry run.
