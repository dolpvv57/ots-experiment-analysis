---
description: "Task list for chat-box-auto-open experiment analysis implementation"
---

# Tasks: Chat-box-auto-open Experiment Analysis

**Input**: Design documents from `/specs/001-chat-box-auto-open-analysis/`
**Prerequisites**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md), [contracts/report-output.md](contracts/report-output.md)

**Tests**: Targeted unit tests are included for the math-heavy modules (load validation, engagement metric math, redirect joins, statistical tests, daily trends) because correctness of these pieces drives the report's credibility. Tests are NOT a strict TDD gate — they may be written alongside or right after implementation.

**Organization**: Tasks are grouped by user story (US1 Engagement, US2 Redirect, US3 HTML Report) so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on other in-flight tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All file paths are absolute or relative to the repo root `/Users/becky.ding/Documents/Bamboo/OTS/analyze-experiment/`

## Path Conventions (per [plan.md](plan.md))

- Source code: `Chat-box-auto-open/analysis/` (Python package under the existing experiment folder)
- Tests: `tests/` at repo root
- Output: `specs/001-chat-box-auto-open-analysis/report.html` (per FR-014)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, dependencies, basic tooling.

- [ ] T001 Create the `Chat-box-auto-open/analysis/` Python package with empty `__init__.py`, plus `Chat-box-auto-open/analysis/templates/` directory (the package already lives next to `Chat-box-auto-open/data/` per plan.md Project Structure)
- [ ] T002 Create `requirements.txt` at the repo root pinning `pandas>=2.0,<3.0`, `scipy>=1.11,<2.0`, `statsmodels>=0.14,<0.15`, `plotly>=5.18,<6.0`, `jinja2>=3.1,<4.0`, `pytest>=7.4,<8.0`
- [ ] T003 [P] Create `pyproject.toml` (or `setup.cfg`) configuring `pytest` test discovery in `tests/` and adding `Chat-box-auto-open` to `sys.path` so `python -m analysis.main` works
- [ ] T004 [P] Create `.gitignore` entries for `.venv/`, `__pycache__/`, `*.pyc`, and `specs/001-chat-box-auto-open-analysis/report.html` (the generated artifact should not be checked in)
- [ ] T005 Create `tests/` directory with `tests/__init__.py`, `tests/conftest.py`, and `tests/fixtures/` subdirectory

**Checkpoint**: A fresh `python3.11 -m venv .venv && pip install -r requirements.txt && pytest --collect-only` succeeds (collects zero tests, no errors).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modules and fixtures that BOTH US1 and US2 depend on. No story work can start until this phase completes.

⚠️ **CRITICAL**: T006–T011 must be complete before any [US1] or [US2] task starts.

- [ ] T006 Create `tests/fixtures/tiny_actions.csv`, `tests/fixtures/tiny_ots_chat.csv`, `tests/fixtures/tiny_redirects.csv` — each with ~10–20 hand-crafted rows covering: variant A and B users, both chat_types, at least one matched redirect, at least one redirect with no chat match, at least one utid with conflicting variants (so the validation path has a positive case), at least one CHAT_TYPE_SUGGESTIONS row with empty `chat_session_id`
- [ ] T007 Implement `Chat-box-auto-open/analysis/load.py` — `load_data(data_dir: Path) -> DataBundle` returning a NamedTuple/dataclass with `actions`, `ots_chat`, `redirects` DataFrames; uses `pandas.read_csv` with explicit dtypes per data-model.md §1; raises `FileNotFoundError` with a clear message if any of the three required CSVs are missing (CLI maps this to exit code 2 per contracts/cli.md)
- [ ] T008 Extend `analysis/load.py` with `build_variant_lookup(bundle) -> tuple[pd.Series, set[str]]` that unions `(utid, variant)` from all three frames, detects utids mapped to >1 variant per FR-003, returns `(variant_lookup, excluded_utids)`; also expose `compute_variant_population(bundle, excluded_utids) -> dict[str, int]` for per-user denominators (FR-013)
- [ ] T009 [P] Implement `Chat-box-auto-open/analysis/stats.py` with `two_proportion_z_test(num_a, den_a, num_b, den_b, alpha=0.05) -> StatResult` (uses `statsmodels.stats.proportion.proportions_ztest` + Wald CI for the difference); `welch_t_test(values_a, values_b, alpha=0.05) -> StatResult` (uses `scipy.stats.ttest_ind(equal_var=False)` + manual t-distribution CI); shared `StatResult` dataclass exposes `p_value`, `ci_low`, `ci_high`, `significance_verdict` (per data-model.md §3 and FR-SIG-001..005)
- [ ] T010 [P] Add `directional_verdict(rel_lift_pct, flat_threshold_pct=2.0) -> Literal["positive", "flat", "negative"]` helper to `analysis/stats.py` per FR-007
- [ ] T011 [P] Write `tests/test_load.py` covering: schema parses correctly on tiny fixtures, missing-file path raises FileNotFoundError, variant-conflict utids end up in `excluded_utids`, `compute_variant_population` matches the hand-counted expected values; write `tests/test_stats.py` covering: known-answer two-proportion z-test (e.g., `(50, 100, 60, 100)` should give a known p-value), Welch's t-test on synthetic samples, CI bounds bracket the point estimate, `directional_verdict` thresholds at exactly ±2%

