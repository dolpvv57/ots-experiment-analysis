# Phase 1 Data Model: Chat-box-auto-open Experiment Analysis

**Feature**: 001-chat-box-auto-open-analysis
**Date**: 2026-05-21

This document specifies the schemas of the input CSV files, the in-memory derived entities the analysis operates on, and the final result objects rendered into the HTML report.

---

## 1. Input CSV schemas

Two CSVs are loaded from `Chat-box-auto-open/data/`. Both are read-only. `actions.csv` and `ots_matched_hotels.csv` are intentionally NOT loaded by this analysis (per Clarifications session 2026-05-21).

### 1.1 `ots_chat.csv`

| Column | Type | Notes |
|--------|------|-------|
| `dt` | date | Day of the chat event |
| `utid` | string (UUID) | User id |
| `chat_session_id` | string (UUID) or empty | Empty for `CHAT_TYPE_SUGGESTIONS` rows where the user has not yet opened the chat |
| `chat_type` | enum {`CHAT_TYPE_SUGGESTIONS`, `CHAT_TYPE_INTENT_RECOGNITION`} | |
| `rounds` | integer | 0 for `CHAT_TYPE_SUGGESTIONS`; ≥1 for `CHAT_TYPE_INTENT_RECOGNITION` |
| `request_id` | string (UUID) | Cache-refreshing request id (one-to-many with `correlation_id`) |
| `correlation_id` | string (UUID) | Backend-request id; joins to `redirects.pre_redirect_id` |
| `variant` | enum {`A`, `B`} | |

**Used by analysis for**: all engagement metrics (Section 3), all variant labels (it is the only source of truth for `utid → variant`), and as the left side of the redirect join (Section 4).

### 1.2 `redirects.csv`

| Column | Type | Notes |
|--------|------|-------|
| `dt` | date | Day of the redirect |
| `utid` | string (UUID) | User who clicked the partner link |
| `pre_redirect_id` | string (UUID) | Equal to `ots_chat.correlation_id` of the chat row that triggered this redirect |

**Note**: `redirects.csv` does NOT carry a `variant` column. Variant is inferred via the join to `ots_chat.csv` on `correlation_id == pre_redirect_id`.

**Used by analysis for**: marking which `correlation_id`s in `ots_chat.csv` (filtered to `CHAT_TYPE_INTENT_RECOGNITION`) led to a partner redirect.

---

## 2. Derived entities (in-memory only)

### 2.1 `variant_lookup: pd.Series[utid → {A, B}]`

Built from `(utid, variant)` pairs in `ots_chat.csv` only. If a single `utid` appears with both `A` and `B` labels within `ots_chat`, those rows are reported as "in-file conflict" and dropped (per FR-003 as scoped to ots_chat-only).

### 2.2 `excluded_utids: set[str]`

Set of utids excluded from comparative analysis due to in-file variant conflict in `ots_chat.csv`. Expected to be empty or near-empty in practice. Recorded in the Appendix per FR-019.

### 2.3 `variant_population: dict[str, int]`

`{ "A": <count of distinct utids in ots_chat with variant=A>, "B": <count of distinct utids in ots_chat with variant=B> }`, after `excluded_utids` are removed. Used as the denominator for per-user rates (FR-005, FR-013). Per spec, this is "users who had at least one chat event of either type".

### 2.4 `chat_with_variant: pd.DataFrame`

`ots_chat` with `excluded_utids` filtered out. Schema unchanged from input.

### 2.5 `chat_interaction: pd.DataFrame`

Subset of `chat_with_variant` where `chat_type == "CHAT_TYPE_INTENT_RECOGNITION"`. Used for redirect attribution (FR-009).

### 2.6 `redirect_attributed: pd.DataFrame`

Inner join: `chat_interaction` ⨝ `redirects` on `chat_interaction.correlation_id == redirects.pre_redirect_id`. One row per attributed redirect, carrying `utid`, `chat_session_id`, `request_id`, `correlation_id`, `variant`, `dt`. Variant is inherited from the `chat_interaction` side; the `redirects.csv` `dt` and `utid` columns are not used for the join.

---

## 3. Engagement metric results

For each `chat_type ∈ {CHAT_TYPE_SUGGESTIONS, CHAT_TYPE_INTENT_RECOGNITION}` and each `dimension ∈ {utid, chat_session_id, request_id, correlation_id}`:

```
EngagementMetric {
  chat_type: str
  dimension: str
  value_A: float        # rate per user (or per session, etc.) for variant A
  value_B: float
  count_A: int          # distinct count of `dimension` with ≥1 row of this chat_type, variant A
  count_B: int
  abs_diff: float       # value_B - value_A
  rel_lift_pct: float   # 100 * (value_B - value_A) / value_A
  p_value: float        # two-proportion z-test p-value
  ci_low: float         # 95% CI lower bound for the lift
  ci_high: float        # 95% CI upper bound
  directional_verdict: enum {"positive", "flat", "negative"}   # per FR-007 (±2% threshold)
  significance_verdict: enum {"significant", "not_significant"}  # p < 0.05 (FR-SIG-004)
}
```

Total: 2 chat_types × 4 dimensions = **8 EngagementMetric rows**.

Plus one additional `RoundsMetric` for the `rounds` mean per session (FR-008):

