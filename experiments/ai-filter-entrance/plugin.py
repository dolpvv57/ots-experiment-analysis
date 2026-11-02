"""Entrance position analysis plugin for the ai-filter-entrance experiment.

Population: session_ids in actions.csv with at least one CHAT_BOX_ENTRY_LOADED,
after removing variant-conflict session_ids.

All blocks are variant-agnostic — every metric is sliced by entrance
(loaded_area), not by A/B. The entrance loader populations overlap:
e.g. an A-group user typically loads both `inline` and `map`. Each cell
is a within-entrance rate.

Block 1 — per-entrance CTR & redirect rate (5 entrances, descriptive).
Block 2 — native-feature usage rate, one cell per entrance (5 events × 5 entrances).
Block 2 add-on — loaded vs not-loaded comparison among active session_ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from analysis.load import DataBundle
from analysis.stats import directional_verdict, two_proportion_z_test
from analysis.types import DirectionalVerdict, SignificanceVerdict

TEMPLATE_FRAGMENT = "templates/section.html.j2"

_LOADED_ACTION = "CHAT_BOX_ENTRY_LOADED"
_CLICK_ACTION = "CHAT_BOX_ENTRY_CLICK"

_ENTRANCE_NAMES: list[str] = ["inline", "map", "filter (ps)", "filter (non-ps)", "search summary"]

_PS_TRAFFIC_SOURCES: frozenset[str] = frozenset({"parallel_search_flight_seo", "parallel_search"})

_ENTRANCES: dict[str, tuple[str, frozenset[str]]] = {
    "inline":           ("INLINE", frozenset({"SEARCH_INPUT_IN_FEEDS", "SUGGESTION_BUTTON"})),
    "map":              ("ON_MAP", frozenset({"CHAT_BUTTON_ON_MAP"})),
    "filter (ps)":      ("SIDEBAR_FILTER_PANEL", frozenset({"CHAT_BOX_ON_FILTER_PANEL"})),
    "filter (non-ps)":  ("SIDEBAR_FILTER_PANEL", frozenset({"CHAT_BOX_ON_FILTER_PANEL"})),
    "search summary":   ("SEARCH_SUMMARY", frozenset({"CHAT_BUTTON_ON_SEARCH_SUMMARY"})),
}

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

_IMPACT_EVENTS: dict[str, list[str]] = {
    "inline":           ["DAY_VIEW_HOTEL_CARD_CLICKED"],
    "map":              ["MAP_MOVING_DAY_VIEW", "MAP_HOTEL_MARKER_CLICK", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "filter (ps)":      ["DAY_VIEW_FILTERS_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "filter (non-ps)":  ["DAY_VIEW_FILTERS_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
    "search summary":   ["DAY_VIEW_SORT_USED", "DAY_VIEW_HOTEL_CARD_CLICKED"],
}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntrancePerformanceMetric:
    entrance: str
    loaded_users: int
    clicked_users: int
    ctr_per_user: float
    chat_users: int
    chat_rate: float
    redirected_clickers: int
    redirect_rate_clickers: float
    redirected_chat_users: int
    redirect_rate_chat_users: float


@dataclass(frozen=True)
class PerEntranceCell:
    numerator: int
    denominator: int
    rate: float
    redirect_count: int = 0
    redirect_rate: float = float("nan")


@dataclass(frozen=True)
class ABStats:
    rel_lift_pct: float
    p_value: float
    directional_verdict: DirectionalVerdict
    significance_verdict: SignificanceVerdict


@dataclass(frozen=True)
class PerEntranceEventRow:
    event: str
    cells: dict[str, PerEntranceCell]
    all_users_ab_stats: ABStats | None = None


@dataclass(frozen=True)
class EntranceImpactRow:
    event: str
    loaded_event_users: int
    loaded_rate: float
    loaded_redirect_count: int
    loaded_redirect_rate: float
    not_loaded_event_users: int
    not_loaded_rate: float
    not_loaded_redirect_count: int
    not_loaded_redirect_rate: float
    abs_diff: float
    redirect_rate_diff: float


@dataclass(frozen=True)
class EntranceImpactTable:
    entrance: str
    loaded_users: int
    not_loaded_users: int
    rows: list[EntranceImpactRow]


@dataclass(frozen=True)
class EntranceSection:
    entrance_names: list[str]
    entrance_loaders: dict[str, int]
    per_entrance: list[EntrancePerformanceMetric]
    native_event_rates: list[PerEntranceEventRow]
    impact_tables: list[EntranceImpactTable]
    native_event_ab_rates: list[PerEntranceEventRow]
    ab_group_sizes: dict[str, int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------

def compute(bundle: DataBundle, excluded_session_ids: set[str]) -> EntranceSection:
    actions = pd.read_csv(
        bundle.data_dir / "actions.csv",
        usecols=[
            "session_id", "action_type",
            "chat_box_entry_loaded", "chat_box_entry_click",
            "traffic_source",
        ],
        dtype={
            "session_id": "string",
            "action_type": "category",
            "chat_box_entry_loaded": "string",
            "chat_box_entry_click": "string",
            "traffic_source": "string",
        },
    )
    actions = actions[~actions["session_id"].isin(excluded_session_ids)]

    loaded_rows = actions[actions["action_type"] == _LOADED_ACTION].copy()
    click_rows = actions[actions["action_type"] == _CLICK_ACTION].copy()

    loaded_rows["area"] = loaded_rows["chat_box_entry_loaded"].apply(
        lambda s: _parse_field(s, "loaded_area")
    )
    click_rows["area"] = click_rows["chat_box_entry_click"].apply(
        lambda s: _parse_field(s, "open_chat_box_area")
    )

    redirected_session_ids: set[str] = set(bundle.redirects["session_id"].dropna())

    ots_chat = bundle.ots_chat[~bundle.ots_chat["session_id"].isin(excluded_session_ids)]
    intent_session_ids: set[str] = set(
        ots_chat.loc[
            ots_chat["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION", "session_id"
        ].dropna()
    )

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

        loaded_users_by_entrance[entrance] = set(loaded_rows.loc[loaded_mask, "session_id"].dropna())
        clicked_users_by_entrance[entrance] = set(click_rows.loc[click_mask, "session_id"].dropna())

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

        chat_users_set = loaded_users & intent_session_ids
        chat_rate = len(chat_users_set) / len(loaded_users) if loaded_users else float("nan")

        redirected_clickers = clicked_in_loaded & redirected_session_ids
        rr = (
            len(redirected_clickers) / len(clicked_in_loaded)
            if clicked_in_loaded else float("nan")
        )

        redirected_chat = chat_users_set & redirected_session_ids
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
            actions.loc[actions["action_type"] == event, "session_id"].dropna()
        )
        cells_block2: dict[str, PerEntranceCell] = {}
        for entrance in _ENTRANCE_NAMES:
            loaded = loaded_users_by_entrance[entrance]
            native_users = loaded & event_users
            cells_block2[entrance] = _cell(
                num=len(native_users),
                den=len(loaded),
                redirect_num=len(native_users & redirected_session_ids),
            )
        native_event_rates.append(PerEntranceEventRow(
            event=event,
            cells=cells_block2,
        ))

    # ---- block 2 add-on: per-entrance "loaded vs not loaded" impact tables ----

    all_loaded: set[str] = set()
    for s in loaded_users_by_entrance.values():
        all_loaded |= s

    active_session_ids: set[str] = set()
    event_users_cache: dict[str, set[str]] = {}
    for event in _NATIVE_EVENTS:
        ev_users = set(
            actions.loc[actions["action_type"] == event, "session_id"].dropna()
        )
        event_users_cache[event] = ev_users
        active_session_ids |= ev_users

    impact_tables: list[EntranceImpactTable] = []
    for entrance in _ENTRANCE_NAMES:
        loaded = loaded_users_by_entrance[entrance] & active_session_ids
        not_loaded = (all_loaded - loaded_users_by_entrance[entrance]) & active_session_ids
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
            loaded_redirect = len(loaded & event_users & redirected_session_ids)
            not_loaded_redirect = len(not_loaded & event_users & redirected_session_ids)
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

    all_a_session_ids = set(ots_chat.loc[ots_chat["variant"] == "A", "session_id"].dropna())
    all_b_session_ids = set(ots_chat.loc[ots_chat["variant"] == "B", "session_id"].dropna())

    ab_group_sizes = {
        "A": len(ab_group_a),
        "B": len(ab_group_b),
        "A_all": len(all_a_session_ids),
        "B_all": len(all_b_session_ids),
    }

    native_event_ab_rates: list[PerEntranceEventRow] = []
    for event in _NATIVE_EVENTS:
        ev_users = event_users_cache[event]
        num_a_all = len(all_a_session_ids & ev_users)
        den_a_all = len(all_a_session_ids)
        num_b_all = len(all_b_session_ids & ev_users)
        den_b_all = len(all_b_session_ids)
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


def count_tests(section: EntranceSection) -> int:
    return 0