**Checkpoint**: `pytest tests/test_load.py tests/test_stats.py -v` is green. The package can load all four CSVs (run an ad-hoc `python -c "from analysis.load import load_data; print(load_data('Chat-box-auto-open/data').ots_chat.shape)"`).

---

## Phase 3: User Story 1 — Engagement Analysis (Priority: P1) 🎯 MVP

**Goal**: Compute the 8 engagement metrics (2 chat_types × 4 aggregation dimensions) + the 1 rounds metric, run statistical tests, and produce the two engagement daily-trend tables (data structures only — chart rendering happens in US3).

**Independent Test**: After this phase, running `python -c "from analysis.engagement import compute_engagement; from analysis.load import load_data, build_variant_lookup; ...; print(metrics)"` outputs the 8 EngagementMetric rows + 1 RoundsMetric with non-null p-values, CIs, and verdicts. `pytest tests/test_engagement.py` is green.

### Implementation for User Story 1

- [ ] T012 [US1] Implement `Chat-box-auto-open/analysis/engagement.py::compute_engagement_metrics(chat_with_variant, variant_population) -> list[EngagementMetric]` — for each `(chat_type, dimension)` in the cartesian product of `{CHAT_TYPE_SUGGESTIONS, CHAT_TYPE_INTENT_RECOGNITION} × {utid, chat_session_id, request_id, correlation_id}`, count distinct `dimension` values per variant, normalize by `variant_population` (or by total dimension count for non-utid dimensions), call `two_proportion_z_test`, populate the `EngagementMetric` dataclass per data-model.md §3; respects the empty-`chat_session_id` exclusion rule for the `chat_session_id` dimension only (per spec Edge Cases)
- [ ] T013 [US1] Implement `analysis/engagement.py::compute_rounds_metric(chat_with_variant) -> RoundsMetric` — filters to `CHAT_TYPE_INTENT_RECOGNITION`, groups by `(chat_session_id, variant)`, takes max `rounds` per session, then computes mean+median per variant and runs `welch_t_test` on the per-session vectors (FR-008)
- [ ] T014 [US1] Implement `analysis/engagement.py::compute_engagement_trends(chat_with_variant) -> tuple[DailyTrend, DailyTrend]` — returns the two `DailyTrend` objects for charts `engagement_abs` and `engagement_ratio` per data-model.md §5; each trend has `utid_panel` and `chat_session_panel` DataFrames with columns `(dt, variant, value)`; ratio chart computes numerator/denominator independently per `(dt, variant)` (FR-TREND-004)
- [ ] T015 [P] [US1] Define the `EngagementMetric`, `RoundsMetric`, and `DailyTrend` dataclasses in `analysis/engagement.py` matching data-model.md §3 and §5 (or import from a shared `analysis/types.py` if cleaner)
- [ ] T016 [P] [US1] Write `tests/test_engagement.py` covering: hand-counted distinct counts on the tiny fixture for all 4 dimensions, empty-`chat_session_id` rows excluded only from per-session aggregation, `compute_rounds_metric` returns expected mean/median on a tiny fixture with known rounds values, `compute_engagement_trends` produces correct daily numerators/denominators for both charts on the tiny fixture (especially the per-day independent ratio rule)

