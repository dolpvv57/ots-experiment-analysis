# Quickstart: Chat-box-auto-open Experiment Analysis

**Feature**: 001-chat-box-auto-open-analysis

This guide walks a developer through setting up the environment, running the analysis, and verifying the output.

---

## Prerequisites

- Python 3.11+
- macOS or Linux
- ~16 GB RAM (the four CSVs total ~750 MB; loading all of them in pandas with explicit dtypes uses 2–3 GB)
- The four input CSVs already in place at `Chat-box-auto-open/data/` (this is the case in the repo)
- A modern web browser (Chrome, Firefox, Safari) for viewing the output

---

## Step 1 — Create a virtualenv and install dependencies

```bash
cd /Users/becky.ding/Documents/Bamboo/OTS/analyze-experiment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

`requirements.txt` (created during implementation) pins:

```text
pandas>=2.0,<3.0
scipy>=1.11,<2.0
statsmodels>=0.14,<0.15
plotly>=5.18,<6.0
jinja2>=3.1,<4.0
pytest>=7.4,<8.0
```

---

## Step 2 — Run the analysis

```bash
python -m analysis.main --verbose
```

Expected stderr (timings approximate):

```text
[load]      8,558,047 rows in 4 files (12.3s)
[validate]  3 utids excluded for variant conflict (0.4s)
[engage]    8 metrics computed (1.1s)
[redirect]  4 metrics computed (1.5s)
[stats]     13 tests run (0.2s)
[trends]    4 daily charts computed (0.3s)
[render]    report.html written (1.8s, 5.4 MB)
[done]      total 21.6s
```

Exit code 0 on success.

Output: `specs/001-chat-box-auto-open-analysis/report.html`.

---

## Step 3 — Open the report

```bash
open specs/001-chat-box-auto-open-analysis/report.html       # macOS
xdg-open specs/001-chat-box-auto-open-analysis/report.html   # Linux
```

You should see, in order:

1. **Executive Summary** — one paragraph + a **SHIP / DO NOT SHIP / INCONCLUSIVE** verdict.
2. **Data Overview** — date range, variant populations, excluded-utid count.
3. **Engagement Analysis** — table of 8 metrics + 8 bar charts + 1 rounds table + 2 daily-trend charts.
4. **Redirect Analysis** — table of 4 metrics + 4 bar charts + funnel-rate table + 2 daily-trend charts.
5. **Appendix** — methodology, statistical tests list, multiple-comparisons disclosure, excluded-data list.

---

## Step 4 — Verify self-containment (FR-015)

```bash
# Disable network and re-open the file
networksetup -setairportpower en0 off  # macOS only — flips Wi-Fi off
open specs/001-chat-box-auto-open-analysis/report.html
# All charts and styles must render. If anything breaks, that's a bug.
networksetup -setairportpower en0 on
```

Or simply: copy the HTML to `/tmp/`, change directory away from the project, and open it. It must render identically.

---

## Step 5 — Run the tests

```bash
pytest tests/ -v
```

The test suite (built during implementation) covers:

- `test_load.py` — variant-conflict detection, CSV schema validation
- `test_engagement.py` — engagement metric math against tiny fixtures
- `test_redirects.py` — redirect-join correctness, INTENT-only filtering, denominator rules
- `test_stats.py` — z-test and Welch's t-test with known-answer fixtures
- `test_trends.py` — daily-aggregate correctness, empty-session-id exclusion rule

---

## Sanity checks the report itself surfaces

The report's Data Overview section lets you cross-check the inputs without re-running the script:

| Sanity check | Where in the report |
|--------------|---------------------|
| Date range matches the CSV `dt` columns | Data Overview > Date range |
| utid counts per variant match `ots_chat.csv` distinct utids | Data Overview > Variant populations |
| Suggestions volume should be much larger than interactions | Engagement table → CHAT_TYPE_SUGGESTIONS row vs CHAT_TYPE_INTENT_RECOGNITION row |
| Redirect rate should be < ~30% (typical for chat-driven funnels) | Redirect table |
| Daily trends shouldn't drop to zero on any single day | Daily-trend charts |

If any of those look wrong, check Appendix > Excluded data first, then re-run with `--verbose` to see per-stage timings.

---

## Common pitfalls

- **Memory pressure**: if your machine has < 16 GB RAM and you also have other heavy apps open, the load step may swap. Close other apps and re-run.
- **Mojibake in the HTML**: the report is UTF-8; if your browser opens it with a different encoding, force UTF-8.
- **Stale virtualenv**: if you previously installed pandas 1.x, reinstall fresh — the analysis assumes pandas 2.x dtype semantics.

---

## Next steps after the report is generated

1. Review the SHIP / DO NOT SHIP verdict in the Executive Summary.
2. Sanity-check the Data Overview (variant populations should be roughly balanced).
3. Read the Engagement table — focus on per-user INTENT_RECOGNITION rate (the headline metric).
4. Read the Redirect table — focus on per-user redirect rate.
5. Look at the daily-trend charts to see whether the effect was stable or driven by one week.
6. Read the Appendix multiple-comparisons disclosure before reporting any borderline-significant finding to stakeholders.
