import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats

from telegram_scraper.analysis.stats import (
    bh_adjust,
    bootstrap_mean_ci,
    chi_square_by_group,
    collapse_rare_categories,
    daily_rate_ci,
    keyword_share,
    mean_diff_ci,
    proportion_ci,
    rate_ratio_ci,
    share_table,
    tost_equivalence,
    two_proportion_test,
)


def _posts(per_day_a, per_day_b, start="2025-01-01"):
    rows = []
    for day_offset, (na, nb) in enumerate(zip(per_day_a, per_day_b)):
        day = pd.Timestamp(start, tz="UTC") + pd.Timedelta(days=day_offset)
        for index in range(na):
            rows.append({"channel_slug": "a", "timestamp": day + pd.Timedelta(hours=index % 24)})
        for index in range(nb):
            rows.append({"channel_slug": "b", "timestamp": day + pd.Timedelta(hours=index % 24)})
    return pd.DataFrame(rows)


def test_wilson_ci_five_of_ten():
    low, high = proportion_ci(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3)
    assert high == pytest.approx(0.7634, abs=1e-3)
    assert all(np.isnan(proportion_ci(0, 0)))


def test_share_table_and_keyword_share():
    df = pd.DataFrame(
        {
            "channel_slug": ["a"] * 10 + ["b"] * 10,
            "flag": [True] * 5 + [False] * 5 + [False] * 10,
            "text": ["Memorial day"] * 5 + ["other"] * 5 + ["x"] * 10,
        }
    )
    table = share_table(df, "channel_slug", "flag").set_index("channel_slug")
    assert table.loc["a", "share"] == 0.5
    assert table.loc["a", "ci_low"] == pytest.approx(0.2366, abs=1e-3)
    assert table.loc["b", "successes"] == 0
    kw = keyword_share(df, r"memorial", "channel_slug").set_index("channel_slug")
    assert kw.loc["a", "successes"] == 5
    assert kw.loc["b", "share"] == 0.0
    assert kw.loc["b", "ci_low"] == 0.0 and kw.loc["b", "ci_high"] > 0


def test_two_proportion_test_known_values():
    result = two_proportion_test(50, 100, 30, 100)
    assert result["diff"] == pytest.approx(0.2)
    assert result["ci_low"] < 0.2 < result["ci_high"]
    assert result["ci_low"] > 0  # clearly different
    assert result["p_value"] < 0.01
    # pooled z: p=0.4, se=sqrt(.4*.6*.02)
    assert result["z"] == pytest.approx(0.2 / np.sqrt(0.4 * 0.6 * 0.02))
    same = two_proportion_test(30, 100, 30, 100)
    assert same["diff"] == 0 and same["p_value"] == pytest.approx(1.0)


def test_bh_adjust_fixed_vector():
    adjusted = bh_adjust(pd.Series([0.01, 0.04, 0.03, 0.005], index=list("abcd")))
    assert adjusted.to_dict() == pytest.approx({"a": 0.02, "b": 0.04, "c": 0.04, "d": 0.02})
    with_nan = bh_adjust(pd.Series([0.01, np.nan, 0.02]))
    assert np.isnan(with_nan.iloc[1])
    assert with_nan.iloc[0] == pytest.approx(0.02)


def test_bootstrap_mean_ci_brackets_mean_and_is_seeded():
    values = np.random.default_rng(1).normal(5, 2, 200)
    first = bootstrap_mean_ci(values, seed=3)
    second = bootstrap_mean_ci(values, seed=3)
    assert first == second
    assert first["ci_low"] < first["mean"] < first["ci_high"]
    assert first["mean"] == pytest.approx(values.mean())


def test_mean_diff_ci_detects_shift():
    rng = np.random.default_rng(2)
    a, b = rng.normal(1.0, 1, 300), rng.normal(0.0, 1, 300)
    result = mean_diff_ci(a, b)
    assert result["ci_low"] > 0
    assert result["p_welch"] < 0.001
    assert result["diff"] == pytest.approx(a.mean() - b.mean())


def test_tost_equivalent_vs_not():
    rng = np.random.default_rng(3)
    a, b = rng.normal(0.0, 1, 400), rng.normal(0.02, 1, 400)
    equivalent = tost_equivalence(a, b, margin=0.3)
    assert equivalent["equivalent"] is True
    assert equivalent["p_tost"] == max(equivalent["p_lower"], equivalent["p_upper"])
    assert -0.3 < equivalent["ci90_low"] < equivalent["ci90_high"] < 0.3

    shifted = tost_equivalence(a, b + 0.5, margin=0.3)
    assert shifted["equivalent"] is False
    assert shifted["p_upper"] > 0.05 or shifted["p_lower"] > 0.05

    # tiny sample, same means: too little data to claim equivalence
    small = tost_equivalence(a[:5], b[:5], margin=0.3)
    assert small["equivalent"] is False


def test_tost_matches_statsmodels():
    from statsmodels.stats.weightstats import ttost_ind

    rng = np.random.default_rng(4)
    a, b = rng.normal(0, 1, 50), rng.normal(0.1, 1.5, 70)
    ours = tost_equivalence(a, b, margin=0.5)
    p, (_, p1, _), (_, p2, _) = ttost_ind(a, b, -0.5, 0.5, usevar="unequal")
    assert ours["p_tost"] == pytest.approx(p)
    assert ours["p_lower"] == pytest.approx(p1)
    assert ours["p_upper"] == pytest.approx(p2)


