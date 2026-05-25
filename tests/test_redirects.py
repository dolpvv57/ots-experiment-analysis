"""Tests for analysis.redirects against the tiny fixture."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from analysis.load import (
    build_variant_lookup,
    compute_variant_population,
    load_data,
)
from analysis.redirects import (
    build_redirect_attributed,
    compute_redirect_funnel_metric,
    compute_redirect_metrics,
    compute_redirect_trends,
)


@pytest.fixture(scope="module")
def setup(fixtures_dir: Path):
    bundle = load_data(fixtures_dir)
    _, excluded = build_variant_lookup(bundle.ots_chat)
    pop = compute_variant_population(bundle.ots_chat, excluded)
    chat = bundle.ots_chat[~bundle.ots_chat["utid"].isin(excluded)]
    attributed = build_redirect_attributed(chat, bundle.redirects)
    return chat, pop, attributed


def _by_dim(metrics, dimension):
    for m in metrics:
        if m.dimension == dimension:
            return m
    raise AssertionError(f"missing dimension {dimension}")


def test_attribution_excludes_suggestions(setup) -> None:
    """Only INTENT chat rows can produce a redirect; SUGGESTIONS rows are dropped."""
    _, _, attributed = setup
    # Fixture: 3 INTENT correlation_ids match a redirect (c5, c7, c8).
    assert len(attributed) == 3
    assert set(attributed["correlation_id"]) == {"c5", "c7", "c8"}


def test_attribution_drops_unmatched_redirects(setup) -> None:
    """redirects with no matching chat row (c_unknown) are excluded."""
    _, _, attributed = setup
    assert "c_unknown" not in set(attributed["correlation_id"])


def test_redirect_metric_per_utid(setup) -> None:
    """A: 0/{u1}=0%; B: 2/3≈66.67% (B redirect utids: u3, u4 of {u3, u4, u6})."""
    chat, _, attributed = setup
    intent_chat = chat[chat["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"]
    metrics = compute_redirect_metrics(attributed, intent_chat)
    m = _by_dim(metrics, "utid")
    assert m.numerator_A == 0
    assert m.denominator_A == 1
    assert m.numerator_B == 2
    assert m.denominator_B == 3
    assert math.isclose(m.rate_A, 0.0)
    assert math.isclose(m.rate_B, 2 / 3)


def test_redirect_metric_per_correlation_id(setup) -> None:
    """A: 0/1=0%; B: 3/4=75%."""
    chat, _, attributed = setup
    intent_chat = chat[chat["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"]
    metrics = compute_redirect_metrics(attributed, intent_chat)
    m = _by_dim(metrics, "correlation_id")
    assert m.numerator_B == 3
    assert m.denominator_B == 4
    assert math.isclose(m.rate_B, 0.75)


def test_redirect_metric_per_session_excludes_empty(setup) -> None:
    """B: {s2, s3}/{s2, s3, s4} = 2/3."""
    chat, _, attributed = setup
    intent_chat = chat[chat["chat_type"] == "CHAT_TYPE_INTENT_RECOGNITION"]
    metrics = compute_redirect_metrics(attributed, intent_chat)
    m = _by_dim(metrics, "chat_session_id")
    assert m.numerator_B == 2
    assert m.denominator_B == 3


def test_funnel_uses_variant_population_denominator(setup) -> None:
    """Funnel: A=0/2=0%; B=2/4=50%."""
    _, pop, attributed = setup
    funnel = compute_redirect_funnel_metric(attributed, pop)
    assert funnel.numerator_A == 0
    assert funnel.numerator_B == 2
    assert funnel.denominator_A == 2  # variant_population[A]
    assert funnel.denominator_B == 4  # variant_population[B]
    assert math.isclose(funnel.rate_A, 0.0)
    assert math.isclose(funnel.rate_B, 0.5)


def test_redirect_trends_abs(setup) -> None:
    chat, _, attributed = setup
    abs_chart, _ratio = compute_redirect_trends(chat, attributed)
    assert abs_chart.chart_id == "redirect_abs"

    utid = abs_chart.utid_panel
    apr10_b = utid[(utid["dt"] == pd.Timestamp("2026-04-10")) & (utid["variant"] == "B")]
    apr11_b = utid[(utid["dt"] == pd.Timestamp("2026-04-11")) & (utid["variant"] == "B")]
    assert apr10_b["value"].iloc[0] == 1  # u3
    assert apr11_b["value"].iloc[0] == 1  # u4


def test_redirect_trends_ratio(setup) -> None:
    chat, _, attributed = setup
    _abs, ratio_chart = compute_redirect_trends(chat, attributed)
    assert ratio_chart.chart_id == "redirect_ratio"

    utid = ratio_chart.utid_panel
    # 2026-04-10 B: redirect_utids={u3}=1, INTENT_utids={u3}=1 → 1.0.
    row = utid[(utid["dt"] == pd.Timestamp("2026-04-10")) & (utid["variant"] == "B")]
    assert math.isclose(row["value"].iloc[0], 1.0)
    # 2026-04-11 B: redirect_utids={u4}=1, INTENT_utids={u4, u6}=2 → 0.5.
    row = utid[(utid["dt"] == pd.Timestamp("2026-04-11")) & (utid["variant"] == "B")]
    assert math.isclose(row["value"].iloc[0], 0.5)
