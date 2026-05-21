# Feature Specification: Chat-box-auto-open Experiment Analysis

**Feature Branch**: `001-chat-box-auto`
**Created**: 2026-05-21
**Status**: Draft
**Input**: User description: "Chat-box-auto-open A/B experiment analysis covering engagement and redirect metrics, output as an HTML report with text + charts."

## Clarifications

### Session 2026-05-21

- Q: Which statistical test method should be used for significance testing? → A: Two-proportion z-test for rate metrics, Welch's t-test for the `rounds` mean; report p-value AND 95% confidence interval for the lift; α = 0.05.
- Q: How should multiple-comparisons correction be handled across the ~13 tests? → A: No correction; report raw p-values and add an appendix note disclosing that with 13 tests at α=0.05 the expected false-positive count is ≈ 0.65.
- Q: Which metrics get daily trend charts and how should they be laid out? → A: Four daily-trend charts total — Engagement-absolute (daily INTENT_RECOGNITION volume), Engagement-ratio (daily INTENT_RECOGNITION ÷ SUGGESTIONS), Redirect-absolute (daily redirect count, INTENT_RECOGNITION-only), Redirect-ratio (daily redirect ÷ INTENT_RECOGNITION). Each chart contains two side-by-side sub-panels for the `utid` and `chat_session_id` aggregation dimensions, with one line per variant on each sub-panel.
- Q: Should `actions.csv` be loaded and used for variant-consistency validation (FR-003) and the funnel-rate denominator (FR-013)? → A: No. Drop `actions.csv` from this analysis entirely. Variant labels are taken from `ots_chat.csv` only. The FR-013 funnel-rate denominator is `distinct utids per variant in ots_chat.csv` (users who at least had one chat event of either type). Variant-consistency cross-checking has already been validated upstream and is out of scope here.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Engagement Between Control and Treatment (Priority: P1)

A product analyst needs to know whether automatically opening the chat box on the day-view page (variant B) increases user engagement with the chat feature compared to the existing manual-open behavior (variant A). They open the generated HTML report and immediately see, for each engagement metric, the values for variant A and variant B side-by-side, the absolute and relative difference, and a clear verdict on which variant performed better.

**Why this priority**: Engagement is the primary success signal for the experiment. If auto-open does not lift engagement, the rest of the analysis is moot — this story alone delivers a viable MVP that answers the core question "did opening the chat box automatically get more users to use it?".

**Independent Test**: Can be fully tested by loading the HTML report in a browser and verifying that engagement metrics for both variants are clearly displayed with comparison numbers, charts, and a written interpretation — without needing the redirect analysis to be present.

**Acceptance Scenarios**:

1. **Given** the experiment data files (actions.csv, ots_chat.csv, redirects.csv) are available, **When** the analyst opens the generated HTML report, **Then** they see total chat volume (CHAT_TYPE_SUGGESTIONS rows) and interaction volume (CHAT_TYPE_INTENT_RECOGNITION rows) for each variant, broken down by all four aggregation dimensions: utid, chat_session_id, request_id, correlation_id.
2. **Given** the engagement section is rendered, **When** the analyst reviews each metric, **Then** they see absolute counts per variant, the per-user (or per-session/per-request) average, the relative lift of B over A as a percentage, and a chart visualizing the comparison.
3. **Given** variant A and variant B may have different user counts, **When** engagement metrics are computed, **Then** rates are normalized (e.g., interactions per user, interaction rate per session) so the variants are comparable even if the population sizes differ.
4. **Given** the analyst wants to verify the result is not noise, **When** they read the engagement section, **Then** a written interpretation states whether the difference between A and B is meaningful and large enough to act on.

---

### User Story 2 - Compare Redirect Conversion Between Control and Treatment (Priority: P1)

The analyst also needs to know whether the chat interactions that happened in the experiment actually led to partner redirects (the downstream business outcome). In the same HTML report they scroll to the redirect section and see, for chat interactions only (CHAT_TYPE_INTENT_RECOGNITION), what fraction matched a redirect event in redirects.csv (via correlation_id ↔ pre_redirect_id), broken down by the same four aggregation dimensions, with A vs B comparison.

