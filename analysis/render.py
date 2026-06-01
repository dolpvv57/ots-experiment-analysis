"""HTML rendering: Plotly charts + Jinja2 template + executive summary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jinja2
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

from analysis.plugin import PluginSection
from analysis.types import (
    EngagementMetric,
    LoadFunnelMetric,
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
    # TODO: replace with AI-generated summary; populate via generate_ai_summary()


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
                x=["A (control)", "B (treatment)"],
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
                x=["A (control)", "B (treatment)"],
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




def build_map_rate_chart(
    metrics: list, title: str, div_id: str
) -> str:
    labels = [m.label for m in metrics]
    max_rate = max((max(m.rate_A, m.rate_B) for m in metrics), default=1.0)
    fig = go.Figure(data=[
        go.Bar(
            name="A (control)",
            x=labels,
            y=[m.rate_A for m in metrics],
            marker_color=VARIANT_COLORS["A"],
            text=[_fmt_pct(m.rate_A) for m in metrics],
            textposition="outside",
        ),
        go.Bar(
            name="B (treatment)",
            x=labels,
            y=[m.rate_B for m in metrics],
            marker_color=VARIANT_COLORS["B"],
            text=[_fmt_pct(m.rate_B) for m in metrics],
            textposition="outside",
        ),
    ])
    fig.update_layout(
        title=title,
        barmode="group",
        yaxis=dict(range=[0, max_rate * 1.3], tickformat=".1%", title="Rate"),
        height=360,
        margin=dict(l=40, r=20, t=50, b=120),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
    )
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id)


@dataclass
class ReportContext:
    experiment_name: str
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
    load_funnel_metric: LoadFunnelMetric | None  # None if actions.csv absent
    redirect_metrics_all: list[RedirectMetric]
    redirect_metrics_intent: list[RedirectMetric]
    redirect_funnel_metric: RedirectFunnelMetric

    chat_rows: int
    redirect_rows: int
    action_rows: int | None  # None if actions.csv was absent
    action_population: dict[str, int] | None  # {A: n, B: n} or None
    plugin_sections: list[PluginSection] = field(default_factory=list)
    exec_summary: Optional[ExecSummary] = None  # populated by AI; None → placeholder shown


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
    plugin_section_htmls: list[str] = []
    for ps in context.plugin_sections:
        fragment_src = ps.template_path.read_text(encoding="utf-8")
        fragment_tpl = env.from_string(fragment_src)
        plugin_section_htmls.append(
            fragment_tpl.render(section=ps.section, charts=ps.charts)
        )

    template = env.get_template("report.html.j2")
    html = template.render(
        ctx=context,
        plotly_bundle=plotly_bundle,
        engagement_charts=engagement_charts,
        rounds_chart_html=rounds_chart_html,
        redirect_charts=redirect_charts,
        variant_colors=VARIANT_COLORS,
        plugin_section_htmls=plugin_section_htmls,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return len(html.encode("utf-8"))


def make_generated_at() -> datetime:
    return datetime.now(timezone.utc)
