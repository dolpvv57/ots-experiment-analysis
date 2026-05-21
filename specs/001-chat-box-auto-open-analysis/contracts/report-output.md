# Contract: HTML Report Output

**File**: `<output>` (default `specs/001-chat-box-auto-open-analysis/report.html`)
**Format**: HTML5, self-contained (no external `<link>`, no external `<script src>`).

This is the structural contract the report must satisfy. Any change to this contract requires a spec update.

## Top-level structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="generated_at" content="<ISO-8601 UTC timestamp>">
  <title>Chat-box-auto-open Experiment — A/B Analysis</title>
  <style>/* inlined CSS */</style>
  <script>/* inlined Plotly bundle (one occurrence) */</script>
</head>
<body>
  <main>
    <!-- See sections below -->
  </main>
  <footer>Generated <timestamp> · Source: Chat-box-auto-open/data/</footer>
</body>
</html>
```

## Required sections (in this order, per FR-016)

### 1. Executive Summary (`<section id="exec-summary">`)

- One headline `<h1>` and 2–4 sentences in `<p>` tags.
- MUST state, in plain language: the engagement headline finding, the redirect headline finding, and one of: **SHIP**, **DO NOT SHIP**, **INCONCLUSIVE — needs more data**.
- The recommendation MUST be inside a `<span class="verdict verdict-{ship|no-ship|inconclusive}">` tag for styling.
- Per FR-SIG-005: recommendation is "SHIP" only if the headline metric is both directionally positive AND statistically significant (p < 0.05).

### 2. Data Overview (`<section id="data-overview">`)

- Date range covered (`<dt>` min and max across loaded files).
- Variant population: distinct `utid` count per variant (table: variant, total utids).
- Excluded utids count and reason (variant conflict).
- Per-CSV row counts with date range.

### 3. Engagement Analysis (`<section id="engagement">`)

- 8 EngagementMetric rows in a single sortable HTML table with columns:
  `chat_type | dimension | A value | B value | Δ (B−A) | rel lift % | p-value | 95% CI | directional | significant?`
- Below the table, per the spec, ONE bar chart per metric (`<div class="chart">`) — 8 charts total. Grouped bar chart of A vs B with axis labels.
- 1 RoundsMetric row (mean and median per session) in a small dedicated table + 1 bar chart.
- **2 daily-trend charts** (per FR-TREND-001):
  - **Chart 1** id `trend-engagement-abs`: side-by-side sub-panels for `utid` and `chat_session_id`, two lines per panel (A, B), y = daily INTENT_RECOGNITION volume.
  - **Chart 2** id `trend-engagement-ratio`: same layout, y = daily INTENT_RECOGNITION ÷ SUGGESTIONS.

### 4. Redirect Analysis (`<section id="redirect">`)

- 4 RedirectMetric rows in a single table with columns:
  `dimension | A rate | B rate | Δ (pp) | rel lift % | p-value | 95% CI | directional | significant?`
- 1 RedirectFunnelMetric row (per all-variant-users) in a small dedicated table.
- 4 bar charts (one per RedirectMetric).
- **2 daily-trend charts** (per FR-TREND-001):
  - **Chart 3** id `trend-redirect-abs`: side-by-side sub-panels for `utid` and `chat_session_id`, two lines per panel, y = daily attributed-redirect count (INTENT_RECOGNITION-only).
  - **Chart 4** id `trend-redirect-ratio`: same layout, y = daily redirect ÷ INTENT_RECOGNITION.

### 5. Appendix (`<section id="appendix">`)

- **Methodology**: definitions of every metric with the exact formula.
- **Statistical tests**: list of the 13 tests run (which one applies to which metric).
- **Multiple comparisons** subsection per FR-SIG-007: states `total_tests * alpha = expected_false_positives` figure.
- **Flat threshold**: states `flat_threshold_pct = 2.0` and the directional rule.
- **Excluded data**: list of excluded utids count and reason.
- **Date coverage**: per-day per-variant row counts in a small table; flag any day missing one variant.

## Self-containment requirements

| Requirement | Verification |
|-------------|--------------|
| No `<link rel="stylesheet" href=...>` to an external stylesheet | grep |
| No `<script src=...>` to an external URL | grep |
| No `<img src=...>` referencing remote URLs | grep |
| No iframes | grep |
| Only one Plotly bundle inlined | content match |
| File opens cleanly with `--allow-file-access-from-files` off and no network | manual |
| Total file size < 10 MB | `stat` |

## Style requirements

- Use a sans-serif system font stack (no web font fetches).
- Two distinguishable variant colors used CONSISTENTLY across every chart (e.g., A = `#4C78A8`, B = `#F58518`).
- Significance is visually flagged: `p < 0.05` cells get a subtle background color (e.g., light green for positive lift, light red for negative); `p ≥ 0.05` cells stay neutral.
- Tables: zebra-striped, sortable, with sticky headers when scrolling within the section.

## Prohibited content

- No raw rounds-per-correlation_id histograms (out of scope for v1).
- No action_type breakdowns (out of scope for v1).
- No `ots_matched_hotels.csv` data.
- No "TODO", "FIXME", or NEEDS CLARIFICATION markers in the rendered report.