**Why this priority**: Engagement without conversion does not justify shipping the change. This is co-equal with Story 1 — together they answer "did auto-open drive more chat use AND did that chat use lead to bookings/redirects?".

**Independent Test**: Can be fully tested by loading the HTML report and verifying that the redirect section shows redirect counts and rates for variant A and variant B at each aggregation dimension, with both numeric tables and visual charts, even if the engagement section is not yet rendered.

**Acceptance Scenarios**:

1. **Given** ots_chat.csv and redirects.csv, **When** the redirect analysis runs, **Then** it considers only rows where chat_type = CHAT_TYPE_INTENT_RECOGNITION and joins them to redirects.csv on correlation_id = pre_redirect_id, treating any match as "redirected".
2. **Given** the join is complete, **When** redirect rates are computed, **Then** the report shows redirect rate at each aggregation level: % of users who had at least one redirected chat, % of chat sessions that produced a redirect, % of request_ids that produced a redirect, and % of correlation_ids that matched a redirect.
3. **Given** the analyst opens the redirect section, **When** they look at each dimension, **Then** they see variant A rate, variant B rate, absolute difference (B − A), relative lift (B/A − 1), and a chart comparing the two variants.
4. **Given** an analyst wants to know whether higher engagement translated to higher conversion, **When** they read the redirect section, **Then** the report explicitly states whether the redirect rate moved in the same direction as engagement (e.g., "engagement up, redirect rate flat" vs "engagement up, redirect rate also up").

---

### User Story 3 - Single Self-Contained HTML Report (Priority: P2)

The analyst wants to share results with non-technical stakeholders by sending them one file. They generate the report once and email the resulting HTML file to product, design, and partners. Recipients open it in any modern browser without needing Python, Jupyter, an internet connection, or external assets.

**Why this priority**: Without portable distribution, the analysis is hard to socialize. This is P2 because the analysis itself (P1) must exist first — but a notebook-only result is not acceptable as the final deliverable.

**Independent Test**: Can be tested by moving the HTML file to a different machine with no project files and no network access, opening it in a browser, and verifying that all text, tables, and charts render correctly.

**Acceptance Scenarios**:

1. **Given** the report is generated, **When** the file is opened with no internet, **Then** all charts and styling render without broken images or missing fonts (charts and styles must be inlined or embedded).
2. **Given** the report is opened, **When** the reader scrolls through it, **Then** they encounter, in order: an executive summary with the headline result, the engagement section, the redirect section, and an appendix listing data assumptions, sample sizes, and caveats.
3. **Given** the report is shown to a non-technical stakeholder, **When** they read the executive summary alone, **Then** they can state whether the experiment was a win, loss, or inconclusive without reading the rest.

---

### Edge Cases

- **Empty session_id rows**: ots_chat.csv contains rows with blank chat_session_id (auto-generated suggestions before the user opens the chat). These rows must still count toward CHAT_TYPE_SUGGESTIONS volume but must be excluded from any per-session aggregation that requires a non-empty chat_session_id.
- **Same row appearing in both chat_types**: A correlation_id may appear in both CHAT_TYPE_SUGGESTIONS and CHAT_TYPE_INTENT_RECOGNITION. The redirect analysis must scope the join to INTENT_RECOGNITION only to avoid double-counting suggestions as user-initiated interactions.
- **Users present in actions.csv but not in ots_chat.csv**: Some variant A or B users in the experiment never triggered a chat event. They should still be counted in the variant's user denominator when computing per-user rates so engagement is not artificially inflated.
- **Redirect rows with no matching chat row**: redirects.csv may contain pre_redirect_ids that do not appear in the filtered chat data. These are out of scope for chat-attributed redirects and should be excluded from numerator counts (but must not error out the join).
- **Highly skewed users**: A small number of utids may produce a disproportionate share of chat events. The report must surface per-user medians or the share of activity from the top 1% of users so a reader can judge whether means are distorted by outliers.
- **Variant imbalance**: Variant A and B will not have identical user counts. Every absolute count must be paired with a normalized rate (per user, per session, etc.) so variants remain comparable.
- **Date range coverage**: The data spans multiple `dt` values. The report must state the exact date range analyzed and flag any day where one variant's data is unexpectedly missing.

## Requirements *(mandatory)*

### Functional Requirements

#### Data Loading and Preparation