**Checkpoint**: US1 is complete and independently demonstrable: feed the real `Chat-box-auto-open/data/` through `load_data` → `build_variant_lookup` → `compute_engagement_metrics` and observe sensible numbers; tests green.

---

## Phase 4: User Story 2 — Redirect Analysis (Priority: P1)

**Goal**: Compute the 4 redirect rate metrics + 1 redirect-funnel rate (per all variant users), run z-tests, and produce the two redirect daily-trend tables.

**Independent Test**: After this phase, running the redirect computation on the tiny fixture or the real data yields 4 RedirectMetric rows with non-null p-values + CIs and 2 daily-trend objects. `pytest tests/test_redirects.py` is green.

**Dependency note**: US2 depends on Foundational (T006–T011). It does NOT depend on US1 — both P1 stories can be developed in parallel.

### Implementation for User Story 2

- [ ] T017 [US2] Implement `Chat-box-auto-open/analysis/redirects.py::build_redirect_attributed(chat_interaction, redirects_df) -> pd.DataFrame` — inner-joins INTENT_RECOGNITION rows to `redirects` on `correlation_id == pre_redirect_id` per FR-010; carries `(utid, chat_session_id, request_id, correlation_id, variant, dt)`; explicitly skips any non-INTENT row (FR-009 enforcement)
- [ ] T018 [US2] Implement `analysis/redirects.py::compute_redirect_metrics(chat_interaction, redirect_attributed) -> list[RedirectMetric]` — for each dimension in `{utid, chat_session_id, request_id, correlation_id}`, numerator = distinct dimension values appearing in `redirect_attributed` per variant; denominator = distinct dimension values in `chat_interaction` per variant (per FR-011); call `two_proportion_z_test`, populate `RedirectMetric` per data-model.md §4; respects empty-`chat_session_id` exclusion for the chat_session_id dimension
- [ ] T019 [US2] Implement `analysis/redirects.py::compute_redirect_funnel_metric(redirect_attributed, variant_population) -> RedirectFunnelMetric` — distinct utids with ≥1 attributed redirect divided by `variant_population[v]` per FR-013; uses `two_proportion_z_test` with denominators = `variant_population`
- [ ] T020 [US2] Implement `analysis/redirects.py::compute_redirect_trends(chat_interaction, redirect_attributed) -> tuple[DailyTrend, DailyTrend]` — returns the two `DailyTrend` objects for charts `redirect_abs` and `redirect_ratio` per data-model.md §5; ratio uses INTENT_RECOGNITION distinct counts as denominator (per `(dt, variant)`); empty-session rows excluded only from `chat_session_panel`
- [ ] T021 [P] [US2] Define `RedirectMetric` and `RedirectFunnelMetric` dataclasses in `analysis/redirects.py` (or in shared `analysis/types.py` from T015) matching data-model.md §4
- [ ] T022 [P] [US2] Write `tests/test_redirects.py` covering: redirect attribution drops SUGGESTIONS rows, redirects without a matching chat are excluded from numerators, hand-counted rates match `compute_redirect_metrics` output on the tiny fixture, funnel-rate denominator is `variant_population` (not chat-active users), trend ratio computed independently per `(dt, variant)`

**Checkpoint**: US2 is complete; tests green; can run end-to-end redirect numbers on the real data.

---

## Phase 5: User Story 3 — Self-Contained HTML Report (Priority: P2)

**Goal**: Render every metric, table, chart, and verdict computed by US1 and US2 into a single self-contained `report.html` file at the path required by FR-014.

**Independent Test**: After this phase, `python -m analysis.main --verbose` exits 0 and writes `specs/001-chat-box-auto-open-analysis/report.html`; the file opens in a browser with no internet, all 5 sections present per [contracts/report-output.md](contracts/report-output.md), no broken charts, file size < 10 MB.

**Dependency note**: US3 depends on US1 and US2 outputs but its rendering layer can be developed in parallel using stub `EngagementMetric`/`RedirectMetric`/`DailyTrend` instances; final integration happens in T029.

