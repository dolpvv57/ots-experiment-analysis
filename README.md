# ots-experiment-analysis

A/B experiment analysis framework: generates a single self-contained HTML report from CSV data.

Each experiment has its own data directory and shares the core analysis framework (engagement / redirect / statistical tests). 
Experiments can optionally attach a "plugin" to add experiment-specific analysis sections.

---

## Directory Structure

```
analyze-experiment/
├── analysis/                    # Shared framework 
│   ├── plugin.py                # Plugin interface definition 
│   ├── main.py                  # CLI entry point; auto-discovers and runs experiment plugins
│   ├── load.py                  # Loads CSVs
│   ├── engagement.py            # Engagement metrics 
│   ├── redirects.py             # Redirect rate metrics 
│   ├── stats.py                 # Welch t-test, z-test, confidence intervals
│   ├── render.py                # Plotly charts + Jinja2 rendering
│   ├── types.py                 # Shared dataclass types
│   └── templates/
│       └── report.html.j2       # Main report template (engagement + redirect)
│
├── chat-box-auto-open/          # Example experiment directory (with plugin)
│   ├── data/                    # ots_chat.csv, redirects.csv, actions.csv
│   ├── output/                  # report.html (generated after running)
│   ├── plugin.py                # Experiment-specific analysis
│   └── templates/
│       └── section.html.j2      # Experiment-specific report section
│
├── ai-filter-entrance/          # Example experiment directory (with plugin)
│   ├── data/
│   ├── output/
│   ├── plugin.py                # Experiment-specific analysis
│   └── templates/
│       └── section.html.j2
│
├── tests/                       # Unit tests (cover the shared framework)
└── requirements.txt
```

---

## Quick Start (Generating a Report)

**1. Create a virtual environment and install dependencies** 

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

**2. Run the analysis**

```bash
# Analyze the ai-filter-entrance experiment (default)
python -m analysis.main --verbose

# Switch experiments by changing the --experiment flag
python -m analysis.main --experiment chat-box-auto-open --verbose
```

**3. View the report**

```bash
open <experiment-name>/output/report.html   # macOS
```

The report is written to `<experiment-name>/output/report.html`. 
The output directory is created automatically if it does not exist.


**Optional flags**

| Flag | Default | Description |
|------|---------|-------------|
| `--experiment` | `ai-filter-entrance` | Experiment directory name; data/output paths are derived from this |
| `--data-dir` | `<experiment>/data` | Override the input CSV directory |
| `--output` | `<experiment>/output/report.html` | Override the report output path |
| `--flat-threshold` | `2.0` | Relative lifts below this percentage (absolute) are treated as "flat" |
| `--alpha` | `0.05` | Statistical significance threshold |
| `--verbose` | off | Print timing for each stage to stderr |

**4. Run the tests**

```bash
pytest tests/ -v
```

---

## Report Contents

Every report includes:

- **Summary**: AI-generated verdict placeholder
- **Data overview**: row counts per file, distinct utids per variant from backend (ots_chat) and frontend (actions)
- **Engagement analysis**:
  - Block 1 — Backend chat engagement: INTENT_RECOGNITION rate per dimension (utid, request_id, correlation_id), A/B counts and rates with z-test
  - Block 2 — Rounds per session: mean and median rounds per INTENT session, Welch's t-test
  - Block 3 — Frontend funnel: load → click → chat rates per variant, z-test
- **Redirect analysis**:
  - Overall redirect: redirect rate across all users per dimension
  - From chat to redirect: redirect rate among INTENT_RECOGNITION users only per dimension
- **Experiment-specific section** (appended automatically if the experiment directory contains a `plugin.py`)
- **Appendix**: methodology notes, multiple-comparisons annotation, excluded utid count

---

## Adding a New Experiment (Developer Guide)

To add a new experiment, create files in your own directory. 
Do not modify any code under `analysis/`.

### Minimum structure

```
<your-experiment>/
├── data/
│   ├── ots_chat.csv
│   ├── redirects.csv
│   ├── actions.csv
│   └── <more data..>
└── output/             # created automatically
```

Without a `plugin.py`, the report contains only the standard engagement and redirect analysis. Run it directly:

```bash
python -m analysis.main --experiment <your-experiment>
```

### Adding an experiment-specific section (plugin)

To append a custom analysis section to the report, create `plugin.py` and `templates/section.html.j2` inside the experiment directory.

**`plugin.py` interface:**

