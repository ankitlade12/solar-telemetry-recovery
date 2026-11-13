import numpy as np
import pandas as pd

from research.revision_calibration import DiagnosticCalibrator
from research.run_annual_calibration import causal_forecasts
from research.run_revision_shrinkage import replay, METHODS
from solar_recovery.calibration import state_key
from solar_recovery.calibration_v2 import IssuedForecast
from solar_recovery.calibration_v3 import full_mask, physical_context
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import replay_features


def inputs():
    ends = pd.date_range("2020-06-01T00:00Z", periods=80, freq="h")
    frame = pd.DataFrame({"pv": 1.+np.arange(80)/100, "irradiance": 300.}, index=ends)
    events = observations_from_hourly(frame, 1)
    features = replay_features(events, ends+pd.Timedelta(minutes=1))
    bases = {h: np.tile(np.arange(7.)/2, (80, 1)) for h in (1, 2)}
    return features, bases, events, {"latitude": 39., "longitude": -105., "capacity_kw_dc": 3.}


def test_revision_replay_preserves_predictions_and_future_label_boundary():
    features, bases, events, contract = inputs()
    actual, diagnostics = replay(features, bases, events, contract, {"min_scores": 2})
    expected, _, _ = causal_forecasts(features, bases, events, contract, {"min_scores": 2}, ["raw", *METHODS])
    cutoff = 60
    prefix, _ = replay(features.iloc[:cutoff], {h: q[:cutoff] for h, q in bases.items()},
                       [e for e in events if e.receipt <= features.index[cutoff-1]], contract, {"min_scores": 2})
    for method in METHODS:
        for h in bases:
            np.testing.assert_array_equal(actual[method][h], expected[method][h])
            np.testing.assert_array_equal(actual[method][h][:cutoff], prefix[method][h])
    assert diagnostics.mixing_strength.dropna().between(0, 1).all()


def test_local_support_is_pre_mixture_and_weaker_shrinkage_increases_weight():
    features, _, _, _ = inputs()
    state = features.iloc[-1].copy()
    state["target_solar_sine"], state["base_median_normalized"], state["base_width90_normalized"] = .5, .2, .4
    state["pv_recovery"], state["irradiance_recovery"] = 0., 0.
    diagnostics = []
    for shrinkage in (50., 1.):
        cal = DiagnosticCalibrator("physical_recovery", min_scores=1, shrinkage=shrinkage)
        assert cal.correction(state.name, 1, state)[1]["mixing_strength"] == 0
        for i in range(20):
            past = state.copy()
            if i:
                past["pv_recovery"], past["irradiance_recovery"] = -1., -1.
            record = IssuedForecast(str(i), state.name-HOUR, state.name, 1, np.arange(7.), np.arange(7.),
                                    state_key(past), full_mask(past), physical_context(past))
            cal.scores[1].append((record, np.ones(3)*i))
        info = cal.correction(state.name, 1, state)[1]
        assert info["local_effective_n"] == 1
        assert info["mixing_strength"] == 1/(1+shrinkage)
        assert info["effective_n"] > info["local_effective_n"]
        diagnostics.append(info)
        state_no_match = state.copy()
        state_no_match["pv_recovery"] = 12.
        info = cal.correction(state.name, 1, state_no_match)[1]
        assert info["fallback"] == "global_pool"
        assert info["mixing_strength"] == 0
    assert diagnostics[1]["mixing_strength"] > diagnostics[0]["mixing_strength"]


HOUR = pd.Timedelta(hours=1)
