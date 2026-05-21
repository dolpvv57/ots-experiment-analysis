"""HTML rendering: Plotly charts + Jinja2 template + executive summary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import jinja2
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

from analysis.types import (
    DailyTrend,
    EngagementMetric,
    RedirectFunnelMetric,
    RedirectMetric,
    RoundsMetric,
)

VARIANT_COLORS = {"A": "#4C78A8", "B": "#F58518"}

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class ExecSummary:
    headline_engagement: str
    headline_redirect: str
    recommendation: str  # "ship" | "do_not_ship" | "inconclusive"
    rationale: str


def _fmt_pct(x: float, digits: int = 2) -> str:
    if x is None or math.isnan(x):
        return "—"
    return f"{x * 100:.{digits}f}%"


def _fmt_pp(x: float, digits: int = 2) -> str:
    """Format a difference of proportions as percentage points."""
    if x is None or math.isnan(x):
        return "—"
    return f"{x * 100:+.{digits}f} pp"


def _fmt_lift(x: float, digits: int = 2) -> str:
    if x is None or math.isnan(x):
        return "—"
    return f"{x:+.{digits}f}%"


def _fmt_p(x: float) -> str:
    if x is None or math.isnan(x):
        return "—"
    if x < 0.001:
        return "<0.001"
    return f"{x:.4f}"


def _fmt_num(x: float, digits: int = 4) -> str:
    if x is None or math.isnan(x):
        return "—"
    return f"{x:.{digits}f}"


def _fmt_ci(low: float, high: float, scale: float = 1.0, suffix: str = "") -> str:
    if math.isnan(low) or math.isnan(high):
        return "—"
    return f"[{low * scale:+.2f}{suffix}, {high * scale:+.2f}{suffix}]"


def build_static_chart_engagement(metric: EngagementMetric) -> str:
    fig = go.Figure(
        data=[
            go.Bar(
                x=["A (control)", "B (auto-open)"],
                y=[metric.value_A, metric.value_B],
                marker_color=[VARIANT_COLORS["A"], VARIANT_COLORS["B"]],
                text=[f"{metric.value_A:.4f}", f"{metric.value_B:.4f}"],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=f"{metric.chat_type} per {metric.dimension}",
        yaxis_title="Distinct count / variant population",
        xaxis_title="Variant",
        showlegend=False,
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        div_id=f"chart-eng-{metric.chat_type}-{metric.dimension}",
    )


def build_static_chart_redirect(
    metric: RedirectMetric | RedirectFunnelMetric, label: str, div_id: str
) -> str:
    fig = go.Figure(
        data=[
            go.Bar(
                x=["A (control)", "B (auto-open)"],
                y=[metric.rate_A, metric.rate_B],
                marker_color=[VARIANT_COLORS["A"], VARIANT_COLORS["B"]],
                text=[_fmt_pct(metric.rate_A), _fmt_pct(metric.rate_B)],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=label,
        yaxis_title="Rate",
        yaxis_tickformat=".0%",
        xaxis_title="Variant",
        showlegend=False,
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id)


def build_rounds_chart(rounds: RoundsMetric) -> str:
    fig = go.Figure(
        data=[
            go.Bar(
                name="Mean",
                x=["A", "B"],
                y=[rounds.mean_A, rounds.mean_B],
                marker_color=[VARIANT_COLORS["A"], VARIANT_COLORS["B"]],
                text=[_fmt_num(rounds.mean_A, 2), _fmt_num(rounds.mean_B, 2)],
                textposition="outside",
            ),
        ]
    )
    fig.update_layout(
        title=f"Rounds per session (mean) — A median={_fmt_num(rounds.median_A, 2)}, B median={_fmt_num(rounds.median_B, 2)}",
        yaxis_title="Average rounds",
        xaxis_title="Variant",
        showlegend=False,
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return pio.to_html(
        fig, include_plotlyjs=False, full_html=False, div_id="chart-rounds"
    )


def _add_trend_traces(fig: go.Figure, panel: pd.DataFrame, col: int, panel_label: str) -> None:
    for variant in ("A", "B"):
        sub = panel[panel["variant"] == variant].sort_values("dt")
        fig.add_trace(
            go.Scatter(
                x=sub["dt"],
                y=sub["value"],
                mode="lines+markers",
                name=f"Variant {variant}",
                legendgroup=variant,
                showlegend=(col == 1),
                line=dict(color=VARIANT_COLORS[variant], width=2),
                marker=dict(size=6),
            ),
            row=1,
            col=col,
        )
    fig.update_xaxes(title_text=panel_label, row=1, col=col)


def build_trend_chart(trend: DailyTrend) -> str:
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("By utid", "By chat_session_id"),
        shared_yaxes=False,
        horizontal_spacing=0.12,
    )
    _add_trend_traces(fig, trend.utid_panel, col=1, panel_label="Date (utid panel)")
    _add_trend_traces(
        fig, trend.chat_session_panel, col=2, panel_label="Date (chat_session_id panel)"
    )
    fig.update_layout(
        title=trend.title,
        height=380,
        margin=dict(l=40, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1.0),
    )
    fig.update_yaxes(title_text=trend.y_label, row=1, col=1)
    fig.update_yaxes(title_text=trend.y_label, row=1, col=2)
    return pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        div_id=f"chart-trend-{trend.chart_id}",
    )


def build_exec_summary(
    engagement_metrics: Iterable[EngagementMetric],
    redirect_funnel: RedirectFunnelMetric,
) -> ExecSummary:
    """Pick the headline finding and produce a SHIP / DO NOT SHIP / INCONCLUSIVE verdict.

    Headline engagement: CHAT_TYPE_INTENT_RECOGNITION × utid (per-user interaction rate).
    Headline redirect: per-FR-013 funnel rate (utids with redirect / variant_population).
    SHIP only if both are directionally positive AND p < 0.05 (FR-SIG-005).
    """
    headline_engagement_metric = None
    for m in engagement_metrics:
        if m.chat_type == "CHAT_TYPE_INTENT_RECOGNITION" and m.dimension == "utid":
            headline_engagement_metric = m
            break

    if headline_engagement_metric is None:
        raise ValueError("missing headline engagement metric (INTENT × utid)")

    e = headline_engagement_metric
    r = redirect_funnel

    headline_engagement = (
        f"Per-user INTENT_RECOGNITION rate moved from {_fmt_pct(e.value_A)} (A) "
        f"to {_fmt_pct(e.value_B)} (B), a relative lift of {_fmt_lift(e.rel_lift_pct)} "
        f"(p={_fmt_p(e.p_value)}, {e.directional_verdict}, {e.significance_verdict.replace('_', ' ')})."
    )
    headline_redirect = (
        f"Per-chat-user redirect rate moved from {_fmt_pct(r.rate_A)} (A) "
        f"to {_fmt_pct(r.rate_B)} (B), a relative lift of {_fmt_lift(r.rel_lift_pct)} "
        f"(p={_fmt_p(r.p_value)}, {r.directional_verdict}, {r.significance_verdict.replace('_', ' ')})."
    )

    is_engagement_win = (
        e.directional_verdict == "positive" and e.significance_verdict == "significant"
    )
    is_redirect_win = (
        r.directional_verdict == "positive" and r.significance_verdict == "significant"
    )
    is_engagement_loss = e.directional_verdict == "negative"
    is_redirect_loss = r.directional_verdict == "negative"

    if is_engagement_loss or is_redirect_loss:
        recommendation = "do_not_ship"
        rationale = (
            "At least one headline metric moved in the wrong direction; do not ship "
            "without further investigation."
        )
    elif is_engagement_win and is_redirect_win:
        recommendation = "ship"
        rationale = (
            "Both headline metrics moved positively and reached statistical significance "
            "at α=0.05. Recommend shipping the auto-open behavior."
        )
    else:
        recommendation = "inconclusive"
        rationale = (
            "Headline metrics did not both clear the bar of directionally positive AND "
            "statistically significant. Treat as inconclusive — gather more data or "
            "iterate on the design."
        )

    return ExecSummary(
        headline_engagement=headline_engagement,
        headline_redirect=headline_redirect,
        recommendation=recommendation,
        rationale=rationale,
    )


@dataclass
class ReportContext:
    generated_at: datetime
    date_range: tuple[pd.Timestamp, pd.Timestamp]
    variant_population: dict[str, int]
    excluded_utids_count: int
    flat_threshold_pct: float
    alpha: float
    total_tests: int
    expected_false_positives: float

    engagement_metrics: list[EngagementMetric]
    rounds_metric: RoundsMetric
    redirect_metrics_all: list[RedirectMetric]
    redirect_metrics_intent: list[RedirectMetric]
    redirect_funnel_metric: RedirectFunnelMetric

    engagement_trends: tuple[DailyTrend, DailyTrend]
    redirect_trends: tuple[DailyTrend, DailyTrend]

    exec_summary: ExecSummary

    chat_rows: int
    redirect_rows: int


def render_report(context: ReportContext, output_path: Path) -> int:
    """Render the report to `output_path`. Returns the bytes written."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fmt_pct"] = _fmt_pct
    env.filters["fmt_pp"] = _fmt_pp
    env.filters["fmt_lift"] = _fmt_lift
    env.filters["fmt_p"] = _fmt_p
    env.filters["fmt_num"] = _fmt_num

    plotly_bundle = get_plotlyjs()

    engagement_charts = {
        f"{m.chat_type}__{m.dimension}": build_static_chart_engagement(m)
        for m in context.engagement_metrics
    }
    rounds_chart_html = build_rounds_chart(context.rounds_metric)
    redirect_charts = {
        f"redirect_all__{m.dimension}": build_static_chart_redirect(
            m,
            label=f"Redirect rate (all chat) per {m.dimension}",
            div_id=f"chart-red-all-{m.dimension}",
        )
        for m in context.redirect_metrics_all
    }
    redirect_charts.update({
        f"redirect_intent__{m.dimension}": build_static_chart_redirect(
            m,
            label=f"Redirect rate (INTENT only) per {m.dimension}",
            div_id=f"chart-red-intent-{m.dimension}",
        )
        for m in context.redirect_metrics_intent
    })
    redirect_charts["redirect_funnel"] = build_static_chart_redirect(
        context.redirect_funnel_metric,
        label="Funnel rate (utids with redirect / variant_population)",
        div_id="chart-red-funnel",
    )
    trend_charts = {
        context.engagement_trends[0].chart_id: build_trend_chart(context.engagement_trends[0]),
        context.engagement_trends[1].chart_id: build_trend_chart(context.engagement_trends[1]),
        context.redirect_trends[0].chart_id: build_trend_chart(context.redirect_trends[0]),
        context.redirect_trends[1].chart_id: build_trend_chart(context.redirect_trends[1]),
    }

    template = env.get_template("report.html.j2")
    html = template.render(
        ctx=context,
        plotly_bundle=plotly_bundle,
        engagement_charts=engagement_charts,
        rounds_chart_html=rounds_chart_html,
        redirect_charts=redirect_charts,
        trend_charts=trend_charts,
        variant_colors=VARIANT_COLORS,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return len(html.encode("utf-8"))


def make_generated_at() -> datetime:
    return datetime.now(timezone.utc)
