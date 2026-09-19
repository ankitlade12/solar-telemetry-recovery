import numpy as np
import pandas as pd
import pytest

from research.benchmark_inference import loaded_call, prepared_calibrator
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import replay_features


class FixtureModel:
    contract = {"latitude": 39.13, "longitude": -77.21, "capacity_kw_dc": 1.}

    def predict(self, features):
        return {h: np.tile(np.arange(1, 8)/10, (len(features), 1)) for h in (1, 2, 3, 4)}


def test_latency_fixture_exercises_all_horizons_and_dense_pool_without_targets():
    ends = pd.date_range("2020-06-01T00:00Z", "2020-06-03T16:00Z", freq="h")
    truth = pd.DataFrame({"pv": .5, "irradiance": 500.}, index=ends)
    features = replay_features(observations_from_hourly(truth, 1), ends+pd.Timedelta(minutes=1)).iloc[[-1]]
    model = FixtureModel()
    base = loaded_call(model, features)
    cal = prepared_calibrator(features, base, model.contract, {"min_scores": 30}, 720)
    assert all(len(cal.scores[h]) == 720 for h in (1, 2, 3, 4))
    assert all(record.target_end <= features.index[0] for pool in cal.scores.values() for record, _ in pool)
    output = loaded_call(model, features, cal)
    assert set(output) == {1, 2, 3, 4}
    assert all(values.shape == (1, 7) and np.isfinite(values).all() and (values >= 0).all() and
               (np.diff(values, axis=1) >= 0).all() for values in output.values())
    assert all(values[0, 3] == .4 for values in output.values())
    assert sum(map(len, cal.pending.values())) == 4
    assert all(len(cal.scores[h]) == 720 for h in (1, 2, 3, 4))
    with pytest.raises(ValueError, match="one forecast origin"):
        loaded_call(model, pd.concat([features, features]))
