"""Inferential statistics for cross-channel comparisons.

Everything here is seeded and works on plain pandas / numpy objects. Single-comparison
helpers return dicts; per-group helpers return DataFrames.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from telegram_scraper.analysis._common import to_utc_timestamp

_BOOT_CHUNK_ELEMENTS = 2_000_000


# ---------------------------------------------------------------------------
# Posting rates
# ---------------------------------------------------------------------------


def _day_window(start: Any, end: Any) -> pd.DatetimeIndex:
    start_ts = to_utc_timestamp(start)
    end_ts = to_utc_timestamp(end)
    if end_ts <= start_ts:
        raise ValueError("end must be after start.")
    return pd.date_range(start_ts.floor("D"), end_ts.ceil("D"), freq="D", tz="UTC", inclusive="left")


def _daily_counts(
    posts_df: pd.DataFrame,
    group_col: str,
    ts_col: str,
    start: Any,
    end: Any,
) -> pd.DataFrame:
    """Calendar-day (UTC) post counts, days x groups, zero-filled across [start, end)."""
    days = _day_window(start, end)
    timestamps = pd.to_datetime(posts_df[ts_col], utc=True)
    in_window = (timestamps >= to_utc_timestamp(start)) & (timestamps < to_utc_timestamp(end))
    frame = pd.DataFrame({group_col: posts_df.loc[in_window, group_col], "day": timestamps[in_window].dt.floor("D")})
    counts = frame.groupby([group_col, "day"]).size().unstack(group_col, fill_value=0)
    counts = counts.reindex(index=days, fill_value=0)
    # Groups present in the data but with no posts in the window still get a zero column.
    missing = [group for group in posts_df[group_col].dropna().unique() if group not in counts.columns]
    for group in missing:
        counts[group] = 0
    return counts[sorted(counts.columns, key=str)]


def _bootstrap_day_means(counts: np.ndarray, indices: np.ndarray) -> np.ndarray:
    return counts[indices].mean(axis=1)


def _day_indices(n_days: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, n_days, size=(n_boot, n_days))


def _percentile_ci(values: np.ndarray, alpha: float) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    low, high = np.percentile(finite, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(low), float(high)


def daily_rate_ci(
    posts_df: pd.DataFrame,
    *,
    group_col: str = "channel_slug",
    ts_col: str = "timestamp",
    start: Any,
    end: Any,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Posts per day per group with a bootstrap-over-days CI.

    Days are UTC calendar days covering [start, end) and include zero-post days. Columns:
    ``group_col, n_posts, days, posts_per_day, ci_low, ci_high``.
    """
    counts = _daily_counts(posts_df, group_col, ts_col, start, end)
    n_days = len(counts)
    rng = np.random.default_rng(seed)
    indices = _day_indices(n_days, n_boot, rng)
    rows = []
    for group in counts.columns:
        values = counts[group].to_numpy(dtype=float)
        low, high = _percentile_ci(_bootstrap_day_means(values, indices), alpha)
        rows.append(
            {
                group_col: group,
                "n_posts": int(values.sum()),
                "days": n_days,
                "posts_per_day": float(values.mean()),
                "ci_low": low,
                "ci_high": high,
            }
        )
    return pd.DataFrame(rows)


