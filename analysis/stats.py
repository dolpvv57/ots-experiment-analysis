"""Statistical tests for the experiment analysis.

- `two_proportion_z_test`: rate metrics (8 engagement + 4 redirect rates).
- `welch_t_test`: the `rounds` mean per chat session.
- `directional_verdict`: applies the ±2% "flat" rule per FR-007.

α = 0.05; no multiple-comparisons correction (FR-SIG-006). All tests are
two-sided.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

ALPHA = 0.05
FLAT_THRESHOLD_PCT = 2.0

DirectionalVerdict = Literal["positive", "flat", "negative"]
SignificanceVerdict = Literal["significant", "not_significant"]


@dataclass(frozen=True)
class StatResult:
    """Result of a single hypothesis test comparing variant A vs variant B."""

    p_value: float
    ci_low: float
    ci_high: float
    significance_verdict: SignificanceVerdict


def _significance(p_value: float, alpha: float = ALPHA) -> SignificanceVerdict:
    if math.isnan(p_value):
        return "not_significant"
    return "significant" if p_value < alpha else "not_significant"


def two_proportion_z_test(
    num_a: int,
    den_a: int,
    num_b: int,
    den_b: int,
    alpha: float = ALPHA,
) -> StatResult:
    """Wald z-test comparing two rates with a 95% CI for B − A.

    Uses the Bernoulli variance formula `p(1-p)/n` when both p1 and p2 lie in
    [0, 1] (true proportion case — e.g. utid-level metrics). Otherwise falls
    back to the Poisson variance formula `count/n^2`, which generalizes to
    count-per-user rates that can exceed 1 (e.g. correlation_id-per-user).
    """
    if den_a <= 0 or den_b <= 0:
        return StatResult(
            p_value=float("nan"),
            ci_low=float("nan"),
            ci_high=float("nan"),
            significance_verdict="not_significant",
        )

    p1 = num_a / den_a
    p2 = num_b / den_b
    diff = p2 - p1

    is_proportion = 0.0 <= p1 <= 1.0 and 0.0 <= p2 <= 1.0
    if is_proportion:
        p_pool = (num_a + num_b) / (den_a + den_b)
        if p_pool == 0.0 or p_pool == 1.0:
            # Zero variance: test is undefined (everyone or no one in numerator).
            return StatResult(
                p_value=float("nan"),
                ci_low=float("nan"),
                ci_high=float("nan"),
                significance_verdict="not_significant",
            )
        counts = np.array([num_a, num_b])
        nobs = np.array([den_a, den_b])
        try:
            _, p_value = proportions_ztest(counts, nobs, alternative="two-sided")
            p_value = float(p_value)
        except (ValueError, ZeroDivisionError):
            p_value = float("nan")
        se = math.sqrt(p1 * (1 - p1) / den_a + p2 * (1 - p2) / den_b)
    else:
        # Poisson Wald: Var(count/n) ≈ count / n^2.
        var = num_a / (den_a**2) + num_b / (den_b**2)
        if var <= 0:
            p_value = float("nan")
            se = float("nan")
        else:
            se = math.sqrt(var)
            z_obs = diff / se
            p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_obs)))

    if math.isnan(se):
        return StatResult(
            p_value=p_value,
            ci_low=float("nan"),
            ci_high=float("nan"),
            significance_verdict=_significance(p_value, alpha),
        )

    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_low = diff - z_crit * se
    ci_high = diff + z_crit * se

    return StatResult(
        p_value=p_value,
        ci_low=ci_low,
        ci_high=ci_high,
        significance_verdict=_significance(p_value, alpha),
    )


def welch_t_test(
    values_a: Sequence[float],
    values_b: Sequence[float],
    alpha: float = ALPHA,
) -> StatResult:
    """Welch's t-test (unequal variances) on two continuous samples.

    Returns p-value and 95% CI for the difference of means (B − A) computed
    from the t-distribution.
    """
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    if len(a) < 2 or len(b) < 2:
        return StatResult(
            p_value=float("nan"),
            ci_low=float("nan"),
            ci_high=float("nan"),
            significance_verdict="not_significant",
        )

    res = stats.ttest_ind(b, a, equal_var=False)
    diff = float(b.mean() - a.mean())
    var_a = a.var(ddof=1) / len(a)
    var_b = b.var(ddof=1) / len(b)
    se = math.sqrt(var_a + var_b)
    df = (var_a + var_b) ** 2 / (
        (var_a**2) / (len(a) - 1) + (var_b**2) / (len(b) - 1)
    )
    t = stats.t.ppf(1 - alpha / 2, df)
    ci_low = diff - t * se
    ci_high = diff + t * se

    return StatResult(
        p_value=float(res.pvalue),
        ci_low=ci_low,
        ci_high=ci_high,
        significance_verdict=_significance(float(res.pvalue), alpha),
    )


def directional_verdict(
    rel_lift_pct: float,
    flat_threshold_pct: float = FLAT_THRESHOLD_PCT,
) -> DirectionalVerdict:
    """Classify a relative lift as positive / flat / negative per FR-007."""
    if math.isnan(rel_lift_pct):
        return "flat"
    if rel_lift_pct > flat_threshold_pct:
        return "positive"
    if rel_lift_pct < -flat_threshold_pct:
        return "negative"
    return "flat"
