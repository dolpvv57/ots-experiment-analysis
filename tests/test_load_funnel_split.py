"""Tests for analysis.engagement.split_by_traffic_source + the resulting funnels."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from analysis.engagement import compute_load_funnel_metric, split_by_traffic_source
from analysis.load import build_variant_lookup, load_data


@pytest.fixture(scope="module")
def setup(fixtures_dir: Path):
    bundle = load_data(fixtures_dir)
    _, excluded = build_variant_lookup(bundle.ots_chat)
    chat = bundle.ots_chat[~bundle.ots_chat["session_id"].isin(excluded)]
    return bundle.actions, chat


def test_split_requires_traffic_source_column(setup) -> None:
    _, chat = setup
    actions_no_col = pd.DataFrame({"session_id": ["u1"], "action_type": ["CHAT_BOX_ENTRY_LOADED"]})
    with pytest.raises(ValueError, match="traffic_source"):
        split_by_traffic_source(actions_no_col, chat)


def test_split_partitions_loaded_sessions(setup) -> None:
    """Fixture: loaded={u1,u2,u3,u4,u5}; parallel={u1,u3,u5}; non_parallel={u2,u4}.

    u6 never loaded (no actions.csv row) so belongs to neither group.
    """
    actions, chat = setup
    (parallel_actions, parallel_chat), (non_parallel_actions, non_parallel_chat) = (
        split_by_traffic_source(actions, chat)
    )
    assert set(parallel_actions["session_id"].unique()) == {"u1", "u3", "u5"}
    assert set(non_parallel_actions["session_id"].unique()) == {"u2", "u4"}
    assert "u6" not in set(parallel_chat["session_id"]) | set(non_parallel_chat["session_id"])


def test_parallel_funnel_rates(setup) -> None:
    """Parallel group: load A={u1}=1, B={u3,u5}=2.

    Click: u1 clicked (A=1/1=100%); u3 clicked, u5 not (B=1/2=50%).
    Chat: u1 INTENT (A=1/1=100%); u3 INTENT, u5 not (B=1/2=50%).
    """
    actions, chat = setup
    (parallel_actions, parallel_chat), _ = split_by_traffic_source(actions, chat)
    f = compute_load_funnel_metric(parallel_actions, parallel_chat)
    assert f.load_A == 1
    assert f.load_B == 2
    assert f.click_A == 1
    assert f.click_B == 1
    assert math.isclose(f.click_rate_A, 1.0)
    assert math.isclose(f.click_rate_B, 0.5)
    assert f.chat_A == 1
    assert f.chat_B == 1
    assert math.isclose(f.chat_rate_A, 1.0)
    assert math.isclose(f.chat_rate_B, 0.5)


def test_non_parallel_funnel_rates(setup) -> None:
    """Non-parallel group: load A={u2}=1, B={u4}=1.

    Click: u2 not clicked (A=0/1=0%); u4 clicked (B=1/1=100%).
    Chat: u2 not INTENT (A=0/1=0%); u4 INTENT (B=1/1=100%).
    """
    actions, chat = setup
    _, (non_parallel_actions, non_parallel_chat) = split_by_traffic_source(actions, chat)
    f = compute_load_funnel_metric(non_parallel_actions, non_parallel_chat)
    assert f.load_A == 1
    assert f.load_B == 1
    assert f.click_A == 0
    assert f.click_B == 1
    assert math.isclose(f.click_rate_A, 0.0)
    assert math.isclose(f.click_rate_B, 1.0)
    assert f.chat_A == 0
    assert f.chat_B == 1
    assert math.isclose(f.chat_rate_A, 0.0)
    assert math.isclose(f.chat_rate_B, 1.0)
