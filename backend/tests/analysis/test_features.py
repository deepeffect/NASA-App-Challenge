import numpy as np
import pandas as pd
import pytest

from app.analysis.catalog import load_catalog, load_rules
from app.analysis.daily import to_daily
from app.analysis.features import badness, compute_series_features, rolling_slope

from .helpers import alt_baseline, day, long_df, run


def test_rolling_slope_exact_on_line():
    y = pd.Series(3.0 + 0.5 * np.arange(20))
    s = rolling_slope(y, window=7, min_periods=4)
    assert s.iloc[:3].isna().all()
    np.testing.assert_allclose(s.iloc[3:].to_numpy(), 0.5, atol=1e-9)


def test_rolling_slope_with_gaps():
    y = pd.Series(1.0 - 2.0 * np.arange(15))
    y.iloc[[5, 6, 10]] = np.nan
    s = rolling_slope(y, 7, 4)
    np.testing.assert_allclose(s.dropna().to_numpy(), -2.0, atol=1e-9)


def test_daily_aggregation_respects_catalog():
    cat = load_catalog()
    df = pd.concat([
        long_df("A", "spo2", [[97, 95, 99]]),            # mean
        long_df("A", "exercise_minutes", [[30, 45]]),     # sum
    ])
    d = to_daily(df, cat).set_index("metric")
    assert d.loc["spo2", "value"] == pytest.approx(97.0)
    assert (d.loc["spo2", "min"], d.loc["spo2", "max"], d.loc["spo2", "n"]) == (95, 99, 3)
    assert d.loc["exercise_minutes", "value"] == pytest.approx(75)


def _features(metric, values, as_of_idx=None):
    cat, rules = load_catalog(), load_rules()
    daily = to_daily(long_df("A", metric, values), cat)
    as_of = pd.Timestamp(day(as_of_idx if as_of_idx is not None else len(values) - 1))
    return compute_series_features("A", cat.metrics[metric], daily, as_of, rules)


def test_baseline_and_min_std_floor():
    sf = _features("sleep_duration", [7.0] * 20)
    assert sf.baseline is not None
    assert sf.baseline.n_days == 14
    assert sf.baseline.mean == pytest.approx(7.0)
    assert sf.baseline.std == pytest.approx(load_catalog().metrics["sleep_duration"].min_std)
    assert sf.eval_from == pd.Timestamp(day(14))
    assert sf.eval_mask.sum() == 6


def test_baseline_missing_when_too_few_days():
    sf = _features("sleep_duration", [7.0, None, None, 7.1, None, None, None, None, None, None, None, None, 7.2, None, 7.0])
    assert sf.baseline is None
    assert not sf.eval_mask.any()
    assert sf.frame["z7"].isna().all()


def test_z7_step_change():
    values = alt_baseline(10.0, 1.0) + [13.0] * 10
    sf = _features("hrv_rmssd", values)
    std = sf.baseline.std
    assert sf.frame["z7"].iloc[-1] == pytest.approx(3.0 / std, rel=1e-6)
    assert sf.frame["z"].iloc[-1] == pytest.approx(3.0 / std, rel=1e-6)


def test_badness_directions():
    z = np.array([-2.0, 1.0])
    np.testing.assert_array_equal(badness(z, "down"), [2.0, -1.0])
    np.testing.assert_array_equal(badness(z, "up"), [-2.0, 1.0])
    np.testing.assert_array_equal(badness(z, "both"), [2.0, 1.0])


def test_causal_features_as_of_equals_truncation():
    """as_of ile hesap = veriyi o güne kadar kesip hesaplamak (gelecek sızmaz)."""
    values = alt_baseline(7.2, 0.3) + list(np.linspace(7.2, 5.0, 30))
    full = run([long_df("A", "sleep_duration", values)], ["threshold", "baseline_deviation", "trend"], as_of=day(30), astronauts=("A",))
    cut = run([long_df("A", "sleep_duration", values[:31])], ["threshold", "baseline_deviation", "trend"], astronauts=("A",))
    assert [e.model_dump() for e in full.events] == [e.model_dump() for e in cut.events]
    pd.testing.assert_frame_equal(full.astronauts["A"].features["sleep_duration"].frame,
                                  cut.astronauts["A"].features["sleep_duration"].frame)
