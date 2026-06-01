"""Engagement metrics.

Implements:
- `compute_engagement_metrics`: 8 EngagementMetric rows (2 chat_types × 4 dims).
- `compute_rounds_metric`: mean/median rounds per chat session, with Welch's t.
- `compute_load_funnel_metric`: load → click / chat funnel from actions.csv.
"""

from __future__ import annotations

import math

import pandas as pd

from analysis.stats import (
    directional_verdict,
    two_proportion_z_test,
    welch_t_test,
)
from analysis.types import EngagementMetric, LoadFunnelMetric, RoundsMetric

CHAT_TYPES = ("CHAT_TYPE_SUGGESTIONS", "CHAT_TYPE_INTENT_RECOGNITION")
DIMENSIONS = ("utid", "chat_session_id", "request_id", "correlation_id")


def _distinct_count(
    df: pd.DataFrame, dimension: str, variant: str
) -> int:
    """Distinct dimension count in `df` filtered to a variant.

    For chat_session_id, empty / null session ids are dropped (per Edge Cases).
    """
    sub = df[df["variant"] == variant]
    if dimension == "chat_session_id":
        sub = sub[sub[dimension].notna() & (sub[dimension] != "")]
    return int(sub[dimension].dropna().nunique())


def _rel_lift_pct(value_a: float, value_b: float) -> float:
    if value_a == 0 or math.isnan(value_a) or math.isnan(value_b):
        return float("nan")
    return 100.0 * (value_b - value_a) / value_a


def compute_engagement_metrics(
    chat_with_variant: pd.DataFrame,
    variant_population: dict[str, int],
) -> list[EngagementMetric]:
    """Compute the 8 EngagementMetric rows.

    Rate denominator is the per-dimension distinct count across ALL chat
    (SUGGESTIONS + INTENT), per variant — i.e. each rate answers "what fraction
    of <dimension> values had at least one row of this chat_type?"
    """
    out: list[EngagementMetric] = []
    for chat_type in CHAT_TYPES:
        sub = chat_with_variant[chat_with_variant["chat_type"] == chat_type]
        for dim in DIMENSIONS:
            count_a = _distinct_count(sub, dim, "A")
            count_b = _distinct_count(sub, dim, "B")
            den_a = _distinct_count(chat_with_variant, dim, "A")
            den_b = _distinct_count(chat_with_variant, dim, "B")
            value_a = count_a / den_a if den_a > 0 else float("nan")
            value_b = count_b / den_b if den_b > 0 else float("nan")
            abs_diff = value_b - value_a
            rel_lift = _rel_lift_pct(value_a, value_b)
            stat = two_proportion_z_test(count_a, den_a, count_b, den_b)
            out.append(
                EngagementMetric(
                    chat_type=chat_type,
                    dimension=dim,
                    count_A=count_a,
                    count_B=count_b,
                    value_A=value_a,
                    value_B=value_b,
                    abs_diff=abs_diff,
                    rel_lift_pct=rel_lift,
                    p_value=stat.p_value,
                    ci_low=stat.ci_low,
                    ci_high=stat.ci_high,
                    directional_verdict=directional_verdict(rel_lift),
                    significance_verdict=stat.significance_verdict,
                )
            )
    return out


def compute_rounds_metric(chat_with_variant: pd.DataFrame) -> RoundsMetric:
    """Mean & median rounds per chat session, with Welch's t-test on the per-session vectors."""
    intent = chat_with_variant[
        chat_with_variant["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"
    ]
    intent = intent[intent["chat_session_id"].notna() & (intent["chat_session_id"] != "")]
    per_session = intent.groupby(
        ["variant", "chat_session_id"], observed=True
    )["rounds"].max().reset_index()

    a = per_session.loc[per_session["variant"] == "A", "rounds"].astype(float).tolist()
    b = per_session.loc[per_session["variant"] == "B", "rounds"].astype(float).tolist()

    mean_a = float(pd.Series(a).mean()) if a else float("nan")
    mean_b = float(pd.Series(b).mean()) if b else float("nan")
    median_a = float(pd.Series(a).median()) if a else float("nan")
    median_b = float(pd.Series(b).median()) if b else float("nan")
    abs_diff = mean_b - mean_a if (a and b) else float("nan")
    rel_lift = _rel_lift_pct(mean_a, mean_b)

    stat = welch_t_test(a, b)
    return RoundsMetric(
        metric="rounds_per_session",
        n_sessions_A=len(a),
        n_sessions_B=len(b),
        mean_A=mean_a,
        mean_B=mean_b,
        median_A=median_a,
        median_B=median_b,
        abs_diff_mean=abs_diff,
        rel_lift_mean_pct=rel_lift,
        p_value=stat.p_value,
        ci_low=stat.ci_low,
        ci_high=stat.ci_high,
        directional_verdict=directional_verdict(rel_lift),
        significance_verdict=stat.significance_verdict,
    )


def compute_load_funnel_metric(
    actions: pd.DataFrame,
    chat_with_variant: pd.DataFrame,
) -> LoadFunnelMetric:
    """Load → click / chat funnel.

    load  = distinct utids with CHAT_BOX_ENTRY_LOADED in actions (denominator).
    click = distinct utids with CHAT_BOX_ENTRY_CLICK in actions.
    chat  = distinct utids with CHAT_TYPE_INTENT_RECOGNITION in ots_chat.
    Rates are click/load and chat/load per variant; p-values compare A vs B.
    """
    loaded = actions[actions["action_type"] == "CHAT_BOX_ENTRY_LOADED"]
    clicked = actions[actions["action_type"] == "CHAT_BOX_ENTRY_CLICK"]
    chatted = chat_with_variant[
        chat_with_variant["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"
    ]

    def _n(df: pd.DataFrame, variant: str) -> int:
        return int(df[df["variant"] == variant]["utid"].nunique())

    load_a, load_b = _n(loaded, "A"), _n(loaded, "B")
    click_a, click_b = _n(clicked, "A"), _n(clicked, "B")
    chat_a, chat_b = _n(chatted, "A"), _n(chatted, "B")

    click_rate_a = click_a / load_a if load_a else float("nan")
    click_rate_b = click_b / load_b if load_b else float("nan")
    chat_rate_a = chat_a / load_a if load_a else float("nan")
    chat_rate_b = chat_b / load_b if load_b else float("nan")

    click_stat = two_proportion_z_test(click_a, load_a, click_b, load_b)
    chat_stat = two_proportion_z_test(chat_a, load_a, chat_b, load_b)

    return LoadFunnelMetric(
        load_A=load_a,
        load_B=load_b,
        click_A=click_a,
        click_B=click_b,
        chat_A=chat_a,
        chat_B=chat_b,
        click_rate_A=click_rate_a,
        click_rate_B=click_rate_b,
        click_rel_lift_pct=_rel_lift_pct(click_rate_a, click_rate_b),
        click_p_value=click_stat.p_value,
        click_directional_verdict=directional_verdict(_rel_lift_pct(click_rate_a, click_rate_b)),
        click_significance_verdict=click_stat.significance_verdict,
        chat_rate_A=chat_rate_a,
        chat_rate_B=chat_rate_b,
        chat_rel_lift_pct=_rel_lift_pct(chat_rate_a, chat_rate_b),
        chat_p_value=chat_stat.p_value,
        chat_directional_verdict=directional_verdict(_rel_lift_pct(chat_rate_a, chat_rate_b)),
        chat_significance_verdict=chat_stat.significance_verdict,
    )