```
RoundsMetric {
  metric: "rounds_per_session"
  mean_A: float
  mean_B: float
  median_A: float
  median_B: float
  abs_diff_mean: float
  rel_lift_mean_pct: float
  p_value: float        # Welch's t-test
  ci_low: float
  ci_high: float
  directional_verdict: ...
  significance_verdict: ...
}
```

---

## 4. Redirect metric results

For each `dimension ∈ {utid, chat_session_id, request_id, correlation_id}`:

```
RedirectMetric {
  dimension: str
  rate_A: float                # numerator_A / denominator_A
  rate_B: float
  numerator_A: int             # distinct dimension values with ≥1 redirected interaction
  numerator_B: int
  denominator_A: int           # distinct dimension values with ≥1 INTENT_RECOGNITION row, variant A
  denominator_B: int
  abs_diff: float              # rate_B - rate_A (in percentage points)
  rel_lift_pct: float
  p_value: float
  ci_low: float
  ci_high: float
  directional_verdict: ...
  significance_verdict: ...
}
```

Total: 4 dimensions = **4 RedirectMetric rows**.

Plus one `RedirectFunnelMetric` per FR-013:

```
RedirectFunnelMetric {
  metric: "redirect_rate_per_all_users"
  rate_A: float        # utids in variant A with ≥1 attributed redirect / variant_population["A"]
  rate_B: float
  ... same fields as RedirectMetric ...
}
```

---

## 5. Daily trend table results (per FR-TREND-001..006)

Four `DailyTrend` objects, one per chart:

```
DailyTrend {
  chart_id: enum {"engagement_abs", "engagement_ratio", "redirect_abs", "redirect_ratio"}
  utid_panel:           pd.DataFrame  # columns: dt, variant, value
  chat_session_panel:   pd.DataFrame  # columns: dt, variant, value
}
```

Per-chart computation rules:

| chart_id | utid_panel.value (per (dt, variant)) | chat_session_panel.value (per (dt, variant)) |
|----------|--------------------------------------|----------------------------------------------|
| `engagement_abs`   | distinct count of utids with ≥1 INTENT_RECOGNITION on that day | distinct count of chat_session_ids with ≥1 INTENT_RECOGNITION on that day (chat_session_id ≠ empty) |
| `engagement_ratio` | (above utid count) / (distinct count of utids with ≥1 SUGGESTIONS on that day) | (above session count) / (distinct count of chat_session_ids with ≥1 SUGGESTIONS on that day) |
| `redirect_abs`     | distinct count of utids with ≥1 attributed redirect on that day | distinct count of chat_session_ids with ≥1 attributed redirect on that day |
| `redirect_ratio`   | (above utid count) / (utid_panel.value of `engagement_abs` for the same (dt, variant)) | (above session count) / (chat_session_panel.value of `engagement_abs` for the same (dt, variant)) |

Empty `chat_session_id` rows are dropped only from `chat_session_panel` (per spec Edge Cases), never from `utid_panel`.

---

## 6. Report context (input to Jinja template)

```
ReportContext {
  generated_at: datetime
  date_range: tuple[date, date]
  variant_population: dict[str, int]
  excluded_utids_count: int
  flat_threshold_pct: float = 2.0       # for FR-007 directional verdict
  alpha: float = 0.05
  total_tests: int = 13                 # for FR-SIG-007 disclosure
  expected_false_positives: float       # alpha * total_tests

  engagement_metrics: list[EngagementMetric]   # 8 entries
  rounds_metric: RoundsMetric                  # 1 entry
  redirect_metrics: list[RedirectMetric]       # 4 entries
  redirect_funnel_metric: RedirectFunnelMetric # 1 entry

  trend_charts: list[DailyTrend]               # 4 entries

  static_chart_html: dict[str, str]            # metric_id -> Plotly HTML <div>
  trend_chart_html: dict[str, str]             # chart_id -> Plotly HTML <div>

  exec_summary: dict {
    headline_engagement: str       # one-sentence verdict
    headline_redirect: str         # one-sentence verdict
    recommendation: enum {"ship", "do_not_ship", "inconclusive"}
    rationale: str                 # 2-4 sentences
  }
}
```

---

## 7. Validation rules summary

| Rule | Source | Enforcement point |
|------|--------|-------------------|
| Each `utid` in `ots_chat.csv` → exactly one `variant` (in-file consistency only) | FR-003 (scoped) | `analysis/load.py` builds `variant_lookup` and exclusion set |
| Empty `chat_session_id` excluded from per-session aggregates only | Edge Cases | `analysis/engagement.py` and `analysis/trends.py` |
| Redirect join uses ONLY `CHAT_TYPE_INTENT_RECOGNITION` rows | FR-009 | `analysis/redirects.py` |
| Per-user rate denominator = `variant_population[v]` (= distinct utids in `ots_chat` with that variant) | FR-013 | `analysis/redirects.py` for funnel metric |
| `flat_threshold_pct = 2.0` declared in report Appendix | FR-007 | `analysis/render.py` includes this in the rendered template |
| `alpha = 0.05`, no correction | FR-SIG-004, FR-SIG-006 | `analysis/stats.py` constants |
| Date range from min/max of `dt` across loaded files | FR-002 | `analysis/load.py` |
