from dataclasses import replace

import numpy as np
import pandas as pd

from solar_recovery import pilot
from solar_recovery.replay import HOUR, Outage, observations_from_hourly, deliver_schedule, replay_features


def configuration():
    return {"horizons": [1, 4], "calibration_window_hours": 72, "calibration_tau_hours": 24,
            "calibration_shrinkage": 10, "context_bandwidth": 1,
            "recovery_window_hours": 24, "calibration_end": "2020-01-05T00:00:00Z",
            "validation_end": "2020-01-07T00:00:00Z", "evaluation_end": "2020-01-09T00:00:00Z"}


def test_delayed_future_truth_cannot_change_issued_forecasts():
    index = pd.date_range("2020-01-01", periods=60, freq="h", tz="UTC")
    frame = pd.DataFrame({"pv": np.arange(60.), "irradiance": np.arange(60.)*10}, index=index)
    events = deliver_schedule(observations_from_hourly(frame), [Outage(index[15], index[30], index[25])])
    changed = [replace(o, value=100000.) if o.receipt >= index[30] else o for o in events]
    config = configuration()
    before = index[:30]
    base = {h: np.tile(np.arange(1., 8.), (len(before), 1)) for h in config["horizons"]}
    a = pilot.causal_intervals(replay_features(events, before), base, events, config, 100)
    b = pilot.causal_intervals(replay_features(changed, before), base, changed, config, 100)
    pd.testing.assert_frame_equal(a, b)


def test_missing_targets_and_cross_split_targets_are_not_scored_as_eligible():
    config = configuration()
    origins = pd.DatetimeIndex(["2020-01-04T23:00Z", "2020-01-05T01:00Z"])
    frame = pd.DataFrame({"pv": [5., np.nan]}, index=origins+4*HOUR)
    predictions = pd.DataFrame({"origin": origins, "target_end": origins+4*HOUR, "horizon": 4})
    for j, value in zip((5, 10, 25, 50, 75, 90, 95), range(1, 8)):
        predictions[f"q{j:02d}"] = float(value)
    scored = pilot.score_predictions(predictions, frame, {"latitude": 0, "longitude": 0, "capacity_kw_dc": 100}, config, [])
    assert not scored.loc[0, "within_split"]
    assert not scored.loc[1, "valid_target"]
    assert np.isnan(scored.loc[1, "wis_kw"])
    assert np.isnan(scored.loc[1, "coverage90"])


def test_training_ignores_labels_after_training_boundary(monkeypatch):
    captured = []
    class CaptureModel:
        def __init__(self, **kwargs):
            pass
        def fit(self, features, labels):
            captured.append((features.copy(), labels.copy()))
            return self
    monkeypatch.setattr(pilot, "HistGradientBoostingRegressor", CaptureModel)
    index = pd.date_range("2020-01-01", periods=240, freq="h", tz="UTC")
    frame = pd.DataFrame({"pv": np.arange(240.), "irradiance": np.arange(240.)*10}, index=index)
    features = replay_features(observations_from_hourly(frame), index)
    cutoff = index[180]
    config = {**configuration(), "train_end": cutoff.isoformat(), "training_block_augmentation": True,
              "max_iter": 1, "max_leaf_nodes": 2, "min_samples_leaf": 2, "learning_rate": .1, "seed": 1}
    pilot.fit_models(frame, features, features, config, 100)
    first = captured.copy()
    captured.clear()
    changed = frame.copy()
    changed.loc[changed.index > cutoff, "pv"] = 1000000
    pilot.fit_models(changed, features, features, config, 100)
    for (xa, ya), (xb, yb) in zip(first, captured):
        pd.testing.assert_frame_equal(xa, xb)
        np.testing.assert_array_equal(ya, yb)
        assert (xa.index < cutoff).all()


def test_calendar_schedule_and_asynchronous_phase_are_reproducible():
    index = pd.date_range("2020-01-01", periods=240, freq="h", tz="UTC")
    starts = pilot.event_starts(index, 42, 7)
    assert starts == pilot.event_starts(index, 42, 7)
    fault = pilot.make_faults(starts, "irradiance_first")[0]
    assert pilot.phase_at(fault.start, [fault], 24)[0] == "outage"
    assert pilot.phase_at(fault.irradiance_return, [fault], 24)[0] == "partial_restoration"
    assert pilot.phase_at(fault.pv_return, [fault], 24)[0] == "recovery"
