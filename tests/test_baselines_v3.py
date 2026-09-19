import numpy as np
import pandas as pd
import pytest

from solar_recovery.baselines_v3 import LagDonorImputer, model_features, target_ends, training_table
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import LAGS, replay_features


def fixture():
    ends = pd.date_range("2020-06-01", periods=100, freq="h", tz="UTC")
    truth = pd.DataFrame({"pv": np.arange(100.), "irradiance": np.arange(100.)*10}, index=ends)
    features = replay_features(observations_from_hourly(truth, 1), ends+pd.Timedelta(minutes=1))
    contract = {"latitude": 39., "longitude": -105., "capacity_kw_dc": 100.}
    return truth, features, contract


def test_imputation_never_uses_future_donors_and_preserves_observations():
    truth, features, contract = fixture()
    cutoff = truth.index[70]
    imputer = LagDonorImputer(truth, contract, cutoff, k=5)
    changed_truth = truth.copy()
    changed_truth.loc[changed_truth.index > cutoff, ["pv", "irradiance"]] = 999999.
    other = LagDonorImputer(changed_truth, contract, cutoff, k=5)
    test = features.iloc[-3:].copy()
    test.loc[:, "pv_lag1"] = np.nan
    test.loc[:, "irradiance_lag2"] = np.nan
    test.loc[:, ["pv_lag3", "irradiance_lag3"]] = np.nan
    for sample in (False, True):
        completed = imputer.transform(test, sample=sample, seed=1)
        pd.testing.assert_frame_equal(completed, other.transform(test, sample=sample, seed=1))
        for c in test:
            finite = np.isfinite(test[c])
            np.testing.assert_array_equal(completed.loc[finite, c], test.loc[finite, c])
        assert np.isfinite(completed.to_numpy()).all()
        assert completed.pv_lag1.max() <= 70
    assert imputer.donor_ends.max() == cutoff


def test_training_eligibility_checks_target_boundary_not_only_origin():
    truth, features, contract = fixture()
    cutoff = truth.index[70]
    eligible, y = training_table(features, truth, contract, 4, cutoff)
    assert target_ends(eligible, 4).max() == cutoff
    assert eligible.index.max() < cutoff-pd.Timedelta(hours=3)
    altered = truth.copy()
    altered.loc[altered.index > cutoff, "pv"] = -99999
    _, other = training_table(features, altered, contract, 4, cutoff)
    np.testing.assert_array_equal(y, other)
    assert np.isfinite(y).all()


def test_stochastic_imputation_is_prefix_and_batch_order_invariant():
    truth, features, contract = fixture()
    imputer = LagDonorImputer(truth, contract, truth.index[70], k=5)
    features = features.iloc[75:].copy()
    features.loc[:, "pv_lag1"] = np.nan
    features.loc[:, "irradiance_lag2"] = np.nan
    features.loc[:, ["pv_lag3", "irradiance_lag3"]] = np.nan
    full = imputer.transform(features, sample=True, seed=33)
    prefix = imputer.transform(features.iloc[:5], sample=True, seed=33)
    pd.testing.assert_frame_equal(prefix, full.iloc[:5])
    reversed_batch = imputer.transform(features.iloc[::-1], sample=True, seed=33)
    pd.testing.assert_frame_equal(reversed_batch.iloc[::-1], full)
    changed_future = features.copy()
    changed_future.iloc[5:, :] = np.nan
    amended = imputer.transform(changed_future, sample=True, seed=33)
    pd.testing.assert_frame_equal(amended.iloc[:5], full.iloc[:5])


def test_target_geometry_and_hourly_slots_are_compatible_with_release_margin():
    truth, features, contract = fixture()
    sample = features.iloc[-1:]
    X = model_features(sample, contract, 4)
    assert X.pv_lag1.iloc[0] == .99
    assert X.irradiance_lag1.iloc[0] == .99
    assert not any(c.endswith("_recovery") for c in X)
    assert target_ends(sample, 4)[0]-sample.index[0] == pd.Timedelta(hours=4, minutes=-1)
    assert 0 <= X.target_solar_sine.iloc[0] <= 1
    with pytest.raises(ValueError):
        LagDonorImputer(truth, contract, truth.index[0], k=5)


def test_daylight_training_excludes_night_and_learns_nonconstant_median(monkeypatch):
    from solar_recovery.baselines_v3 import PROFILES, QuantileForecaster, geometry
    from threadpoolctl import threadpool_limits
    contract = {"latitude": 39., "longitude": -105., "capacity_kw_dc": 100.}
    ends = pd.date_range("2020-03-01", periods=24*28, freq="h", tz="UTC")
    solar = geometry(ends, contract)
    truth = pd.DataFrame({"pv": 100*solar, "irradiance": 1000*solar}, index=ends)
    features = replay_features(observations_from_hourly(truth, 1), ends+pd.Timedelta(minutes=1))
    eligible, y = training_table(features, truth, contract, 1, ends[-1], daylight_only=True)
    assert (geometry(target_ends(eligible, 1), contract) > 0).all()
    assert (y > 0).all()
    monkeypatch.setitem(PROFILES, "test", {"max_iter": 30, "max_leaf_nodes": 7, "min_samples_leaf": 10, "learning_rate": .1})
    with threadpool_limits(limits=1):
        model = QuantileForecaster("test", daylight_only=True).fit(features, truth, contract, ends[-1], horizons=(1,))
        q = model.predict(features)[1]
    daylight = geometry(target_ends(features, 1), contract) > 0
    assert q[daylight, 3].std() > 5.
    assert (q[~daylight] == 0).all()
