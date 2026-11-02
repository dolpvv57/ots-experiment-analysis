"""Map usage analysis for the chat-box-auto-open experiment.

Population: users with at least one CHAT_BOX_ENTRY_LOADED in actions.csv
(proxy for "actually rendered day view with the chat box").

Block 1 — exposure rate: % users with MAP_MOVING_DAY_VIEW / MAP_HOTEL_MARKER_CLICK / any map action.
Block 2 — intensity: mean & median map actions per map-user (Welch's t; post-treatment selection caveat).
Block 3 — redirect funnel: P(redirect) segmented by map usage (map users / marker users / non-map users).
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from analysis.stats import directional_verdict, two_proportion_z_test
from analysis.types import MapRateMetric, MapSection

_LOADED_ACTION = "CHAT_BOX_ENTRY_LOADED"
_MAP_ACTIONS = ("MAP_MOVING_DAY_VIEW", "MAP_HOTEL_MARKER_CLICK")


def _rel_lift_pct(a: float, b: float) -> float:
    if a == 0 or math.isnan(a) or math.isnan(b):
        return float("nan")
    return 100.0 * (b - a) / a


def _rate_metric(
    label: str,
    num_a: int, den_a: int,
    num_b: int, den_b: int,
) -> MapRateMetric:
    r_a = num_a / den_a if den_a > 0 else float("nan")
    r_b = num_b / den_b if den_b > 0 else float("nan")
    rel_lift = _rel_lift_pct(r_a, r_b)
    stat = two_proportion_z_test(num_a, den_a, num_b, den_b)
    abs_diff = r_b - r_a if not (math.isnan(r_a) or math.isnan(r_b)) else float("nan")
    return MapRateMetric(
        label=label,
        numerator_A=num_a, denominator_A=den_a,
        numerator_B=num_b, denominator_B=den_b,
        rate_A=r_a, rate_B=r_b,
        abs_diff=abs_diff,
        rel_lift_pct=rel_lift,
        p_value=stat.p_value,
        ci_low=stat.ci_low,
        ci_high=stat.ci_high,
        directional_verdict=directional_verdict(rel_lift),
        significance_verdict=stat.significance_verdict,
    )



def compute(
    data_dir: Path,
    redirects_df: pd.DataFrame,
    excluded_session_ids: set[str],
) -> MapSection:
    actions = pd.read_csv(
        data_dir / "actions.csv",
        usecols=["session_id", "variant", "action_type"],
        dtype={"session_id": "string", "variant": "category", "action_type": "category"},
    )

    actions = actions[~actions["session_id"].isin(excluded_session_ids)]

    loaded_session_ids: set[str] = set(
        actions.loc[actions["action_type"] == _LOADED_ACTION, "session_id"].dropna()
    )

    variant_lookup: pd.Series = (
        actions[actions["session_id"].isin(loaded_session_ids)]
        .drop_duplicates("session_id")[["session_id", "variant"]]
        .set_index("session_id")["variant"]
        .astype("string")
    )
    pop_a = int((variant_lookup == "A").sum())
    pop_b = int((variant_lookup == "B").sum())

    map_rows = actions[
        actions["session_id"].isin(loaded_session_ids)
        & actions["action_type"].isin(_MAP_ACTIONS)
    ].copy()
    map_rows["v"] = map_rows["session_id"].map(variant_lookup)

    def _users_with(action_type: str, variant: str) -> set[str]:
        return set(
            map_rows.loc[
                (map_rows["action_type"] == action_type) & (map_rows["v"] == variant),
                "session_id",
            ]
        )

    # ---- block 1: exposure ----

    moving_a = _users_with("MAP_MOVING_DAY_VIEW", "A")
    moving_b = _users_with("MAP_MOVING_DAY_VIEW", "B")
    marker_a = _users_with("MAP_HOTEL_MARKER_CLICK", "A")
    marker_b = _users_with("MAP_HOTEL_MARKER_CLICK", "B")
    any_a = moving_a | marker_a
    any_b = moving_b | marker_b

    exposure = [
        _rate_metric("MAP_MOVING_DAY_VIEW", len(moving_a), pop_a, len(moving_b), pop_b),
        _rate_metric("MAP_HOTEL_MARKER_CLICK", len(marker_a), pop_a, len(marker_b), pop_b),
        _rate_metric("Any map action", len(any_a), pop_a, len(any_b), pop_b),
    ]

    # ---- block 3: redirect funnel ----

    redirected_session_ids: set[str] = set(redirects_df["session_id"].dropna())
    loaded_a: set[str] = set(variant_lookup[variant_lookup == "A"].index)
    loaded_b: set[str] = set(variant_lookup[variant_lookup == "B"].index)
    non_map_a = loaded_a - any_a
    non_map_b = loaded_b - any_b

    def _funnel(label: str, users_a: set[str], users_b: set[str]) -> MapRateMetric:
        return _rate_metric(
            label,
            len(users_a & redirected_session_ids), len(users_a),
            len(users_b & redirected_session_ids), len(users_b),
        )

    funnel = [
        _funnel("Map users (any map action)", any_a, any_b),
        _funnel("Marker-click users", marker_a, marker_b),
        _funnel("Non-map users", non_map_a, non_map_b),
        _funnel("All loaded users (overall)", loaded_a, loaded_b),
    ]

    return MapSection(
        population_A=pop_a,
        population_B=pop_b,
        exposure_metrics=exposure,
        funnel_metrics=funnel,
    )