def rate_ratio_ci(
    posts_df: pd.DataFrame,
    numerator_group: Any,
    denominator_group: Any,
    *,
    group_col: str = "channel_slug",
    ts_col: str = "timestamp",
    start: Any,
    end: Any,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Ratio of daily posting rates (numerator / denominator) with a joint day-resampling CI."""
    counts = _daily_counts(posts_df, group_col, ts_col, start, end)
    for group in (numerator_group, denominator_group):
        if group not in counts.columns:
            raise KeyError(f"Group {group!r} not found in {group_col!r}.")
    numerator = counts[numerator_group].to_numpy(dtype=float)
    denominator = counts[denominator_group].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    indices = _day_indices(len(counts), n_boot, rng)
    boot_num = _bootstrap_day_means(numerator, indices)
    boot_den = _bootstrap_day_means(denominator, indices)
    with np.errstate(divide="ignore", invalid="ignore"):
        boot_ratio = np.where(boot_den > 0, boot_num / boot_den, np.nan)
    low, high = _percentile_ci(boot_ratio, alpha)
    rate_den = float(denominator.mean())
    return {
        "numerator": numerator_group,
        "denominator": denominator_group,
        "days": len(counts),
        "rate_numerator": float(numerator.mean()),
        "rate_denominator": rate_den,
        "ratio": float(numerator.mean() / rate_den) if rate_den > 0 else float("nan"),
        "ci_low": low,
        "ci_high": high,
    }


# ---------------------------------------------------------------------------
# Proportions
# ---------------------------------------------------------------------------


def proportion_ci(successes: int, n: int, method: str = "wilson", alpha: float = 0.05) -> tuple[float, float]:
    """Confidence interval for a binomial proportion (statsmodels methods; default Wilson)."""
    from statsmodels.stats.proportion import proportion_confint

    if n <= 0:
        return float("nan"), float("nan")
    low, high = proportion_confint(int(successes), int(n), alpha=alpha, method=method)
    return float(low), float(high)


def share_table(df: pd.DataFrame, group_col: str, flag_col: str, *, method: str = "wilson", alpha: float = 0.05) -> pd.DataFrame:
    """Share of rows with a truthy ``flag_col`` per group, with CIs.

    Columns: ``group_col, n, successes, share, ci_low, ci_high``. Rows with a missing flag are dropped.
    """
    frame = df[[group_col, flag_col]].dropna()
    flags = frame[flag_col].astype(bool)
    grouped = flags.groupby(frame[group_col]).agg(["size", "sum"])
    rows = []
    for group, record in grouped.iterrows():
        n = int(record["size"])
        successes = int(record["sum"])
        low, high = proportion_ci(successes, n, method=method, alpha=alpha)
        rows.append(
            {
                group_col: group,
                "n": n,
                "successes": successes,
                "share": successes / n if n else float("nan"),
                "ci_low": low,
                "ci_high": high,
            }
        )
    return pd.DataFrame(rows, columns=[group_col, "n", "successes", "share", "ci_low", "ci_high"])


def keyword_share(
    df: pd.DataFrame,
    pattern: str,
    group_col: str,
    text_col: str = "text",
    *,
    flags: int = re.IGNORECASE,
    method: str = "wilson",
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Share of rows whose text matches regex ``pattern`` per group, with Wilson CIs."""
    matches = df[text_col].fillna("").astype(str).str.contains(pattern, flags=flags, regex=True)
    frame = pd.DataFrame({group_col: df[group_col].to_numpy(), "_match": matches.to_numpy()})
    return share_table(frame, group_col, "_match", method=method, alpha=alpha)


def two_proportion_test(x1: int, n1: int, x2: int, n2: int, *, alpha: float = 0.05) -> dict[str, float]:
    """Compare two proportions: difference, Newcombe (Wilson-score) CI, pooled z-test and Fisher exact p."""
    if n1 <= 0 or n2 <= 0:
        raise ValueError("n1 and n2 must be positive.")
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = proportion_ci(x1, n1, alpha=alpha)
    l2, u2 = proportion_ci(x2, n2, alpha=alpha)
    diff = p1 - p2
    ci_low = diff - np.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    ci_high = diff + np.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)

    pooled = (x1 + x2) / (n1 + n2)
    se = np.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se > 0:
        z = diff / se
        p_value = float(2 * scipy_stats.norm.sf(abs(z)))
    else:
        z, p_value = float("nan"), 1.0
    _, p_fisher = scipy_stats.fisher_exact([[x1, n1 - x1], [x2, n2 - x2]])
    return {
        "p1": float(p1),
        "p2": float(p2),
        "diff": float(diff),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "z": float(z),
        "p_value": p_value,
        "p_fisher": float(p_fisher),
    }


# ---------------------------------------------------------------------------
# Means
# ---------------------------------------------------------------------------


def _clean_values(values: Any) -> np.ndarray:
    array = np.asarray(pd.Series(values).dropna(), dtype=float)
    if array.size == 0:
        raise ValueError("No non-missing values.")
    return array


