import numpy as np
import pandas as pd

from solar_recovery.calibration_v3 import ContextCalibrator, full_mask, physical_context
from solar_recovery.replay import Observation, observations_from_hourly
from solar_recovery.replay_v3 import replay_features


def states():
    ends = pd.date_range("2020-06-01T00:00Z", periods=70, freq="h")
    frame = pd.DataFrame({"pv": 1., "irradiance": 300.}, index=ends)
    state = replay_features(observations_from_hourly(frame, 1), ends+pd.Timedelta(minutes=1))
    state["target_solar_sine"] = .5
    state["base_median_normalized"] = .2
    state["base_width90_normalized"] = .4
    return state


def test_physical_control_excludes_recovery_and_mask_covers_all_fifty_slots():
    state = states().iloc[-1].copy()
    changed = state.copy()
    changed["pv_recovery"], changed["irradiance_recovery"] = 0., 2.
    np.testing.assert_array_equal(physical_context(state), physical_context(changed))
    assert len(full_mask(state)) == 50
    changed["pv_lag17"] = np.nan
    assert full_mask(state) != full_mask(changed)


def test_availability_control_drops_only_recovery_coordinates():
    from solar_recovery.calibration_v2 import IssuedForecast
    from solar_recovery.calibration import state_key
    features = states().iloc[-1].copy()
    features["pv_recovery"], features["irradiance_recovery"] = 0., 0.
    origin = features.name
    controls = [ContextCalibrator(kind, min_scores=1, shrinkage=1.)
                for kind in ("physical_availability", "physical_recovery")]
    for i in range(40):
        past = features.copy()
        past["pv_recovery"], past["irradiance_recovery"] = ((0., 0.) if i < 20 else (-1., -1.))
        record = IssuedForecast(str(i), origin-pd.Timedelta(hours=40-i), origin-pd.Timedelta(hours=39-i), 1,
            np.arange(7.), np.arange(7.), state_key(past), full_mask(past), physical_context(past))
        for cal in controls:
            cal.scores[1].append((record, np.full(3, 0. if i < 20 else 10.)))
    _, availability_info = controls[0].correction(origin, 1, features)
    _, recovery_info = controls[1].correction(origin, 1, features)
    assert availability_info["matching_size"] == 40
    assert recovery_info["matching_size"] == 20


def test_matched_context_recovery_is_identical_when_all_states_match():
    state = states()
    calibrators = [ContextCalibrator(kind, min_scores=2) for kind in ("physical", "physical_recovery")]
    pending = []
    for i, (origin, features) in enumerate(state.iloc[50:].iterrows()):
        for observation in pending:
            if observation.receipt <= origin:
                for cal in calibrators:
                    cal.receive(observation, origin)
        target = origin.floor("h")+pd.Timedelta(hours=1)
        forecasts = [cal.issue(str(i), origin, 1, np.arange(7.)/5., features, True, target) for cal in calibrators]
        np.testing.assert_allclose(forecasts[0][0], forecasts[1][0], atol=1e-12)
        pending.append(Observation(str(i), "pv", target, target+pd.Timedelta(minutes=1), 1.+.01*i))
    assert calibrators[0].update_count == len(pending)-1
    assert calibrators[1].update_count == len(pending)-1


def test_context_is_saved_at_issue_not_recomputed_at_label_return():
    features = states().iloc[-1].copy()
    origin = features.name
    target = origin.floor("h")+pd.Timedelta(hours=2)
    cal = ContextCalibrator("mask50", min_scores=1)
    original = physical_context(features)
    cal.issue("a", origin, 2, np.arange(7.), features, True, target)
    features["base_median_normalized"] = 99.
    features["pv_lag17"] = np.nan
    cal.receive(Observation("label", "pv", target, target+pd.Timedelta(hours=4), 2.), target+pd.Timedelta(hours=4))
    record = cal.scores[2][0][0]
    np.testing.assert_array_equal(record.context, original)
    assert all(record.mask)


def test_full_calibration_pipeline_has_future_label_and_prefix_invariance():
    from research.run_annual_calibration import causal_forecasts
    from solar_recovery.replay_v3 import Fault, deliver_schedule
    ends = pd.date_range("2020-06-01T00:00Z", periods=96, freq="h")
    frame = pd.DataFrame({"pv": 1.+np.arange(96.)/100, "irradiance": 300.}, index=ends)
    origins = ends+pd.Timedelta(minutes=1)
    events = observations_from_hourly(frame, 1)
    fault = Fault(origins[40], origins[50], origins[47], "gradual", 15)
    events = deliver_schedule(events, [fault])
    features = replay_features(events, origins)
    bases = {h: np.tile(np.arange(7.)/2, (len(origins), 1)) for h in (1, 2)}
    contract = {"latitude": 39., "longitude": -105., "capacity_kw_dc": 3.}
    params = {"min_scores": 2}
    full, _, _ = causal_forecasts(features, bases, events, contract, params)
    cutoff = 70
    prefix, _, _ = causal_forecasts(features.iloc[:cutoff], {h: q[:cutoff] for h, q in bases.items()},
                                    [o for o in events if o.receipt <= origins[cutoff-1]], contract, params)
    modified = [Observation(o.id, o.stream, o.end, o.receipt, o.value+100.) if o.receipt > origins[cutoff-1] else o for o in events]
    changed, _, _ = causal_forecasts(features, bases, modified, contract, params)
    for method in full:
        for h in full[method]:
            np.testing.assert_array_equal(full[method][h][:cutoff], prefix[method][h])
            np.testing.assert_array_equal(full[method][h][:cutoff], changed[method][h][:cutoff])