- **FR-001**: System MUST load two CSV files from `Chat-box-auto-open/data/`: `ots_chat.csv` and `redirects.csv`. `actions.csv` and `ots_matched_hotels.csv` are explicitly out of scope and MUST NOT be loaded for this analysis. (Variant labels are read from `ots_chat.csv`; `redirects.csv` carries no variant column and inherits variant via the join on `correlation_id`.)
- **FR-002**: System MUST report, for each loaded file, the row count, date range (`dt` min/max), and distinct count of `utid` (and `variant` for `ots_chat.csv`) so the analyst can sanity-check the inputs.
- **FR-003**: Variant-consistency cross-file validation is OUT OF SCOPE for this analysis (per Clarifications session 2026-05-21). Variant labels are sourced from `ots_chat.csv` only; if a single utid appears with both A and B labels within `ots_chat.csv`, those rows MUST still be reported as "variant-conflict" rows in the appendix and excluded from comparative analysis.

#### Engagement Analysis

- **FR-004**: For each variant (A, B), system MUST compute total CHAT_TYPE_SUGGESTIONS volume and total CHAT_TYPE_INTENT_RECOGNITION volume aggregated at four levels: by utid, by chat_session_id, by request_id, and by correlation_id.
- **FR-005**: For each engagement metric, system MUST report both raw counts and normalized rates: counts per user (sum / unique users in that variant), per session, per request, etc., so variants of different sizes are directly comparable.
- **FR-006**: System MUST compute the absolute difference (B − A) and relative lift ((B − A) / A) for every engagement metric, expressed as both a number and a percentage.
- **FR-007**: System MUST flag, in plain language, whether the observed difference is "directionally positive for B", "directionally negative for B", or "essentially flat" using a documented threshold (e.g., relative lift of less than ±2% considered flat); the threshold MUST be stated in the report.
- **FR-008**: For the rounds metric (conversation length), system MUST additionally report the average and median rounds per chat_session_id for each variant, since auto-open might affect not only whether users chat but how long they chat.

#### Redirect Analysis

- **FR-009**: System MUST filter ots_chat.csv to chat_type = CHAT_TYPE_INTENT_RECOGNITION before computing any redirect metric (suggestions are excluded from redirect attribution).
- **FR-010**: System MUST mark a chat row as "redirected" if and only if its correlation_id appears as a pre_redirect_id in redirects.csv.
- **FR-011**: For each variant, system MUST compute redirect rate at each of four aggregation levels:
  - **Per user**: % of utids with ≥1 redirected interaction-chat among utids with ≥1 interaction-chat.
  - **Per session**: % of chat_session_ids with ≥1 redirected correlation_id.
  - **Per request**: % of request_ids with ≥1 redirected correlation_id.
  - **Per correlation_id**: % of interaction-chat correlation_ids with a matching redirect.
- **FR-012**: System MUST report variant A rate, variant B rate, absolute difference, and relative lift for each of the four redirect rates above, in both a table and a chart.
- **FR-013**: System MUST report per-user redirect rate using the population of *all chat users in that variant* (denominator = distinct utids per variant in `ots_chat.csv`, i.e. users who had at least one chat event of either type), as a secondary metric, so the reader can see funnel-level impact among the population that actually saw the chat surface.

#### Statistical Significance

- **FR-SIG-001**: For every rate-type metric (engagement counts normalized to per-user / per-session / per-request rates, and all four redirect rates), system MUST run a two-proportion z-test comparing variant A and variant B and report the resulting p-value alongside the lift figure.
- **FR-SIG-002**: For the `rounds` mean (average rounds per chat_session_id) system MUST run Welch's t-test (unequal variances assumed) comparing variant A and variant B and report the resulting p-value.
- **FR-SIG-003**: For every test in FR-SIG-001 and FR-SIG-002, system MUST also report the 95% confidence interval for the lift (B − A for absolute difference; B/A − 1 for relative lift), expressed in the same units as the metric itself.
- **FR-SIG-004**: System MUST use significance level α = 0.05. A metric is flagged "statistically significant" if and only if p < 0.05; otherwise it is flagged "not significant" and the report MUST avoid claims of impact for that metric in the executive summary.
- **FR-SIG-005**: For every metric, the report MUST present, side by side, three values: the directional verdict from FR-007 (positive / negative / flat), the p-value, and the 95% CI. The Executive Summary MUST only recommend "ship" if the headline metric is both directionally positive AND statistically significant.
- **FR-SIG-006**: System MUST NOT apply multiple-comparisons correction (no Bonferroni, no Benjamini-Hochberg). Raw p-values are reported as-is.
- **FR-SIG-007**: The Appendix MUST include a "Multiple comparisons" subsection that states the total number of tests run and the expected false-positive count at α=0.05 (e.g., "13 tests × 0.05 ≈ 0.65 expected false positives if all nulls were true"), so readers can calibrate borderline-significant findings appropriately.

