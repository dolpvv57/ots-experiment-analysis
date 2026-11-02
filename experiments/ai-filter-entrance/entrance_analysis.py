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
from analysis.stats import directional_verdict, two_proportion_z_test
from analysis.types import (
    ABStats,
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
_ENTRANCE_NAMES: list[str] = ["inline", "map", "filter (ps)", "filter (non-ps)", "search summary"]

# traffic_source values that identify Parallel Search traffic
_PS_TRAFFIC_SOURCES: frozenset[str] = frozenset({"parallel_search_flight_seo", "parallel_search"})

# entrance label -> (loaded_area, set of click areas)
_ENTRANCES: dict[str, tuple[str, frozenset[str]]] = {
    "inline":           ("INLINE", frozenset({"SEARCH_INPUT_IN_FEEDS", "SUGGESTION_BUTTON"})),
    "map":              ("ON_MAP", frozenset({"CHAT_BUTTON_ON_MAP"})),
    "filter (ps)":      ("SIDEBAR_FILTER_PANEL", frozenset({"CHAT_BOX_ON_FILTER_PANEL"})),
    "filter (non-ps)":  ("SIDEBAR_FILTER_PANEL", frozenset({"CHAT_BOX_ON_FILTER_PANEL"})),
    "search summary":   ("SEARCH_SUMMARY", frozenset({"CHAT_BUTTON_ON_SEARCH_SUMMARY"})),
}

# ps_filter: True = PS only, False = non-PS only, None = no filter
_ENTRANCE_PS_FILTER: dict[str, bool | None] = {
    "inline":           None,
    "map":              None,
    "filter (ps)":      True,
    "filter (non-ps)":  False,
    "search summary":   None,
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
    "inline":           ["DAY_VIEW_HOTEL_CARD_CLICKED"],
    "map":              ["MAP_MOVING_DAY_VIEW", "MAP_HOTEL_MARKER_CLICK", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "filter (ps)":      ["DAY_VIEW_FILTERS_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "filter (non-ps)":  ["DAY_VIEW_FILTERS_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "search summary":   ["DAY_VIEW_SORT_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
}



def _cell(num: int, den: int, redirect_num: int = 0) -> PerEntranceCell:
    rate = num / den if den > 0 else float("nan")
    redirect_rate = redirect_num / num if num > 0 else float("nan")
    return PerEntranceCell(
        numerator=num, denominator=den, rate=rate,
        redirect_count=redirect_num, redirect_rate=redirect_rate,
    )


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
            "traffic_source",
        ],
        dtype={
            "utid": "string",
            "action_type": "category",
            "chat_box_entry_loaded": "string",
            "chat_box_entry_click": "string",
            "traffic_source": "string",
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

    ots_chat_early = pd.read_csv(
        data_dir / "ots_chat.csv",
        usecols=["utid", "chat_type"],
        dtype={"utid": "string", "chat_type": "string"},
    )
    ots_chat_early = ots_chat_early[~ots_chat_early["utid"].isin(excluded_utids)]
    intent_utids: set[str] = set(
        ots_chat_early.loc[
            ots_chat_early["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION", "utid"
        ].dropna()
    )

    # Per-entrance loaded/clicked user sets (variant-agnostic).
    loaded_users_by_entrance: dict[str, set[str]] = {}
    clicked_users_by_entrance: dict[str, set[str]] = {}
    for entrance in _ENTRANCE_NAMES:
        loaded_area, click_areas = _ENTRANCES[entrance]
        ps_filter = _ENTRANCE_PS_FILTER[entrance]

        loaded_mask = loaded_rows["area"] == loaded_area
        click_mask = click_rows["area"].isin(click_areas)
        if ps_filter is True:
            loaded_mask = loaded_mask & loaded_rows["traffic_source"].isin(_PS_TRAFFIC_SOURCES)
            click_mask = click_mask & click_rows["traffic_source"].isin(_PS_TRAFFIC_SOURCES)
        elif ps_filter is False:
            loaded_mask = loaded_mask & ~loaded_rows["traffic_source"].isin(_PS_TRAFFIC_SOURCES)
            click_mask = click_mask & ~click_rows["traffic_source"].isin(_PS_TRAFFIC_SOURCES)

        loaded_users_by_entrance[entrance] = set(loaded_rows.loc[loaded_mask, "utid"].dropna())
        clicked_users_by_entrance[entrance] = set(click_rows.loc[click_mask, "utid"].dropna())

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

        chat_users_set = loaded_users & intent_utids
        chat_rate = len(chat_users_set) / len(loaded_users) if loaded_users else float("nan")

        redirected_clickers = clicked_in_loaded & redirected_utids
        rr = (
            len(redirected_clickers) / len(clicked_in_loaded)
            if clicked_in_loaded else float("nan")
        )

        redirected_chat = chat_users_set & redirected_utids
        rr_chat = (
            len(redirected_chat) / len(chat_users_set)
            if chat_users_set else float("nan")
        )

        per_entrance.append(EntrancePerformanceMetric(
            entrance=entrance,
            loaded_users=len(loaded_users),
            clicked_users=len(clicked_in_loaded),
            ctr_per_user=ctr,
            chat_users=len(chat_users_set),
            chat_rate=chat_rate,
            redirected_clickers=len(redirected_clickers),
            redirect_rate_clickers=rr,
            redirected_chat_users=len(redirected_chat),
            redirect_rate_chat_users=rr_chat,
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
            native_users = loaded & event_users
            cells_block2[entrance] = _cell(
                num=len(native_users),
                den=len(loaded),
                redirect_num=len(native_users & redirected_utids),
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
            loaded_redirect = len(loaded & event_users & redirected_utids)
            not_loaded_redirect = len(not_loaded & event_users & redirected_utids)
            loaded_redirect_rate = loaded_redirect / loaded_hit if loaded_hit > 0 else float("nan")
            not_loaded_redirect_rate = not_loaded_redirect / not_loaded_hit if not_loaded_hit > 0 else float("nan")
            rows.append(EntranceImpactRow(
                event=event,
                loaded_event_users=loaded_hit,
                loaded_rate=loaded_rate,
                loaded_redirect_count=loaded_redirect,
                loaded_redirect_rate=loaded_redirect_rate,
                not_loaded_event_users=not_loaded_hit,
                not_loaded_rate=not_loaded_rate,
                not_loaded_redirect_count=not_loaded_redirect,
                not_loaded_redirect_rate=not_loaded_redirect_rate,
                abs_diff=loaded_rate - not_loaded_rate,
                redirect_rate_diff=loaded_redirect_rate - not_loaded_redirect_rate,
            ))

        impact_tables.append(EntranceImpactTable(
            entrance=entrance,
            loaded_users=loaded_n,
            not_loaded_users=not_loaded_n,
            rows=rows,
        ))

    # ---- block 2 A/B table: native-event rates by variant group ----
    #
    # A group: utids who loaded inline or map, but NOT filter or search summary.
    # B group: utids who loaded filter or search summary, but NOT inline or map.
    # Overlap (dirty data) is excluded from both groups.
    ab_group_a = (
        loaded_users_by_entrance["inline"] | loaded_users_by_entrance["map"]
    ) - (
        loaded_users_by_entrance["filter (ps)"]
        | loaded_users_by_entrance["filter (non-ps)"]
        | loaded_users_by_entrance["search summary"]
    )
    ab_group_b = (
        loaded_users_by_entrance["filter (ps)"]
        | loaded_users_by_entrance["filter (non-ps)"]
        | loaded_users_by_entrance["search summary"]
    ) - (
        loaded_users_by_entrance["inline"] | loaded_users_by_entrance["map"]
    )
    # All utids per variant (full population, for the "all users" columns)
    ots_chat = pd.read_csv(
        data_dir / "ots_chat.csv",
        usecols=["utid", "variant"],
        dtype={"utid": "string", "variant": "string"},
    )
    ots_chat = ots_chat[~ots_chat["utid"].isin(excluded_utids)]
    all_a_utids = set(ots_chat.loc[ots_chat["variant"] == "A", "utid"].dropna())
    all_b_utids = set(ots_chat.loc[ots_chat["variant"] == "B", "utid"].dropna())

    ab_group_sizes = {
        "A": len(ab_group_a),
        "B": len(ab_group_b),
        "A_all": len(all_a_utids),
        "B_all": len(all_b_utids),
    }

    native_event_ab_rates: list[PerEntranceEventRow] = []
    for event in _NATIVE_EVENTS:
        ev_users = event_users_cache[event]
        num_a_all = len(all_a_utids & ev_users)
        den_a_all = len(all_a_utids)
        num_b_all = len(all_b_utids & ev_users)
        den_b_all = len(all_b_utids)
        stat = two_proportion_z_test(num_a_all, den_a_all, num_b_all, den_b_all)
        rate_a_all = num_a_all / den_a_all if den_a_all > 0 else float("nan")
        rate_b_all = num_b_all / den_b_all if den_b_all > 0 else float("nan")
        rel_lift = (
            (rate_b_all - rate_a_all) / rate_a_all * 100
            if rate_a_all > 0 else float("nan")
        )
        all_stats = ABStats(
            rel_lift_pct=rel_lift,
            p_value=stat.p_value,
            directional_verdict=directional_verdict(rel_lift),
            significance_verdict=stat.significance_verdict,
        )
        native_event_ab_rates.append(PerEntranceEventRow(
            event=event,
            cells={
                "A": _cell(len(ab_group_a & ev_users), len(ab_group_a)),
                "B": _cell(len(ab_group_b & ev_users), len(ab_group_b)),
                "A_all": _cell(num_a_all, den_a_all),
                "B_all": _cell(num_b_all, den_b_all),
            },
            all_users_ab_stats=all_stats,
        ))

    return EntranceSection(
        entrance_names=_ENTRANCE_NAMES,
        entrance_loaders=entrance_loaders,
        per_entrance=per_entrance,
        native_event_rates=native_event_rates,
        impact_tables=impact_tables,
        native_event_ab_rates=native_event_ab_rates,
        ab_group_sizes=ab_group_sizes,
    )