### Implementation for User Story 3

- [ ] T023 [US3] Implement `Chat-box-auto-open/analysis/render.py::build_static_chart(metric) -> str` — Plotly grouped bar chart of A vs B for one rate metric, returns HTML `<div>` snippet via `plotly.io.to_html(..., include_plotlyjs=False, full_html=False)`; uses consistent variant colors (A = `#4C78A8`, B = `#F58518`); axis titles + legend per FR-017 and contracts/report-output.md
- [ ] T024 [US3] Implement `analysis/render.py::build_trend_chart(daily_trend) -> str` — Plotly figure with two side-by-side sub-panels (`make_subplots(cols=2)`), each panel showing 2 lines (A, B) per FR-TREND-002/003; date on x-axis; y-axis label depends on chart_id; returns HTML `<div>` snippet
- [ ] T025 [US3] Implement `analysis/render.py::build_exec_summary(engagement_metrics, redirect_metrics) -> dict` — picks the headline engagement metric (per-utid INTENT_RECOGNITION rate) and the headline redirect metric (per-utid redirect rate from FR-013 funnel), formats one-sentence verdicts per FR-018, and emits recommendation `"ship"` only if BOTH headlines are directionally positive AND statistically significant (FR-SIG-005)
- [ ] T026 [US3] Create `Chat-box-auto-open/analysis/templates/report.html.j2` — Jinja2 template implementing the exact structure in [contracts/report-output.md](contracts/report-output.md): inlined `<style>`, one inlined Plotly bundle, sections in order (`exec-summary`, `data-overview`, `engagement`, `redirect`, `appendix`); zebra-striped sortable tables; significance-cell coloring (light green for sig+positive, light red for sig+negative)
- [ ] T027 [US3] Implement `analysis/render.py::render_report(context: ReportContext, output_path: Path) -> int` — loads the template, renders into the path, returns the bytes written; inlines the Plotly bundle exactly once (use `include_plotlyjs='inline'` on the FIRST chart and `include_plotlyjs=False` on the rest, OR use `include_plotlyjs='cdn'` swap with manual inlining at template top); ensures the output meets the self-containment checks in contracts/report-output.md
- [ ] T028 [US3] Implement `Chat-box-auto-open/analysis/main.py` CLI per [contracts/cli.md](contracts/cli.md) — `argparse` for `--data-dir`, `--output`, `--flat-threshold`, `--alpha`, `--verbose`; orchestrates: `load_data` → `build_variant_lookup` → `compute_variant_population` → engagement/redirects/trends in parallel-friendly order → `build_exec_summary` → `render_report`; emits the verbose stage timings to stderr; maps `FileNotFoundError` to exit code 2; emits the `>50% excluded utids` guard as exit code 3 per cli.md; uses absolute paths
- [ ] T029 [US3] Wire end-to-end integration: run `python -m analysis.main --verbose` against the real `Chat-box-auto-open/data/`, confirm `report.html` is created at the expected path, manually open in a browser (with Wi-Fi off) and walk through the 5-section checklist in [contracts/report-output.md](contracts/report-output.md); fix any rendering or sizing issues

**Checkpoint**: All three user stories now functional. Running `/speckit.implement` from a fresh checkout reproduces the report.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Determinism, perf, docs, and validation against the quickstart.