#### Daily Trend Charts

- **FR-TREND-001**: System MUST produce exactly four daily-trend charts (one chart per logical metric), each grouped by date (`dt`) on the x-axis:
  - **Chart 1 — Engagement-absolute**: daily INTENT_RECOGNITION volume.
  - **Chart 2 — Engagement-ratio**: daily INTENT_RECOGNITION ÷ SUGGESTIONS (interaction-to-suggestion conversion rate).
  - **Chart 3 — Redirect-absolute**: daily count of redirect-attributed events, computed only from chat rows where chat_type = CHAT_TYPE_INTENT_RECOGNITION.
  - **Chart 4 — Redirect-ratio**: daily redirect count ÷ INTENT_RECOGNITION count, denominator restricted to CHAT_TYPE_INTENT_RECOGNITION rows (consistent with FR-009).
- **FR-TREND-002**: Each of the four trend charts MUST be presented as two side-by-side sub-panels representing two aggregation dimensions:
  - **Left sub-panel**: aggregation by `utid` (distinct user IDs per day).
  - **Right sub-panel**: aggregation by `chat_session_id` (distinct chat sessions per day; rows with empty `chat_session_id` are excluded from this sub-panel only, per Edge Cases).
- **FR-TREND-003**: Each sub-panel MUST display exactly two lines — one for variant A and one for variant B — both labeled in a legend, with consistent variant colors across all four trend charts.
- **FR-TREND-004**: For ratio charts (Charts 2 and 4), the daily numerator and denominator MUST be computed independently *within each day* (no carry-forward, no cumulative sums), and the denominator MUST be the same aggregation dimension as the numerator (e.g., distinct utids with INTENT_RECOGNITION on day X ÷ distinct utids with SUGGESTIONS on day X).
- **FR-TREND-005**: Trend charts MUST appear in their parent section: Charts 1 and 2 inside the Engagement Analysis section; Charts 3 and 4 inside the Redirect Analysis section. They are in addition to the static A-vs-B summary tables already required by FR-017.
- **FR-TREND-006**: Each chart MUST label both axes (x: "Date"; y: the metric name and unit), include a legend, and use the same date range as the rest of the report.

#### Reporting / Output

- **FR-014**: System MUST produce a single self-contained HTML file (`report.html`) at the feature directory root.
- **FR-015**: The HTML file MUST be self-contained: charts, fonts, and styles required for rendering MUST be embedded so the file opens correctly without internet access and without other local files.
- **FR-016**: The HTML report MUST be structured with these sections in this order: (1) Executive Summary, (2) Data Overview, (3) Engagement Analysis (including the two engagement daily-trend charts from FR-TREND-001), (4) Redirect Analysis (including the two redirect daily-trend charts from FR-TREND-001), (5) Appendix (assumptions, caveats, methodology, sample sizes, multiple-comparisons disclosure).
- **FR-017**: Each metric MUST be presented with both a numeric table and at least one chart (e.g., grouped bar chart of A vs B); charts MUST be labeled with axis titles, units, and a legend identifying variants.
- **FR-018**: The Executive Summary MUST state, in two to four sentences, the headline finding for engagement and the headline finding for redirects, and recommend "ship", "do not ship", or "inconclusive — needs more data".
- **FR-019**: The Appendix MUST list: exact date range covered, total utids per variant, definitions of every metric, the redirect-flat threshold used, and any rows excluded with the reason for exclusion.

### Key Entities *(include if feature involves data)*