def test_tost_rejects_bad_margin():
    with pytest.raises(ValueError):
        tost_equivalence([1, 2, 3], [1, 2, 3], margin=0)


def test_daily_rate_ci_brackets_point_estimate_and_includes_zero_days():
    posts = _posts([4, 0, 6, 2, 0, 8, 4, 0], [1, 1, 1, 1, 1, 1, 1, 1])
    start, end = pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-01-09", tz="UTC")
    table = daily_rate_ci(posts, group_col="channel_slug", start=start, end=end).set_index("channel_slug")
    assert table.loc["a", "days"] == 8
    assert table.loc["a", "n_posts"] == 24
    assert table.loc["a", "posts_per_day"] == pytest.approx(3.0)
    assert table.loc["a", "ci_low"] < 3.0 < table.loc["a", "ci_high"]
    assert table.loc["b", "ci_low"] == table.loc["b", "ci_high"] == 1.0
    again = daily_rate_ci(posts, group_col="channel_slug", start=start, end=end)
    pd.testing.assert_frame_equal(again.set_index("channel_slug"), table)


def test_daily_rate_ci_zero_post_group_and_window_filter():
    posts = _posts([2, 2, 2], [0, 0, 0])
    posts = pd.concat([posts, pd.DataFrame({"channel_slug": ["a"], "timestamp": [pd.Timestamp("2026-01-01", tz="UTC")]})])
    table = daily_rate_ci(
        posts, group_col="channel_slug", start="2025-01-01", end="2025-01-04"
    ).set_index("channel_slug")
    assert table.loc["a", "n_posts"] == 6  # out-of-window post excluded


def test_rate_ratio_ci():
    posts = _posts([6, 4, 8, 6, 2, 10, 6, 6], [2, 1, 3, 2, 1, 3, 2, 2])
    result = rate_ratio_ci(
        posts, "a", "b", group_col="channel_slug", start="2025-01-01", end="2025-01-09"
    )
    assert result["ratio"] == pytest.approx(48 / 16)
    assert result["ci_low"] < result["ratio"] < result["ci_high"]
    with pytest.raises(KeyError):
        rate_ratio_ci(posts, "a", "zzz", start="2025-01-01", end="2025-01-09")


def _cat_frame():
    rng = np.random.default_rng(0)
    rows = []
    for group, probs in {"a": [0.5, 0.3, 0.15, 0.03, 0.02], "b": [0.3, 0.3, 0.2, 0.15, 0.05], "c": [0.4, 0.4, 0.1, 0.05, 0.05]}.items():
        cats = rng.choice(list("ABCDE"), size=60, p=probs)
        rows += [{"grp": group, "cat": cat} for cat in cats]
    return pd.DataFrame(rows)


def test_collapse_rare_categories_keeps_expected_at_least_five():
    df = _cat_frame()
    collapsed = collapse_rare_categories(df, "cat", min_expected=5, group_col="grp")
    table = pd.crosstab(collapsed["grp"], collapsed["cat"])
    expected = scipy_stats.contingency.expected_freq(table.to_numpy())
    assert expected.min() >= 5
    assert "Other" in set(collapsed["cat"])
    assert len(df) == len(collapsed)
    assert set(df["cat"]) != set(collapsed["cat"])  # some collapsed
    assert not df.equals(collapsed)
    # original untouched
    assert "Other" not in set(df["cat"])


def test_collapse_without_group_uses_total_counts():
    df = pd.DataFrame({"cat": ["x"] * 10 + ["y"] * 3 + ["z"] * 2})
    collapsed = collapse_rare_categories(df, "cat", min_expected=5)
    assert collapsed["cat"].value_counts().to_dict() == {"x": 10, "Other": 5}


def test_chi_square_by_group_matches_scipy_and_v():
    table = pd.DataFrame({"a": [30, 10], "b": [10, 30]}, index=["g1", "g2"])  # g x cat
    rows = [(group, cat) for group in table.index for cat in table.columns for _ in range(table.loc[group, cat])]
    df = pd.DataFrame(rows, columns=["grp", "cat"])
    result = chi_square_by_group(df, "grp", "cat")
    chi2, p, dof, _ = scipy_stats.chi2_contingency(table.to_numpy(), correction=False)
    assert result["chi2"] == pytest.approx(chi2)
    assert result["p_value"] == pytest.approx(p)
    assert result["dof"] == dof == 1
    assert result["cramers_v"] == pytest.approx(np.sqrt(chi2 / 80))
    assert result["cramers_v_bias_corrected"] < result["cramers_v"]
    assert result["n_categories"] == 2
    assert result["min_expected_count"] >= 5


def test_chi_square_by_group_collapses_and_reports():
    df = _cat_frame()
    result = chi_square_by_group(df, "grp", "cat")
    assert result["min_expected_count"] >= 5
    assert result["n_categories"] < 5
    assert result["collapsed_categories"]


def test_chi_square_degenerate_single_category():
    df = pd.DataFrame({"grp": ["a", "b"] * 10, "cat": ["x"] * 20})
    result = chi_square_by_group(df, "grp", "cat")
    assert np.isnan(result["chi2"]) and result["n_categories"] == 1
