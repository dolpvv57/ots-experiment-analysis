# Implementation Plan: Chat-box-auto-open Experiment Analysis

**Branch**: `001-chat-box-auto` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-chat-box-auto-open-analysis/spec.md`

## Summary

A one-shot Python data-analysis pipeline that ingests two CSV files from `Chat-box-auto-open/data/` (`ots_chat.csv` and `redirects.csv`; `actions.csv` is intentionally not loaded), computes A/B engagement metrics (8 rate-style metrics across 4 aggregation dimensions × 2 chat types), redirect metrics (4 rate-style metrics joined via `correlation_id ↔ pre_redirect_id`), runs two-proportion z-tests on rates and Welch's t-test on the `rounds` mean (α=0.05; no multiple-comparisons correction), generates four daily-trend charts (engagement absolute/ratio + redirect absolute/ratio, each split by `utid` and `chat_session_id` sub-panels), and emits a single self-contained HTML report.

**Technical approach**: Python 3.11 + pandas for CSV processing, scipy.stats + statsmodels for the z-test and Welch's t-test, Plotly for charts (rendered with `include_plotlyjs='inline'` so the HTML is fully self-contained), and Jinja2 for HTML templating. Single-script orchestration; no service or daemon. Output: one `report.html` file at the feature directory root.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: pandas ≥ 2.0, scipy ≥ 1.11, statsmodels ≥ 0.14, plotly ≥ 5.18, jinja2 ≥ 3.1
**Storage**: Local CSV files under `Chat-box-auto-open/data/` (read-only); two of the four files are loaded (`ots_chat.csv` ≈ 4.2M rows, `redirects.csv` ≈ 2M rows); `actions.csv` and `ots_matched_hotels.csv` are skipped
**Testing**: pytest ≥ 7.4 with small CSV fixtures under `tests/fixtures/`
**Target Platform**: macOS / Linux developer laptop (Python 3.11 venv)
**Project Type**: Single-script analysis (one Python package, no service/UI)
**Performance Goals**: Full pipeline (load → compute → render) completes in under 5 minutes on a 16 GB MacBook
**Constraints**: Output `report.html` MUST open offline with no external assets; total HTML size < 10 MB so it can be emailed
**Scale/Scope**: 2 input CSVs (~6.1M rows total loaded); 13 statistical tests; 4 daily-trend charts × 2 sub-panels each; static A-vs-B tables for 8 engagement + 4 redirect metrics

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repository's constitution at `.specify/memory/constitution.md` is a placeholder template with no ratified principles. **No active gates apply.** When the constitution is filled in, re-evaluate this section.

| Gate | Status | Notes |
|------|--------|-------|
| Constitution principles ratified | N/A | Template only, no principles defined |
| Simplicity (single project) | PASS | One Python package; no service, no DB, no frontend |
| Test coverage on metric functions | PASS | pytest unit tests planned for engagement, redirect, stats modules |
| Reproducibility | PASS | Deterministic pipeline; same CSVs → identical HTML (modulo timestamp in footer) |

## Project Structure

### Documentation (this feature)

```text
specs/001-chat-box-auto-open-analysis/
├── plan.md              # This file
├── spec.md              # Approved feature spec (with Clarifications)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (CSV schemas, derived entities)
├── quickstart.md        # Phase 1 output (how to run + verify)
├── contracts/
│   └── report-output.md # Spec of the HTML report's structure / contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (already passing)
└── tasks.md             # Phase 2 output (created by /speckit.tasks, NOT here)
```

### Source Code (repository root)

```text
Chat-box-auto-open/
├── data/                       # Input CSVs (already present, read-only)
│   ├── actions.csv             # NOT loaded by this analysis
│   ├── ots_chat.csv            # LOADED (engagement + variant labels)
│   ├── redirects.csv           # LOADED (redirect attribution)
│   └── ots_matched_hotels.csv  # NOT loaded by this analysis
├── analysis/                   # NEW: Python package implementing the pipeline
│   ├── __init__.py
│   ├── load.py                 # CSV loading + in-file variant-consistency check
│   ├── engagement.py           # 8 engagement metrics (2 chat_types × 4 dimensions)
│   ├── redirects.py            # 4 redirect rates + per-all-users redirect rate
│   ├── stats.py                # two-proportion z-test + Welch's t-test + 95% CI
│   ├── trends.py               # 4 daily-trend tables (engagement abs/ratio + redirect abs/ratio)
│   ├── render.py               # Jinja2 template rendering + Plotly inlining
│   ├── templates/
│   │   └── report.html.j2      # Jinja2 template for the HTML report
│   └── main.py                 # CLI entry point: `python -m analysis.main`
└── (report.html lives at specs/001-chat-box-auto-open-analysis/report.html per FR-014)

tests/
├── conftest.py                 # Shared fixtures (tiny CSV builders)
├── fixtures/
│   ├── tiny_actions.csv
│   ├── tiny_ots_chat.csv
│   └── tiny_redirects.csv
├── test_load.py
├── test_engagement.py
├── test_redirects.py
├── test_stats.py
└── test_trends.py
```

**Structure Decision**: Single Python package `analysis/` under the existing `Chat-box-auto-open/` directory (which already holds the `data/` folder), keeping the experiment self-contained. Tests live in a top-level `tests/` directory at the repo root. Output `report.html` is written into `specs/001-chat-box-auto-open-analysis/` per FR-014 ("feature directory root"). No frontend, no API, no database — this is a CLI-style script.

## Complexity Tracking

> Constitution has no ratified principles, so there are no violations to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none)    | —          | —                                    |
