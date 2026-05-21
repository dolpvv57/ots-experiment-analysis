# Contract: CLI Entry Point

**Module**: `analysis.main`
**Invocation**: `python -m analysis.main [options]`

This is the only externally-callable contract for this feature — there is no library API, no HTTP endpoint, no UI. The CLI runs the full pipeline end-to-end and writes `report.html`.

## Synopsis

```text
python -m analysis.main \
    [--data-dir <path>] \
    [--output <path>] \
    [--flat-threshold <float>] \
    [--alpha <float>] \
    [--verbose]
```

## Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--data-dir` | path | `Chat-box-auto-open/data/` (relative to repo root) | Directory containing `ots_chat.csv` and `redirects.csv`. Must exist; if either required file is missing, exit code 2. `actions.csv` and `ots_matched_hotels.csv` are ignored regardless of presence. |
| `--output` | path | `specs/001-chat-box-auto-open-analysis/report.html` | Destination HTML file. Parent directory must exist; the file is overwritten if present. |
| `--flat-threshold` | float | `2.0` | Relative-lift percentage below which `directional_verdict = "flat"` (per FR-007). |
| `--alpha` | float | `0.05` | Significance level (per FR-SIG-004). |
| `--verbose` | flag | off | Print per-stage progress and timing to stderr. |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success. `report.html` written. |
| 1 | Generic failure (uncaught exception). Stderr contains traceback. |
| 2 | Input data error: missing file, unreadable CSV, schema mismatch, or no rows after filtering. Stderr contains a clear, single-line diagnosis. |
| 3 | Validation failure: more than 50% of utids excluded due to variant conflict. Stderr contains the exclusion count. (This guard prevents a silently meaningless report.) |

## Outputs

### `report.html` (path from `--output`)

A single self-contained HTML file matching the contract in [`report-output.md`](report-output.md). Size: < 10 MB.

### Stderr (when `--verbose`)

Single-line progress markers, e.g.:

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

### Stdout

Empty on success. Errors go to stderr.

## Determinism

Same input CSVs + same arguments → byte-for-byte identical `report.html`, except for a `<meta name="generated_at" content="...">` tag in the HTML head and a "Generated: <timestamp>" line in the footer.

## Examples

```bash
# Default run from repo root
python -m analysis.main

# Use a different data snapshot
python -m analysis.main --data-dir /tmp/exp-snapshot/data --output /tmp/report.html

# Tighter directional threshold
python -m analysis.main --flat-threshold 1.0 --verbose
```
