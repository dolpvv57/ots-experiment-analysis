# Phase 0 Research: Chat-box-auto-open Experiment Analysis

**Feature**: 001-chat-box-auto-open-analysis
**Date**: 2026-05-21
**Status**: Complete — no NEEDS CLARIFICATION remain.

This document captures the technology and methodology decisions referenced by [plan.md](plan.md). Each section answers a single open question identified during planning.

---

## R1. Charting library: how to embed interactive charts in a self-contained HTML file

**Decision**: Use **Plotly** (`plotly.graph_objects` + `plotly.io.to_html` with `include_plotlyjs='inline'` and `full_html=False`). Each chart is rendered to an HTML `<div>` snippet with the Plotly JS library inlined exactly once at the top of the report.

**Rationale**:

- FR-015 requires the HTML to render with no internet and no sibling files. Plotly's `include_plotlyjs='inline'` embeds the ~3.5 MB JS bundle into the file, satisfying this requirement.
- Plotly renders interactive charts (hover, zoom, legend toggling), which makes daily-trend lines actually readable when stakeholders compare A vs B per day.
- `full_html=False` per chart lets us combine multiple charts into a single Jinja-rendered template without duplicating the Plotly bundle.
- One single inlined Plotly bundle keeps total file size around 4–6 MB even with 4 trend charts + ~12 static bar charts, well under the 10 MB email budget.

**Alternatives considered**:

- **Matplotlib + base64-encoded PNGs**: smaller file, but no interactivity (hover, day-level tooltip). Daily trend charts with two sub-panels and 4 lines benefit from interactivity. Rejected.
- **Bokeh**: comparable to Plotly for self-contained HTML, but the team's existing analyses use Plotly. Rejected for consistency.
- **Altair / Vega-Lite**: declarative and clean, but requires careful handling for fully-offline rendering and produces noticeably larger HTML files for many charts. Rejected.

---

## R2. Statistical test implementation

**Decision**:

- **Two-proportion z-test** for all rate-style metrics (8 engagement rates + 4 redirect rates) → use `statsmodels.stats.proportion.proportions_ztest` for the p-value and `statsmodels.stats.proportion.confint_proportions_2indep` (or manual Wald formula) for the 95% CI of the difference of proportions.
- **Welch's t-test** for the `rounds` mean → use `scipy.stats.ttest_ind(..., equal_var=False)` with the per-session rounds vectors of variant A and B; CI is computed manually from the t-distribution.

**Rationale**:

- `statsmodels` is the de-facto Python library for proportions tests; it returns both z-statistic and p-value in one call.
- `scipy.stats.ttest_ind(equal_var=False)` is the canonical Welch's t implementation. Pairing it with a manual Wald CI keeps the implementation transparent and avoids a heavier dependency like `pingouin`.
- α = 0.05 and "no multiple-comparisons correction" are encoded as constants in `analysis/stats.py`; raw p-values are reported as-is per FR-SIG-006.

**Alternatives considered**:

- **`scipy.stats.proportions_ztest`**: scipy does not actually expose a one-shot two-proportion z-test; the recommended path is statsmodels. Rejected.
- **Bootstrap CIs**: rejected during clarification (see spec session 2026-05-21, Q1) — slower and unnecessary at this sample size.
- **Pingouin**: clean API, but a third stats dependency on top of scipy + statsmodels is overkill. Rejected.

---

## R3. Loading 8.5M rows efficiently

**Decision**: Use `pandas.read_csv` with explicit `dtype` per column and `parse_dates=['dt']`. Load the four input CSVs once at startup; keep them as separate DataFrames; do all aggregation in pandas (vectorized groupby), not row-by-row. JSON-shaped string columns (e.g., `chat_box_entry_loaded`) are NOT parsed in v1 because the analysis only needs `chat_type`, `correlation_id`, `request_id`, `chat_session_id`, `utid`, `variant`, `dt`, `rounds`.

**Rationale**:

- ~8.5M rows × ~10 columns fits comfortably in 16 GB RAM as a typed DataFrame (~2-3 GB).
- Skipping JSON-column parsing for v1 saves significant load time; if a later version needs `loaded_area` / `selected_sorting_columns` etc., we add the parser then.
- Explicit dtypes (UUID strings as `string[python]` or `category` where unique values are bounded) avoid pandas's `object` default and reduce memory.

**Alternatives considered**:

- **Polars**: 5–10× faster on the load step, but adds a new dependency the rest of the codebase doesn't yet use. Pandas is sufficient for a 5-min budget. Reconsider if we ever drop the budget below 60 s.
- **DuckDB read_csv**: extremely fast for joins, but introduces SQL inside Python. Pandas is more idiomatic for this team's analyses. Rejected.
- **Chunked load + accumulate**: not needed at 8.5M rows. Premature optimization.

---

## R4. Variant-consistency validation

**Decision**: Build a lookup `utid → variant` from the union of all rows across `actions.csv`, `ots_chat.csv`, and `redirects.csv`. Any `utid` that maps to more than one variant is logged to a "data quality" list and excluded from comparative analysis (per FR-003). The count of excluded utids is reported in the Appendix.

**Rationale**:

- A/B experiments occasionally have a tiny number of utids whose variant flipped during the experiment (e.g., re-bucketing). Including them double-counts and biases the comparison.
- Logging the count lets the reader judge whether the exclusion is material.

**Alternatives considered**:

- **Drop only the conflicting rows, not the user**: keeps more data but mixes A and B activity for the same user. Rejected — bias risk.
- **Pick the first-seen variant and keep all rows**: arbitrary tiebreaker; rejected.

---

## R5. Daily trend ratio: how to compute "ratio" per day

**Decision**: For ratio charts (engagement-ratio = INTENT_RECOGNITION ÷ SUGGESTIONS; redirect-ratio = redirect ÷ INTENT_RECOGNITION), compute numerator and denominator independently within each `(dt, variant)` group, at the appropriate aggregation dimension (utid or chat_session_id), then divide. No carry-forward, no smoothing, no cumulative.

**Rationale**:

- FR-TREND-004 mandates this exact rule.
- Per-day independent ratios let the reader see day-level effects (e.g., a single bad day) rather than smearing them across the window.

**Alternatives considered**:

- **7-day rolling ratio**: smoother, but hides daily anomalies. The user did not ask for smoothing. Rejected.
- **Cumulative ratio**: would be useful for a launch-monitoring dashboard, not for a one-shot retro. Rejected.

---

## R6. HTML templating: Jinja2 vs string concat

**Decision**: Use **Jinja2** with a single `report.html.j2` template under `analysis/templates/`. The template receives a context dict containing pre-rendered chart `<div>` strings, metric tables (rendered as HTML via `pandas.DataFrame.to_html`), and computed verdict strings; the template handles section ordering and the executive summary.

**Rationale**:

- Keeps presentation (HTML, CSS) separate from computation (Python).
- Jinja2 is already a transitive dependency of most Python data tooling; tiny addition.
- Easy to iterate on the report layout without re-running the analysis: load saved DataFrames + re-render template.

**Alternatives considered**:

- **Pure string concatenation in `render.py`**: simpler at first but quickly becomes unreadable once the template has 5 sections, conditional verdicts, and embedded Plotly divs. Rejected.
- **`pandas.DataFrame.to_html` + manual concat**: still applicable for the metric tables, but doesn't solve the section-level structure. We use it INSIDE the Jinja template.

---

## R7. Reproducibility & determinism

**Decision**: Pin top-level dependency versions via `requirements.txt` (and a `requirements.lock` if the team's other projects use one). The analysis itself is deterministic — given the same CSVs, the same `report.html` is produced (modulo a timestamp in the footer that says when the report was generated).

**Rationale**:

- Reviewers re-running the report should get identical numbers.
- The footer timestamp is the only source of variance and is clearly labeled.

**Alternatives considered**:

- **Hash the inputs and embed the hash in the report**: nice-to-have, not required. Defer to a follow-up if needed.

---

## Summary of unresolved items

| Item | Status |
|------|--------|
| Statistical test type | Resolved (R2) — z-test for rates, Welch's t for rounds |
| Multiple-comparisons correction | Resolved (clarification Q2) — none, with disclosure |
| Daily trend chart layout | Resolved (clarification Q3) — 4 charts, 2 sub-panels each |
| Charting library | Resolved (R1) — Plotly with inline JS |
| HTML templating | Resolved (R6) — Jinja2 |
| Stats library | Resolved (R2) — statsmodels + scipy |
| CSV ingest pattern | Resolved (R3) — pandas with explicit dtypes |
| Reproducibility | Resolved (R7) — pinned deps; deterministic except footer timestamp |

No NEEDS CLARIFICATION remain. Ready for Phase 1 design.