- [ ] T030 [P] Add a brief `Chat-box-auto-open/analysis/README.md` summarizing how to run and where the report lands; link to [quickstart.md](quickstart.md) for the full walkthrough (skip this if you'd rather keep docs only in `specs/`)
- [ ] T031 [P] Run the [quickstart.md](quickstart.md) Step 1–5 verbatim from a fresh `.venv`, confirm timings are within ±50% of the documented numbers, fix anything that drifted
- [ ] T032 Verify FR-015 (self-containment) end-to-end: copy `report.html` to `/tmp/`, disable Wi-Fi, open it; confirm all charts render and total file size < 10 MB
- [ ] T033 Verify determinism: run the pipeline twice in a row, diff the two `report.html` outputs, confirm differences are limited to `<meta name="generated_at">` and the footer timestamp (per the contract)
- [ ] T034 Skim the rendered report against the spec one more time: every FR-* and FR-SIG-* and FR-TREND-* requirement is reflected in the report; if any aren't, file follow-up tasks

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS all user stories.**
- **US1 (Phase 3)** and **US2 (Phase 4)**: Both depend only on Foundational. **Can run in parallel.**
- **US3 (Phase 5)**: Depends on US1 + US2 outputs for the final integration step (T029). The rendering layer (T023–T028) can be drafted in parallel using stub data, but the final wiring/validation requires US1 and US2 to be done.
- **Polish (Phase 6)**: Depends on US3 being functional.

### User Story Dependencies

- **US1 (Engagement, P1)**: Depends only on Foundational.
- **US2 (Redirect, P1)**: Depends only on Foundational. **Independent of US1.**
- **US3 (HTML Report, P2)**: Depends on US1 and US2 outputs at integration time.

### Within Each User Story

- Models/dataclasses (T015, T021) before the functions that produce them.
- Computation modules (T012–T014, T017–T020) before tests that exercise them — except where TDD is preferred, in which case tests can be written first and start red.
- All metric/trend computation before render (T023+).
- Render before CLI orchestration (T028).
- CLI orchestration before end-to-end integration (T029).

### Parallel Opportunities

- T003, T004 within Setup.
- T009, T010, T011 within Foundational (different files).
- T015, T016 within US1 (dataclass definition + tests can be drafted while T012–T014 are in flight).
- T021, T022 within US2 (same pattern).
- US1 (Phase 3) and US2 (Phase 4) entirely in parallel between two developers.
- T030, T031 within Polish.

---

## Parallel Example: Foundational Phase

```bash
# After T006–T008 (load.py + fixtures) land:
Task: "T009 Implement analysis/stats.py — z-test + Welch's t + StatResult dataclass"
Task: "T010 Add directional_verdict helper to analysis/stats.py"
Task: "T011 Write tests/test_load.py and tests/test_stats.py"
# All three operate on independent file scopes.
```

## Parallel Example: US1 + US2 (two-developer split)

```bash
# After Phase 2 checkpoint:
Developer A: T012 → T013 → T014 → T015 → T016   # Engagement
Developer B: T017 → T018 → T019 → T020 → T021 → T022   # Redirect
# Then they meet at T023 (US3) for the rendering layer.
```

---

## Implementation Strategy

### MVP Path (single developer)

1. **Phase 1 + Phase 2** (T001–T011): set up the project and the shared loader/stats foundations.
2. **Phase 3 (US1)** (T012–T016): get engagement numbers right against the tiny fixture, then on real data.
3. **Phase 4 (US2)** (T017–T022): same drill for redirects.
4. **Phase 5 (US3)** (T023–T029): build the rendering layer, wire the CLI, generate `report.html`, verify it opens offline.
5. **Phase 6** (T030–T034): polish, determinism, doc validation.

### Incremental delivery

- After Phase 3: have engagement numbers in a Python REPL. Already valuable.
- After Phase 4: redirect numbers also in REPL. Both halves of the experiment story computable.
- After Phase 5: the deliverable HTML is generated. The actual user-facing artifact.
- After Phase 6: confidence the deliverable is reproducible and self-contained.

### Two-developer split

- Dev A and Dev B pair on Phases 1 and 2 (small).
- Dev A takes US1 (T012–T016).
- Dev B takes US2 (T017–T022).
- Whoever finishes first starts on US3 rendering (T023–T028).
- Both meet at T029 for end-to-end integration.

---

## Notes

- `[P]` markers reflect file-level independence — same-file tasks are kept sequential even when the work could overlap.
- The `tests/fixtures/tiny_*.csv` files are the test contract: they are tiny but must cover every edge case enumerated in the spec.
- T009 and T010 both modify `analysis/stats.py` but were left as separate tasks for review granularity; if a dev does both, they should keep them as one PR.
- T015 and T021 both create dataclasses; merge into a shared `analysis/types.py` if you'd rather avoid scattered definitions (this is a reasonable refactor during the first PR review).
- Output file (`report.html`) is intentionally NOT checked into git (T004); generate it fresh from a clean run.
