"""Shared dataclasses for the analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

DirectionalVerdict = Literal["positive", "flat", "negative"]
SignificanceVerdict = Literal["significant", "not_significant"]


@dataclass(frozen=True)
class EngagementMetric:
    """One row of the engagement table.

    `chat_type × dimension` → 8 EngagementMetric rows total.
    `value_X` is the normalized rate (count_X / variant_population[X]).
    """

    chat_type: str
    dimension: str
    count_A: int
    count_B: int
    value_A: float
    value_B: float
    abs_diff: float
    rel_lift_pct: float
    p_value: float
    ci_low: float
    ci_high: float
    directional_verdict: DirectionalVerdict
    significance_verdict: SignificanceVerdict


@dataclass(frozen=True)
class RoundsMetric:
    """The single rounds (mean per session) metric (FR-008)."""

    metric: str  # "rounds_per_session"
    n_sessions_A: int
    n_sessions_B: int
    mean_A: float
    mean_B: float
    median_A: float
    median_B: float
    abs_diff_mean: float
    rel_lift_mean_pct: float
    p_value: float
    ci_low: float
    ci_high: float
    directional_verdict: DirectionalVerdict
    significance_verdict: SignificanceVerdict


@dataclass(frozen=True)
class RedirectMetric:
    """One row of a redirect-rate table (all-chat or intent-only variant).

    numerator  = distinct dimension values in redirect_attributed.
    denominator = distinct dimension values in the corresponding chat subset.
    """

    dimension: str
    numerator_A: int
    numerator_B: int
    denominator_A: int
    denominator_B: int
    rate_A: float
    rate_B: float
    abs_diff: float
    rel_lift_pct: float
    p_value: float
    directional_verdict: DirectionalVerdict
    significance_verdict: SignificanceVerdict


@dataclass(frozen=True)
class RedirectFunnelMetric:
    """Per-FR-013 funnel metric: distinct utids with redirect / variant_population."""

    metric: str  # "redirect_rate_per_chat_user"
    numerator_A: int
    numerator_B: int
    denominator_A: int  # variant_population[A]
    denominator_B: int  # variant_population[B]
    rate_A: float
    rate_B: float
    abs_diff: float
    rel_lift_pct: float
    p_value: float
    ci_low: float
    ci_high: float
    directional_verdict: DirectionalVerdict
    significance_verdict: SignificanceVerdict


@dataclass(frozen=True)
class LoadFunnelMetric:
    """Load → click / chat funnel: denominator is ENTRY_LOADED distinct utids per variant.

    click = ENTRY_CLICK distinct utids; chat = INTENT_RECOGNITION distinct utids.
    p-values are two-proportion z-tests comparing A vs B.
    None when actions.csv was absent.
    """

    load_A: int
    load_B: int
    click_A: int
    click_B: int
    chat_A: int
    chat_B: int
    click_rate_A: float
    click_rate_B: float
    click_rel_lift_pct: float
    click_p_value: float
    click_directional_verdict: DirectionalVerdict
    click_significance_verdict: SignificanceVerdict
    chat_rate_A: float
    chat_rate_B: float
    chat_rel_lift_pct: float
    chat_p_value: float
    chat_directional_verdict: DirectionalVerdict
    chat_significance_verdict: SignificanceVerdict


@dataclass(frozen=True)
class DailyTrend:
    """One of the four daily-trend charts.

    Each `*_panel` is a tidy DataFrame with columns (`dt`, `variant`, `value`).
    """

    chart_id: str  # "engagement_abs" | "engagement_ratio" | "redirect_abs" | "redirect_ratio"
    title: str
    y_label: str
    utid_panel: pd.DataFrame
    chat_session_panel: pd.DataFrame
