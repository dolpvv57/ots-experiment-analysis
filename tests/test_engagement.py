"""Tests for analysis.engagement against the tiny fixture."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from analysis.engagement import (
    compute_engagement_metrics,
    compute_engagement_trends,
    compute_rounds_metric,
)
from analysis.load import (
    build_variant_lookup,
    compute_variant_population,
    load_data,
)


@pytest.fixture(scope="module")
def setup(fixtures_dir: Path):
    bundle = load_data(fixtures_dir)
    _, excluded = build_variant_lookup(bundle.ots_chat)
    pop = compute_variant_population(bundle.ots_chat, excluded)
    chat = bundle.ots_chat[~bundle.ots_chat["session_id"].isin(excluded)]
    return chat, pop


def _find(metrics, chat_type, dimension):
    for m in metrics:
        if m.chat_type == chat_type and m.dimension == dimension:
            return m
    raise AssertionError(f"missing metric ({chat_type}, {dimension})")


def test_engagement_metric_count_correct(setup) -> None:
    chat, pop = setup
    metrics = compute_engagement_metrics(chat, pop)
    assert len(metrics) == 8


def test_engagement_suggestions_per_session_id(setup) -> None:
    """A: {u1, u2}=2/2=1.0; B: {u3, u4, u5}=3/4=0.75."""
    chat, pop = setup
    metrics = compute_engagement_metrics(chat, pop)
    m = _find(metrics, "CHAT_TYPE_SUGGESTIONS", "session_id")
    assert m.count_A == 2
    assert m.count_B == 3
    assert math.isclose(m.value_A, 1.0)
    assert math.isclose(m.value_B, 0.75)


def test_engagement_intent_per_session_id(setup) -> None:
    """A: {u1}=1/2=0.5; B: {u3, u4, u6}=3/4=0.75."""
    chat, pop = setup
    metrics = compute_engagement_metrics(chat, pop)
    m = _find(metrics, "CHAT_TYPE_INTENT_RECOGNITION", "session_id")
    assert m.count_A == 1
    assert m.count_B == 3
    assert math.isclose(m.value_A, 0.5)
    assert math.isclose(m.value_B, 0.75)


def test_engagement_intent_per_session_excludes_empty(setup) -> None:
    """SUGGESTIONS sessions are empty → count is 0; INTENT sessions count as expected."""
    chat, pop = setup
    metrics = compute_engagement_metrics(chat, pop)
    m_sug = _find(metrics, "CHAT_TYPE_SUGGESTIONS", "chat_session_id")
    assert m_sug.count_A == 0  # all SUGGESTIONS rows have empty session_id
    assert m_sug.count_B == 0

    m_int = _find(metrics, "CHAT_TYPE_INTENT_RECOGNITION", "chat_session_id")
    assert m_int.count_A == 1  # {s1}
    assert m_int.count_B == 3  # {s2, s3, s4}


def test_engagement_intent_per_correlation_id(setup) -> None:
    """A: {c2}=1; B: {c5, c7, c8, c10}=4."""
    chat, pop = setup
    metrics = compute_engagement_metrics(chat, pop)
    m = _find(metrics, "CHAT_TYPE_INTENT_RECOGNITION", "correlation_id")
    assert m.count_A == 1
    assert m.count_B == 4


def test_rounds_metric(setup) -> None:
    """A sessions: [s1=2]; B sessions: [s2=3, s3=max(1,2)=2, s4=1]."""
    chat, _ = setup
    rm = compute_rounds_metric(chat)
    assert rm.n_sessions_A == 1
    assert rm.n_sessions_B == 3
    assert math.isclose(rm.mean_A, 2.0)
    assert math.isclose(rm.mean_B, 2.0)
    assert math.isclose(rm.median_A, 2.0)
    assert math.isclose(rm.median_B, 2.0)
    # Welch's t needs ≥2 samples on each side; A has only 1 → NaN.
    assert math.isnan(rm.p_value)


def test_engagement_trends_abs(setup) -> None:
    chat, _ = setup
    abs_chart, _ratio = compute_engagement_trends(chat)
    assert abs_chart.chart_id == "engagement_abs"

    session_id = abs_chart.session_id_panel
    # 2026-04-10: A=1 (u1), B=1 (u3); 2026-04-11: B=2 (u4, u6); A absent.
    apr10_a = session_id[(session_id["dt"] == pd.Timestamp("2026-04-10")) & (session_id["variant"] == "A")]
    apr10_b = session_id[(session_id["dt"] == pd.Timestamp("2026-04-10")) & (session_id["variant"] == "B")]
    apr11_b = session_id[(session_id["dt"] == pd.Timestamp("2026-04-11")) & (session_id["variant"] == "B")]
    assert apr10_a["value"].iloc[0] == 1
    assert apr10_b["value"].iloc[0] == 1
    assert apr11_b["value"].iloc[0] == 2

    sess = abs_chart.chat_session_panel
    apr11_b_sess = sess[(sess["dt"] == pd.Timestamp("2026-04-11")) & (sess["variant"] == "B")]
    assert apr11_b_sess["value"].iloc[0] == 2  # {s3, s4}


def test_engagement_trends_ratio(setup) -> None:
    chat, _ = setup
    _abs, ratio_chart = compute_engagement_trends(chat)
    assert ratio_chart.chart_id == "engagement_ratio"

    session_id = ratio_chart.session_id_panel
    # 2026-04-10 A: INTENT_session_ids={u1}=1, SUGG_session_ids={u1, u2}=2 → 0.5.
    row = session_id[(session_id["dt"] == pd.Timestamp("2026-04-10")) & (session_id["variant"] == "A")]
    assert math.isclose(row["value"].iloc[0], 0.5)

    # 2026-04-11 B: INTENT_session_ids={u4, u6}=2, SUGG_session_ids={u4}=1 → 2.0.
    row = session_id[(session_id["dt"] == pd.Timestamp("2026-04-11")) & (session_id["variant"] == "B")]
    assert math.isclose(row["value"].iloc[0], 2.0)

    # Session panel uses SUGGESTIONS row count as denominator.
    # 2026-04-10 A: INTENT_sessions={s1}=1, SUGG_rows=2 (c1, c3) → 0.5.
    sess = ratio_chart.chat_session_panel
    row = sess[(sess["dt"] == pd.Timestamp("2026-04-10")) & (sess["variant"] == "A")]
    assert math.isclose(row["value"].iloc[0], 0.5)
