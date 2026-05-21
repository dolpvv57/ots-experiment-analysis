"""Tests for analysis.stats."""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.stats import (
    directional_verdict,
    two_proportion_z_test,
    welch_t_test,
)


def test_two_proportion_z_test_obvious_difference() -> None:
    # 50/100 vs 90/100 — large gap, should be highly significant.
    result = two_proportion_z_test(50, 100, 90, 100)
    assert result.p_value < 1e-6
    assert result.significance_verdict == "significant"
    assert result.ci_low > 0  # B − A is positive and CI is above zero.
    assert result.ci_high > result.ci_low


def test_two_proportion_z_test_no_difference() -> None:
    # Identical rates — p-value should be 1.0.
    result = two_proportion_z_test(50, 100, 50, 100)
    assert math.isclose(result.p_value, 1.0, abs_tol=1e-12)
    assert result.significance_verdict == "not_significant"
    assert result.ci_low <= 0 <= result.ci_high


def test_two_proportion_z_test_zero_denominator() -> None:
    result = two_proportion_z_test(0, 0, 5, 10)
    assert math.isnan(result.p_value)
    assert result.significance_verdict == "not_significant"


def test_welch_t_test_obvious_difference() -> None:
    rng = np.random.default_rng(42)
    a = rng.normal(loc=0.0, scale=1.0, size=200)
    b = rng.normal(loc=1.0, scale=1.0, size=200)
    result = welch_t_test(a, b)
    assert result.p_value < 1e-6
    assert result.significance_verdict == "significant"
    assert result.ci_low > 0


def test_welch_t_test_too_small_sample() -> None:
    result = welch_t_test([1.0], [2.0])
    assert math.isnan(result.p_value)


@pytest.mark.parametrize(
    ("rel_lift_pct", "expected"),
    [
        (5.0, "positive"),
        (2.0, "flat"),  # exactly at the boundary -> flat
        (-2.0, "flat"),
        (-5.0, "negative"),
        (0.0, "flat"),
        (float("nan"), "flat"),
    ],
)
def test_directional_verdict_thresholds(rel_lift_pct: float, expected: str) -> None:
    assert directional_verdict(rel_lift_pct) == expected