def _bootstrap_means(values: np.ndarray, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    n = len(values)
    chunk = max(1, _BOOT_CHUNK_ELEMENTS // n)
    out = np.empty(n_boot, dtype=float)
    for offset in range(0, n_boot, chunk):
        size = min(chunk, n_boot - offset)
        out[offset : offset + size] = values[rng.integers(0, n, size=(size, n))].mean(axis=1)
    return out


def bootstrap_mean_ci(values: Any, *, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict[str, float]:
    """Percentile-bootstrap CI for a mean. Keys: ``n, mean, ci_low, ci_high``."""
    array = _clean_values(values)
    rng = np.random.default_rng(seed)
    low, high = _percentile_ci(_bootstrap_means(array, n_boot, rng), alpha)
    return {"n": int(array.size), "mean": float(array.mean()), "ci_low": low, "ci_high": high}


def mean_diff_ci(a: Any, b: Any, *, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict[str, float]:
    """Mean(a) - mean(b) with an independent-resampling bootstrap CI and a Welch t-test p-value."""
    array_a, array_b = _clean_values(a), _clean_values(b)
    rng = np.random.default_rng(seed)
    boot_diff = _bootstrap_means(array_a, n_boot, rng) - _bootstrap_means(array_b, n_boot, rng)
    low, high = _percentile_ci(boot_diff, alpha)
    if array_a.size > 1 and array_b.size > 1 and (array_a.std() > 0 or array_b.std() > 0):
        p_value = float(scipy_stats.ttest_ind(array_a, array_b, equal_var=False).pvalue)
    else:
        p_value = float("nan")
    return {
        "n_a": int(array_a.size),
        "n_b": int(array_b.size),
        "mean_a": float(array_a.mean()),
        "mean_b": float(array_b.mean()),
        "diff": float(array_a.mean() - array_b.mean()),
        "ci_low": low,
        "ci_high": high,
        "p_welch": p_value,
    }


def tost_equivalence(a: Any, b: Any, margin: float, *, alpha: float = 0.05) -> dict[str, Any]:
    """Two one-sided Welch tests that |mean(a) - mean(b)| < margin.

    ``p_lower`` tests H0: diff <= -margin, ``p_upper`` tests H0: diff >= +margin,
    ``p_tost = max(p_lower, p_upper)``; ``equivalent`` is ``p_tost < alpha``. ``ci90_*`` is the
    (1 - 2*alpha) Welch interval, which lies inside (-margin, margin) iff equivalence holds.
    """
    if margin <= 0:
        raise ValueError("margin must be positive.")
    array_a, array_b = _clean_values(a), _clean_values(b)
    if array_a.size < 2 or array_b.size < 2:
        raise ValueError("Each sample needs at least two values.")
    var_a, var_b = array_a.var(ddof=1), array_b.var(ddof=1)
    se_a, se_b = var_a / array_a.size, var_b / array_b.size
    se = float(np.sqrt(se_a + se_b))
    diff = float(array_a.mean() - array_b.mean())
    if se == 0:
        within = abs(diff) < margin
        p_lower = p_upper = 0.0 if within else 1.0
        ci = (diff, diff)
        dof = float("nan")
    else:
        dof = float((se_a + se_b) ** 2 / (se_a**2 / (array_a.size - 1) + se_b**2 / (array_b.size - 1)))
        p_lower = float(scipy_stats.t.sf((diff + margin) / se, dof))
        p_upper = float(scipy_stats.t.cdf((diff - margin) / se, dof))
        half_width = scipy_stats.t.ppf(1 - alpha, dof) * se
        ci = (diff - half_width, diff + half_width)
    p_tost = max(p_lower, p_upper)
    return {
        "mean_diff": diff,
        "margin": float(margin),
        "dof": dof,
        "p_lower": p_lower,
        "p_upper": p_upper,
        "p_tost": p_tost,
        "equivalent": bool(p_tost < alpha),
        "ci90_low": float(ci[0]),
        "ci90_high": float(ci[1]),
    }


# ---------------------------------------------------------------------------
# Categorical association
# ---------------------------------------------------------------------------


def collapse_rare_categories(
    df: pd.DataFrame,
    col: str,
    min_expected: float = 5,
    other_label: str = "Other",
    *,
    group_col: str | None = None,
) -> pd.DataFrame:
    """Return a copy of ``df`` with sparse categories of ``col`` merged into ``other_label``.

    With ``group_col`` the rule guarantees every cell of the group x category contingency table
    has expected count >= ``min_expected`` (expected = row_total * col_total / N, so each category
    needs ``col_total >= min_expected * N / smallest_group_size``). Without ``group_col`` it only
    requires ``col_total >= min_expected``. If the merged "Other" bucket is itself too small it
    absorbs the next-smallest categories until it is large enough.
    """
    data = df.copy()
    totals = data[col].value_counts()
    n_total = int(totals.sum())
    if n_total == 0:
        return data
    if group_col is None:
        threshold = float(min_expected)
    else:
        min_group = int(data.loc[data[col].notna(), group_col].value_counts().min())
        threshold = min_expected * n_total / max(min_group, 1)

    ordered = totals.sort_values(kind="mergesort")  # ascending
    collapsed = [category for category, count in ordered.items() if count < threshold]
    if collapsed:
        other_total = int(ordered[collapsed].sum())
        remaining = [category for category in ordered.index if category not in collapsed]
        while other_total < threshold and remaining:
            nxt = remaining.pop(0)
            collapsed.append(nxt)
            other_total += int(ordered[nxt])
        data[col] = data[col].where(~data[col].isin(collapsed), other_label)
    return data


def chi_square_by_group(
    df: pd.DataFrame,
    group_col: str,
    cat_col: str,
    min_expected: float = 5,
    *,
    other_label: str = "Other",
) -> dict[str, Any]:
    """Chi-square test of independence between group and category after collapsing sparse categories.

    Returns ``chi2, dof, p_value, n, n_groups, n_categories`` (after collapse),
    ``min_expected_count``, ``cramers_v``, ``cramers_v_bias_corrected`` (Bergsma 2013) and
    ``collapsed_categories``. Statistics are NaN when the collapsed table is smaller than 2 x 2.
    """
    frame = df[[group_col, cat_col]].dropna()
    original = set(frame[cat_col].unique())
    collapsed_frame = collapse_rare_categories(
        frame, cat_col, min_expected=min_expected, other_label=other_label, group_col=group_col
    )
    table = pd.crosstab(collapsed_frame[group_col], collapsed_frame[cat_col])
    n_groups, n_categories = table.shape
    n = int(table.to_numpy().sum())
    collapsed_categories = sorted(original - set(collapsed_frame[cat_col].unique()), key=str)

    result: dict[str, Any] = {
        "chi2": float("nan"),
        "dof": 0,
        "p_value": float("nan"),
        "n": n,
        "n_groups": int(n_groups),
        "n_categories": int(n_categories),
        "min_expected_count": float("nan"),
        "cramers_v": float("nan"),
        "cramers_v_bias_corrected": float("nan"),
        "collapsed_categories": collapsed_categories,
    }
    if n_groups < 2 or n_categories < 2:
        return result

    chi2, p_value, dof, expected = scipy_stats.chi2_contingency(table.to_numpy(), correction=False)
    r, k = n_groups, n_categories
    v = float(np.sqrt(chi2 / (n * min(r - 1, k - 1))))
    phi2_corrected = max(0.0, chi2 / n - (k - 1) * (r - 1) / (n - 1))
    k_corrected = k - (k - 1) ** 2 / (n - 1)
    r_corrected = r - (r - 1) ** 2 / (n - 1)
    denominator = min(k_corrected - 1, r_corrected - 1)
    v_corrected = float(np.sqrt(phi2_corrected / denominator)) if denominator > 0 else float("nan")
    result.update(
        chi2=float(chi2),
        dof=int(dof),
        p_value=float(p_value),
        min_expected_count=float(expected.min()),
        cramers_v=v,
        cramers_v_bias_corrected=v_corrected,
    )
    return result


# ---------------------------------------------------------------------------
# Multiple comparisons
# ---------------------------------------------------------------------------


def bh_adjust(pvalues: pd.Series, *, alpha: float = 0.05) -> pd.Series:
    """Benjamini-Hochberg adjusted p-values (same index; NaNs are left as NaN and not counted)."""
    from statsmodels.stats.multitest import multipletests

    series = pd.Series(pvalues, dtype=float)
    adjusted = pd.Series(np.nan, index=series.index, dtype=float, name=series.name)
    valid = series.notna()
    if valid.any():
        adjusted.loc[valid] = multipletests(series[valid].to_numpy(), alpha=alpha, method="fdr_bh")[1]
    return adjusted
