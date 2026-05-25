"""CLI entry point: end-to-end orchestration of the analysis pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

from analysis import stats as stats_module
from analysis.engagement import (
    compute_engagement_metrics,
    compute_engagement_trends,
    compute_rounds_metric,
)
from analysis.load import (
    build_variant_lookup,
    compute_variant_population,
    load_data,
)
from analysis.redirects import (
    build_redirect_attributed,
    compute_redirect_funnel_metric,
    compute_redirect_metrics,
    compute_redirect_trends,
)
from analysis.render import (
    ReportContext,
    build_exec_summary,
    make_generated_at,
    render_report,
)

DEFAULT_EXPERIMENT = "ai-filter-entrance"


def _now() -> float:
    return time.perf_counter()


def _stage(verbose: bool, label: str, message: str, t0: float) -> None:
    if verbose:
        elapsed = _now() - t0
        print(f"[{label}] {message} ({elapsed:.1f}s)", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analysis.main",
        description="Generate the A/B experiment analysis HTML report.",
    )
    parser.add_argument(
        "--experiment",
        default=DEFAULT_EXPERIMENT,
        help="Experiment directory name under the project root (default: %(default)s). "
        "Data is read from <experiment>/data/, report written to <experiment>/output/report.html.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override input CSV directory (default: <experiment>/data).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override report output path (default: <experiment>/output/report.html).",
    )
    parser.add_argument(
        "--flat-threshold",
        type=float,
        default=stats_module.FLAT_THRESHOLD_PCT,
        help="Relative lift |x|%% under this is 'flat' (per FR-007). Default 2.0.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=stats_module.ALPHA,
        help="Significance level (per FR-SIG-004). Default 0.05.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    # Allow runtime override of stats module constants without complicating signatures.
    stats_module.ALPHA = args.alpha
    stats_module.FLAT_THRESHOLD_PCT = args.flat_threshold

    experiment_root = Path(args.experiment)
    data_dir = Path(args.data_dir) if args.data_dir else experiment_root / "data"
    output_path = (
        Path(args.output) if args.output else experiment_root / "output" / "report.html"
    )

    try:
        t0 = _now()
        bundle = load_data(data_dir)
        chat_rows = len(bundle.ots_chat)
        redirect_rows = len(bundle.redirects)
        _stage(
            args.verbose,
            "load",
            f"{chat_rows + redirect_rows:,} rows in 2 files",
            t0,
        )

        t0 = _now()
        _, excluded = build_variant_lookup(bundle.ots_chat)
        pop = compute_variant_population(bundle.ots_chat, excluded)
        chat = bundle.ots_chat[~bundle.ots_chat["utid"].isin(excluded)]
        _stage(
            args.verbose,
            "validate",
            f"{len(excluded)} utids excluded for in-file variant conflict",
            t0,
        )

        if pop["A"] == 0 or pop["B"] == 0:
            print(
                f"FATAL: empty variant population (A={pop['A']}, B={pop['B']}); cannot compare.",
                file=sys.stderr,
            )
            return 2

        t0 = _now()
        eng_metrics = compute_engagement_metrics(chat, pop)
        rounds_metric = compute_rounds_metric(chat)
        eng_trends = compute_engagement_trends(chat)
        _stage(
            args.verbose,
            "engage",
            f"{len(eng_metrics)} engagement metrics + rounds metric + 2 trend tables",
            t0,
        )

        t0 = _now()
        attributed_all = build_redirect_attributed(chat, bundle.redirects, intent_only=False)
        attributed_intent = build_redirect_attributed(chat, bundle.redirects, intent_only=True)
        intent_chat = chat[chat["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"]
        red_metrics_all = compute_redirect_metrics(attributed_all, chat)
        red_metrics_intent = compute_redirect_metrics(attributed_intent, intent_chat)
        funnel = compute_redirect_funnel_metric(attributed_all, pop)
        red_trends = compute_redirect_trends(chat, attributed_intent)
        _stage(
            args.verbose,
            "redirect",
            f"all={len(attributed_all):,} / intent={len(attributed_intent):,} attributed redirects",
            t0,
        )

        t0 = _now()
        map_section = None
        map_analysis_path = experiment_root / "map_analysis.py"
        if map_analysis_path.exists():
            spec = importlib.util.spec_from_file_location("map_analysis", map_analysis_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            map_section = mod.compute(data_dir, bundle.redirects, excluded)
            _stage(args.verbose, "map", "map usage analysis computed", t0)

        t0 = _now()
        entrance_section = None
        entrance_analysis_path = experiment_root / "entrance_analysis.py"
        if entrance_analysis_path.exists():
            spec = importlib.util.spec_from_file_location("entrance_analysis", entrance_analysis_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            entrance_section = mod.compute(data_dir, bundle.redirects, excluded)
            _stage(args.verbose, "entrance", "entrance position analysis computed", t0)

        t0 = _now()
        exec_summary = build_exec_summary(eng_metrics, funnel)
        map_tests = (
            len(map_section.exposure_metrics)
            + len(map_section.funnel_metrics)
        ) if map_section is not None else 0
        # Entrance section contributes 0 z-tests (all blocks are descriptive
        # per-entrance comparisons, not A/B hypothesis tests).
        total_tests = (
            len(eng_metrics) + len(red_metrics_all) + len(red_metrics_intent)
            + 1 + 1 + map_tests
        )
        ctx = ReportContext(
            experiment_name=args.experiment,
            generated_at=make_generated_at(),
            date_range=(bundle.ots_chat["dt"].min(), bundle.ots_chat["dt"].max()),
            variant_population=pop,
            excluded_utids_count=len(excluded),
            flat_threshold_pct=args.flat_threshold,
            alpha=args.alpha,
            total_tests=total_tests,
            expected_false_positives=total_tests * args.alpha,
            engagement_metrics=eng_metrics,
            rounds_metric=rounds_metric,
            redirect_metrics_all=red_metrics_all,
            redirect_metrics_intent=red_metrics_intent,
            redirect_funnel_metric=funnel,
            engagement_trends=eng_trends,
            redirect_trends=red_trends,
            exec_summary=exec_summary,
            chat_rows=chat_rows,
            redirect_rows=redirect_rows,
            map_section=map_section,
            entrance_section=entrance_section,
        )
        size_bytes = render_report(ctx, output_path)
        _stage(
            args.verbose,
            "render",
            f"report.html written ({size_bytes / 1024 / 1024:.1f} MB) -> {output_path}",
            t0,
        )

        if args.verbose:
            print(f"[done] {output_path}", file=sys.stderr)
        return 0

    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception:  # pragma: no cover - top-level safety net
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
