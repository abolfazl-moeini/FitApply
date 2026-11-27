# AGENTS.md — FitApply

AI-powered job application automation agent for Iranian (`jobinja`, `jobvision`, `irantalent`) and global (`remotive`, `themuse`, `linkedin`, `indeed`) job boards.

## Core Design Principles

- **Anti-Overengineering:** Keep the stack lightweight and dependency-minimal (`uv` + Python `>=3.11,<3.14`). Do not add web servers or heavy UI frameworks (no Streamlit, FastAPI, or Docker). Visual reporting uses a standalone, zero-dependency HTML file.
- **Site-Hosted vs. Local PDF Resume:** Iranian boards (`jobinja`, `jobvision`, `irantalent`) default to `site_profile` mode — they use the user's pre-configured on-site resume, never touch `input[type="file"]`, and do not require a local PDF (`candidate_profile` in `config.yaml` is used for matching). Global boards default to `auto` mode (upload PDF only if provided and a visible file input exists).
- **Safe Automation:** Connect to the user's logged-in Chrome instance via CDP (`--remote-debugging-port=9222`). `--dry-run` must never trigger 1-click or final submissions.

## Project Layout

- `src/fitapply/cli.py` — Typer CLI (`parse`, `audit`, `status`, `run`) with `--config`, `--upload-mode`, `--dry-run`, `--auto`, `--html`, and `--export`.
- `src/fitapply/resume.py` — PDF extraction (`pymupdf`, prompt-budget bounded), SHA-256 fingerprint-aware `.pdf.profile.json` caching, `build_profile_from_config()`, and bounded `audit_resume()`.
- `src/fitapply/discovery/` — `BaseDiscoverer` / `JobPosting` (`base.py`), platform registry (`__init__.py`), Iranian scrapers (`iran_boards.py`), and global/remote boards (`global_boards.py`: `GlobalBoardsDiscoverer`, `RemotiveDiscoverer`, `TheMuseDiscoverer`).
- `src/fitapply/matcher.py` — `evaluate_job_fit()` producing `JobMatchEvaluation` (`fit_score` clamped `0..100`, `seniority_fit`, `compensation_fit`, `cover_letter`) with candidate privacy filtering and salary unit awareness.
- `src/fitapply/applier.py` — `BrowserApplier` with lazy persistent CDP lifecycle (`async with`), read-only `--dry-run`, `site_profile` / `auto` / `always_upload` handling, scoped modal/receipt verification, and LLM screening Q&A.
- `src/fitapply/llm.py` — `BaseLLM` (with 1-retry JSON recovery strictly for decode/schema failures), `AntigravityLLM`, and `LiteLLM`.
- `src/fitapply/store.py` — SQLite `JobStore` (`data/jobs.db`) with atomic `claim_application()`, safe retryable pre-submit failures, and protected submissions.
- `src/fitapply/report.py` — Markdown and standalone HTML dashboard export with DB overwrite protection, context-aware escaping, and `http(s)://` URL validation.
- `tests/` — Unit and integration test suite (`pytest` + `pytest-asyncio`, 66 tests).

## Commands

```bash
# Sync environment
uv sync --extra antigravity

# Run full test suite (all 66 tests must pass before committing)
uv run pytest -v

# Check CLI entrypoints
uv run fitapply --help
uv run fitapply run --help
uv run fitapply status --help
```

## Conventions & Guardrails

1. **Tests:** Always run `uv run pytest -v` after edits. Mock network (`httpx.AsyncClient`), Playwright, and LLM calls in unit tests — never hit live external APIs or real Chrome in tests.
2. **Scrapers:** Always deduplicate within `search_jobs()` via `seen_ids`, strip trailing slashes when extracting post IDs, and guard against `null` nested JSON fields.
3. **Security & Sanitization:** Escape all untrusted job data in HTML/Markdown reports and bound PDF text passed to LLM prompts.
4. **Versioning:** Keep `__version__` in `src/fitapply/__init__.py`, `version` in `pyproject.toml`, and the header in `README.md` synchronized.
