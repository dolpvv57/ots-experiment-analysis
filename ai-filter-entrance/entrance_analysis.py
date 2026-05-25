"""Per-entrance position analysis for the ai-filter-entrance experiment.

Population: utids in actions.csv with at least one CHAT_BOX_ENTRY_LOADED,
after removing variant-conflict utids.

All blocks are variant-agnostic — every metric is sliced by entrance
(loaded_area), not by A/B. The 4 entrance loader populations overlap:
e.g. an A-group user typically loads both `inline` and `map`. Each cell
is a within-entrance rate.

Block 1 — per-entrance CTR & redirect rate (4 entrances, descriptive).
Block 2 — native-feature usage rate, one cell per entrance (5 events × 4 entrances).
Block 2 add-on — loaded vs not-loaded comparison among active utids
                 (4 tables, one per entrance).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from analysis.types import (
    EntranceImpactRow,
    EntranceImpactTable,
    EntrancePerformanceMetric,
    EntranceSection,
    PerEntranceCell,
    PerEntranceEventRow,
)

_LOADED_ACTION = "CHAT_BOX_ENTRY_LOADED"
_CLICK_ACTION = "CHAT_BOX_ENTRY_CLICK"

# Ordered: report tables iterate in this order.
_ENTRANCE_NAMES: list[str] = ["inline", "map", "filter", "sort"]

# entrance label -> (loaded_area, set of click areas)
_ENTRANCES: dict[str, tuple[str, frozenset[str]]] = {
    "inline": ("INLINE", frozenset({"SEARCH_INPUT_IN_FEEDS", "SUGGESTION_BUTTON"})),
    "map":    ("ON_MAP", frozenset({"CHAT_BUTTON_ON_MAP"})),
    "filter": ("SIDEBAR_FILTER_PANEL", frozenset({"CHAT_BOX_ON_FILTER_PANEL"})),
    "sort":   ("SEARCH_SUMMARY", frozenset({"CHAT_BUTTON_ON_SEARCH_SUMMARY"})),
}

_NATIVE_EVENTS: list[str] = [
    "DAY_VIEW_FILTERS_USED",
    "DAY_VIEW_SORT_USED",
    "MAP_MOVING_DAY_VIEW",
    "MAP_HOTEL_MARKER_CLICK",
    "DAY_VIEW_HOTEL_CARD_CLICKED",
]

# Impact tables: per entrance, the events whose usage we expect to be
# affected by placing/not placing a chat-box entrance at that position.
_IMPACT_EVENTS: dict[str, list[str]] = {
    "inline": ["DAY_VIEW_HOTEL_CARD_CLICKED"],
    "map":    ["MAP_MOVING_DAY_VIEW", "MAP_HOTEL_MARKER_CLICK", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "filter": ["DAY_VIEW_FILTERS_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "sort":   ["DAY_VIEW_SORT_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
}


def _wilson(num: int, den: int) -> tuple[float, float]:
    if den <= 0:
        return float("nan"), float("nan")
    low, high = proportion_confint(num, den, alpha=0.05, method="wilson")
    return float(low), float(high)


def _cell(num: int, den: int) -> PerEntranceCell:
    rate = num / den if den > 0 else float("nan")
    return PerEntranceCell(numerator=num, denominator=den, rate=rate)


def _parse_field(payload: object, key: str) -> str | None:
    if not isinstance(payload, str) or not payload:
        return None
    try:
        obj = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    val = obj.get(key)
    return val if isinstance(val, str) else None


def compute(
    data_dir: Path,
    redirects_df: pd.DataFrame,
    excluded_utids: set[str],
) -> EntranceSection:
    actions = pd.read_csv(
        data_dir / "actions.csv",
        usecols=[
            "utid", "action_type",
            "chat_box_entry_loaded", "chat_box_entry_click",
        ],
        dtype={
            "utid": "string",
            "action_type": "category",
            "chat_box_entry_loaded": "string",
            "chat_box_entry_click": "string",
        },
    )
    actions = actions[~actions["utid"].isin(excluded_utids)]

    loaded_rows = actions[actions["action_type"] == _LOADED_ACTION].copy()
    click_rows = actions[actions["action_type"] == _CLICK_ACTION].copy()

    loaded_rows["area"] = loaded_rows["chat_box_entry_loaded"].apply(
        lambda s: _parse_field(s, "loaded_area")
    )
    click_rows["area"] = click_rows["chat_box_entry_click"].apply(
        lambda s: _parse_field(s, "open_chat_box_area")
    )

    redirected_utids: set[str] = set(redirects_df["utid"].dropna())

    # Per-entrance loaded/clicked user sets (variant-agnostic).
    loaded_users_by_entrance: dict[str, set[str]] = {}
    clicked_users_by_entrance: dict[str, set[str]] = {}
    for entrance in _ENTRANCE_NAMES:
        loaded_area, click_areas = _ENTRANCES[entrance]
        loaded_users_by_entrance[entrance] = set(
            loaded_rows.loc[loaded_rows["area"] == loaded_area, "utid"].dropna()
        )
        clicked_users_by_entrance[entrance] = set(
            click_rows.loc[click_rows["area"].isin(click_areas), "utid"].dropna()
        )

    entrance_loaders: dict[str, int] = {
        e: len(loaded_users_by_entrance[e]) for e in _ENTRANCE_NAMES
    }

    # ---- block 1: per-entrance CTR & redirect rate ----

    per_entrance: list[EntrancePerformanceMetric] = []
    for entrance in _ENTRANCE_NAMES:
        loaded_users = loaded_users_by_entrance[entrance]
        clicked_users = clicked_users_by_entrance[entrance]
        clicked_in_loaded = clicked_users & loaded_users
        ctr = len(clicked_in_loaded) / len(loaded_users) if loaded_users else float("nan")
        ctr_low, ctr_high = _wilson(len(clicked_in_loaded), len(loaded_users))

        redirected_clickers = clicked_users & redirected_utids
        rr = (
            len(redirected_clickers) / len(clicked_users)
            if clicked_users else float("nan")
        )
        rr_low, rr_high = _wilson(len(redirected_clickers), len(clicked_users))

        per_entrance.append(EntrancePerformanceMetric(
            entrance=entrance,
            loaded_users=len(loaded_users),
            clicked_users=len(clicked_users),
            ctr_per_user=ctr,
            ctr_ci_low=ctr_low,
            ctr_ci_high=ctr_high,
            redirected_clickers=len(redirected_clickers),
            redirect_rate_clickers=rr,
            redirect_ci_low=rr_low,
            redirect_ci_high=rr_high,
        ))

    # ---- block 2: per-entrance native-event rates ----

    native_event_rates: list[PerEntranceEventRow] = []

    for event in _NATIVE_EVENTS:
        event_users: set[str] = set(
            actions.loc[actions["action_type"] == event, "utid"].dropna()
        )
        cells_block2: dict[str, PerEntranceCell] = {}
        for entrance in _ENTRANCE_NAMES:
            loaded = loaded_users_by_entrance[entrance]
            cells_block2[entrance] = _cell(
                num=len(loaded & event_users),
                den=len(loaded),
            )
        native_event_rates.append(PerEntranceEventRow(
            event=event,
            cells=cells_block2,
        ))

    # ---- block 2 add-on: per-entrance "loaded vs not loaded" impact tables ----
    #
    # Population is restricted to ACTIVE utids — those who triggered at least
    # one of the 5 native events. This filters out passively-loaded users
    # (e.g. B-group users whose filter sidebar auto-loaded but who never
    # interacted with the page), so the loaded-vs-not-loaded comparison
    # reflects entrance position, not exposure-mechanism asymmetry.
    #
    # "all_loaded" = utids who loaded any of the 4 known entrances. Both
    # subsets are then intersected with the active set.
    all_loaded: set[str] = set()
    for s in loaded_users_by_entrance.values():
        all_loaded |= s

    active_utids: set[str] = set()
    event_users_cache: dict[str, set[str]] = {}
    for event in _NATIVE_EVENTS:
        ev_users = set(
            actions.loc[actions["action_type"] == event, "utid"].dropna()
        )
        event_users_cache[event] = ev_users
        active_utids |= ev_users

    impact_tables: list[EntranceImpactTable] = []
    for entrance in _ENTRANCE_NAMES:
        loaded = loaded_users_by_entrance[entrance] & active_utids
        not_loaded = (all_loaded - loaded_users_by_entrance[entrance]) & active_utids
        loaded_n = len(loaded)
        not_loaded_n = len(not_loaded)

        rows: list[EntranceImpactRow] = []
        for event in _IMPACT_EVENTS[entrance]:
            event_users = event_users_cache[event]
            loaded_hit = len(loaded & event_users)
            not_loaded_hit = len(not_loaded & event_users)
            loaded_rate = loaded_hit / loaded_n if loaded_n > 0 else float("nan")
            not_loaded_rate = (
                not_loaded_hit / not_loaded_n if not_loaded_n > 0 else float("nan")
            )
            rows.append(EntranceImpactRow(
                event=event,
                loaded_event_users=loaded_hit,
                loaded_rate=loaded_rate,
                not_loaded_event_users=not_loaded_hit,
                not_loaded_rate=not_loaded_rate,
                abs_diff=loaded_rate - not_loaded_rate,
            ))

        impact_tables.append(EntranceImpactTable(
            entrance=entrance,
            loaded_users=loaded_n,
            not_loaded_users=not_loaded_n,
            rows=rows,
        ))

    return EntranceSection(
        entrance_names=_ENTRANCE_NAMES,
        entrance_loaders=entrance_loaders,
        per_entrance=per_entrance,
        native_event_rates=native_event_rates,
        impact_tables=impact_tables,
    )
