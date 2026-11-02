"""Redirect attribution + redirect-rate metrics.

Implements:
- `build_redirect_attributed`: INTENT chat rows × redirects.csv on correlation_id,
  carrying through redirects.is_booking so callers can derive booking metrics by
  filtering the result to is_booking == 1 and re-calling `compute_redirect_metrics`.
- `compute_redirect_metrics`: 4 RedirectMetric rows (one per dimension).
- `compute_redirect_funnel_metric`: per-FR-013 funnel rate.
- `compute_redirect_trends`: charts 3 (redirect_abs) and 4 (redirect_ratio).
"""

from __future__ import annotations

import math

import pandas as pd

from analysis.stats import directional_verdict, two_proportion_z_test
from analysis.types import (
    DailyTrend,
    RedirectFunnelMetric,
    RedirectMetric,
)

DIMENSIONS = ("session_id", "chat_session_id", "request_id", "correlation_id")


def _rel_lift_pct(value_a: float, value_b: float) -> float:
    if value_a == 0 or math.isnan(value_a) or math.isnan(value_b):
        return float("nan")
    return 100.0 * (value_b - value_a) / value_a


def build_redirect_attributed(
    chat_with_variant: pd.DataFrame,
    redirects: pd.DataFrame,
    intent_only: bool = False,
) -> pd.DataFrame:
    """Inner-join chat rows to redirects on (session_id, correlation_id == pre_redirect_id).

    Args:
        intent_only: if True, restrict chat side to CHAT_TYPE_INTENT_RECOGNITION rows only.
    """
    chat = (
        chat_with_variant[
            chat_with_variant["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"
        ]
        if intent_only
        else chat_with_variant
    )
    redirect_keys = redirects[["session_id", "pre_redirect_id", "is_booking"]].drop_duplicates()
    attributed = chat.merge(
        redirect_keys,
        left_on=["session_id", "correlation_id"],
        right_on=["session_id", "pre_redirect_id"],
        how="inner",
    )
    return attributed[
        ["session_id", "chat_session_id", "request_id", "correlation_id", "variant", "dt", "is_booking"]
    ]


def _distinct_count(df: pd.DataFrame, dimension: str, variant: str) -> int:
    sub = df[df["variant"] == variant]
    if dimension == "chat_session_id":
        sub = sub[sub[dimension].notna() & (sub[dimension] != "")]
    return int(sub[dimension].dropna().nunique())


def compute_redirect_metrics(
    numerator_df: pd.DataFrame,
    denominator_df: pd.DataFrame,
) -> list[RedirectMetric]:
    """Four RedirectMetric rows, one per dimension.

    Args:
        numerator_df  : redirect_attributed (rows that matched a redirect).
        denominator_df: the chat subset that defines the population
                        (all chat rows, or INTENT-only rows).
    """
    out: list[RedirectMetric] = []
    for dim in DIMENSIONS:
        num_a = _distinct_count(numerator_df, dim, "A")
        num_b = _distinct_count(numerator_df, dim, "B")
        den_a = _distinct_count(denominator_df, dim, "A")
        den_b = _distinct_count(denominator_df, dim, "B")
        rate_a = num_a / den_a if den_a > 0 else float("nan")
        rate_b = num_b / den_b if den_b > 0 else float("nan")
        abs_diff = rate_b - rate_a if not (math.isnan(rate_a) or math.isnan(rate_b)) else float("nan")
        rel_lift = _rel_lift_pct(rate_a, rate_b)
        stat = two_proportion_z_test(num_a, den_a, num_b, den_b)
        out.append(
            RedirectMetric(
                dimension=dim,
                numerator_A=num_a,
                numerator_B=num_b,
                denominator_A=den_a,
                denominator_B=den_b,
                rate_A=rate_a,
                rate_B=rate_b,
                abs_diff=abs_diff,
                rel_lift_pct=rel_lift,
                p_value=stat.p_value,
                directional_verdict=directional_verdict(rel_lift),
                significance_verdict=stat.significance_verdict,
            )
        )
    return out


def compute_redirect_funnel_metric(
    redirect_attributed: pd.DataFrame, variant_population: dict[str, int]
) -> RedirectFunnelMetric:
    """Per-FR-013: distinct session_ids with redirect / variant_population (chat users)."""
    num_a = _distinct_count(redirect_attributed, "session_id", "A")
    num_b = _distinct_count(redirect_attributed, "session_id", "B")
    den_a = variant_population["A"]
    den_b = variant_population["B"]
    rate_a = num_a / den_a if den_a > 0 else float("nan")
    rate_b = num_b / den_b if den_b > 0 else float("nan")
    abs_diff = rate_b - rate_a if not (math.isnan(rate_a) or math.isnan(rate_b)) else float("nan")
    rel_lift = _rel_lift_pct(rate_a, rate_b)
    stat = two_proportion_z_test(num_a, den_a, num_b, den_b)
    return RedirectFunnelMetric(
        metric="redirect_rate_per_chat_user",
        numerator_A=num_a,
        numerator_B=num_b,
        denominator_A=den_a,
        denominator_B=den_b,
        rate_A=rate_a,
        rate_B=rate_b,
        abs_diff=abs_diff,
        rel_lift_pct=rel_lift,
        p_value=stat.p_value,
        ci_low=stat.ci_low,
        ci_high=stat.ci_high,
        directional_verdict=directional_verdict(rel_lift),
        significance_verdict=stat.significance_verdict,
    )


def _daily_distinct(
    df: pd.DataFrame, dimension: str, drop_empty_session: bool
) -> pd.DataFrame:
    if drop_empty_session and dimension == "chat_session_id":
        df = df[df[dimension].notna() & (df[dimension] != "")]
    grouped = (
        df.groupby(["dt", "variant"], observed=True)[dimension]
        .nunique()
        .reset_index(name="value")
    )
    return grouped


def _ratio_panel(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    merged = num.merge(
        den, on=["dt", "variant"], how="outer", suffixes=("_num", "_den")
    )
    merged["value_num"] = merged["value_num"].fillna(0)
    merged["value"] = merged.apply(
        lambda r: r["value_num"] / r["value_den"]
        if pd.notna(r["value_den"]) and r["value_den"] > 0
        else float("nan"),
        axis=1,
    )
    return merged[["dt", "variant", "value"]].sort_values(["dt", "variant"]).reset_index(drop=True)


def compute_redirect_trends(
    chat_with_variant: pd.DataFrame,
    redirect_attributed: pd.DataFrame,
) -> tuple[DailyTrend, DailyTrend]:
    """Charts 3 (redirect_abs) and 4 (redirect_ratio).

    Chart 3 numerator: distinct session_ids / chat_sessions in `redirect_attributed`.
    Chart 4 denominator: distinct INTENT session_ids / chat_sessions per (dt, variant).
    """
    intent = chat_with_variant[
        chat_with_variant["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"
    ]

    abs_session_id = _daily_distinct(redirect_attributed, "session_id", drop_empty_session=False)
    abs_session = _daily_distinct(
        redirect_attributed, "chat_session_id", drop_empty_session=True
    )
    chart_abs = DailyTrend(
        chart_id="redirect_abs",
        title="Daily redirect-attributed count (INTENT_RECOGNITION only)",
        y_label="Distinct count",
        session_id_panel=abs_session_id,
        chat_session_panel=abs_session,
    )

    intent_session_id = _daily_distinct(intent, "session_id", drop_empty_session=False)
    intent_session = _daily_distinct(
        intent, "chat_session_id", drop_empty_session=True
    )
    ratio_session_id = _ratio_panel(abs_session_id, intent_session_id)
    ratio_session = _ratio_panel(abs_session, intent_session)
    chart_ratio = DailyTrend(
        chart_id="redirect_ratio",
        title="Daily redirect ÷ INTENT_RECOGNITION rate",
        y_label="Redirect rate",
        session_id_panel=ratio_session_id,
        chat_session_panel=ratio_session,
    )

    return chart_abs, chart_ratio