- **Chat Event**: A row in ots_chat.csv. Two distinct kinds: SUGGESTIONS (auto-generated when the user enters day view) and INTENT_RECOGNITION (user actively interacted). Each chat event has a correlation_id that links to backend requests; multiple correlation_ids share a request_id; multiple chat events share a chat_session_id; chat events are owned by a utid.
- **Redirect Event**: A row in redirects.csv representing a partner-redirect click. Linked back to the chat that produced it via pre_redirect_id = chat.correlation_id. `redirects.csv` carries no `variant` column; variant is inferred from the joined chat row.
- **Variant Assignment**: The mapping utid → A or B, sourced from `ots_chat.csv` (every chat row carries a variant). Defines who is in control vs treatment.
- **Aggregation Dimension**: One of {utid, chat_session_id, request_id, correlation_id} — the four granularity levels at which both engagement and redirect metrics are computed and compared.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader can determine whether to ship the auto-open change by reading the executive summary alone — the summary states win/loss/inconclusive within the first 4 sentences.
- **SC-002**: All eight engagement metrics (2 chat_types × 4 aggregation dimensions) are present in the report with variant A value, variant B value, absolute difference, and relative lift, with no missing or "N/A" values for either variant.
- **SC-003**: All four redirect rates (one per aggregation dimension) are present in the report with variant A rate, variant B rate, absolute difference, and relative lift, computed only from CHAT_TYPE_INTENT_RECOGNITION rows.
- **SC-004**: The HTML report opens correctly in a modern browser with no internet connection and no external dependencies (verified by opening the file from a different directory with the network disabled).
- **SC-005**: The data overview section confirms the analyzed date range matches the date range present in the source files (no silent dropping of dates).
- **SC-006**: The number of variant A and variant B users reported in the appendix equals the count of distinct utids per variant in `ots_chat.csv`.
- **SC-007**: A non-technical stakeholder (product manager unfamiliar with the data) can read the report end-to-end and answer the question "did auto-open improve chat usage and partner redirects?" without asking follow-up questions about methodology.

## Assumptions

- **Data freshness**: The four CSV files in `Chat-box-auto-open/data/` are the final, complete experiment dataset. No live data refresh is needed; the analysis is one-shot.
- **Variant labels**: `A` always means control (manual-open, status quo) and `B` always means treatment (auto-open). This is consistent with the user's description.
- **Population definition**: The set of "variant A users" and "variant B users" is the set of distinct utids appearing with that variant label in `ots_chat.csv`. Users who never produced any chat event are not counted, even if they would appear in `actions.csv`. No additional eligibility filter (country, device, etc.) is applied.
- **Statistical testing**: Significance testing is in scope (per FR-SIG-001..005). Rate metrics use a two-proportion z-test; the `rounds` mean uses Welch's t-test; α = 0.05; both p-values and 95% CIs are reported.
- **Date scope**: The analysis covers the full date range present in the data; no date trimming for ramp-up or warm-up periods is applied unless the data overview reveals an obvious anomaly.
- **Aggregation semantics**: At per-session / per-request / per-correlation_id levels, "engagement" means "count of distinct IDs at that level that have ≥1 row of the relevant chat_type". For "redirect rate per X", the numerator is "distinct Xs with ≥1 matched redirect" and the denominator is "distinct Xs with ≥1 INTENT_RECOGNITION row".
- **Charting library**: A Python plotting library that supports embedding charts directly in HTML (e.g., as inline SVG or self-contained interactive HTML) will be used so FR-015 (self-contained file) holds. Specific library choice is left to the implementation.
- **Outliers**: Outlier handling beyond surfacing top-1% concentration in the appendix (FR — Edge Cases) is out of scope for v1.
- **Out of scope**: `actions.csv` is NOT loaded by this analysis (per Clarifications session 2026-05-21); `ots_matched_hotels.csv` is not analyzed. action_type breakdowns (sort, filter, map move) are not analyzed in v1 — only chat-related engagement and redirects.
- **In scope (per Clarifications session)**: Daily trend charts are now in scope per FR-TREND-001..006 (4 charts, 2 sub-panels each: utid + chat_session_id). Aggregation dimensions for trend charts are restricted to `utid` and `chat_session_id`; trend charts at `request_id` and `correlation_id` granularity are out of scope (those dimensions remain in the static A-vs-B summary tables only).