```python
from __future__ import annotations
from dataclasses import dataclass
from analysis.load import DataBundle

# Required: Jinja2 template path, relative to this file's directory
TEMPLATE_FRAGMENT = "templates/section.html.j2"

# Required: run the analysis and return any dataclass
def compute(bundle: DataBundle, excluded_utids: set[str]) -> MySection:
    # bundle.ots_chat   — DataFrame from ots_chat.csv
    # bundle.redirects  — DataFrame from redirects.csv
    # bundle.data_dir   — path to the data/ directory (for reading other CSVs)
    # excluded_utids    — set of utids excluded due to variant conflicts
    ...

# Required: how many statistical hypothesis tests this section contributes
# (used for the total_tests annotation)
def count_tests(section: MySection) -> int:
    return len(section.some_metrics)

# Optional: return chart_id -> Plotly HTML div string
def build_charts(section: MySection) -> dict[str, str]:
    ...
```

**Variables available in `templates/section.html.j2`:**

| Variable | Type | Description |
|----------|------|-------------|
| `section` | `MySection` | Return value of `compute()` |
| `charts` | `dict[str, str]` | Return value of `build_charts()` (empty dict if no charts) |

All Jinja2 filters from the main template are available: `fmt_pct`, `fmt_pp`, `fmt_lift`, `fmt_p`, `fmt_num`.

**Example: minimal plugin**

```python
# my-experiment/plugin.py
from dataclasses import dataclass
from analysis.load import DataBundle

TEMPLATE_FRAGMENT = "templates/section.html.j2"

@dataclass(frozen=True)
class MySection:
    total_actions: int

def compute(bundle: DataBundle, excluded_utids: set[str]) -> MySection:
    actions = __import__("pandas").read_csv(bundle.data_dir / "actions.csv")
    return MySection(total_actions=len(actions))

def count_tests(section: MySection) -> int:
    return 0
```

```jinja2
{# my-experiment/templates/section.html.j2 #}
<section id="my-section">
<h2>My Custom Analysis</h2>
<p>Total actions: {{ section.total_actions }}</p>
</section>
```

---

## Data Notes

- Variant A: control group. 
- Variant B: treatment group.
- `ots_chat.csv`: built from backend data. Contains per-session chat fields, enriched with `request_id` and `correlation_id` via `hotel_result_event`, and with variant assignment via the experiment table. 
- `redirects.csv`: redirect event data. Linked to other tables via `(utid, correlation_id)`.
- `actions.csv`: built from frontend event data. Contains user behavior fields, enriched with variant assignment via the experiment table.

### ots_chat.csv fields

| Field | Description |
|-------|-------------|
| `utid` | User identifier |
| `chat_session_id` | Chat session ID (null when `chat_type` is `CHAT_TYPE_SUGGESTIONS`) |
| `chat_type` | `CHAT_TYPE_SUGGESTIONS` or `CHAT_TYPE_INTENT_RECOGNITION` |
| `rounds` | Number of max rounds in this session |
| `request_id` | Request ID (denotes every request that refreshes the cache) |
| `correlation_id` | Correlation ID (denotes every single request to backend) |
| `variant` | `A` or `B` |
| `dt` | Date |

### redirects.csv fields

| Field | Description |
|-------|-------------|
| `utid` | User identifier |
| `pre_redirect_id` | Corresponds to `ots_chat.correlation_id` |
| `dt` | Date |

### actions.csv fields

| Field | Description |
|-------|-------------|
| `utid` | User identifier |
| `action_type` | Frontend event type |
| `traffic_source` | Traffic source of the session |
| `chat_box_entry_loaded` | JSON payload for the load event |
| `chat_box_entry_click` | JSON payload for the click event |
| `variant` | `A` or `B` |
| `dt` | Date |

---

## Module Responsibilities

| File | Responsibility |
|------|----------------|
| `analysis/main.py` | CLI entry point; orchestrates the analysis pipeline; auto-discovers and runs `<experiment>/plugin.py` |
| `analysis/load.py` | Reads CSVs; builds variant lookup; excludes conflicting utids |
| `analysis/engagement.py` | 8 engagement metrics + rounds + daily trend |
| `analysis/redirects.py` | Redirect rate metrics (4 dimensions + funnel) + daily trend |
| `analysis/stats.py` | Two-proportion z-test, Welch t-test, 95% confidence intervals |
| `analysis/render.py` | Plotly charts + Jinja2 rendering; `build_map_rate_chart()` available for plugin reuse |
| `analysis/plugin.py` | `PluginSection` dataclass (used internally by the framework) |
| `analysis/types.py` | Shared types: `EngagementMetric`, `RedirectMetric`, etc. |
