import numpy as np
import pandas as pd

from research.revision_recovery import recovery_features, realistic_faults, transport_stress, RecoveryKernelCalibrator, FAMILIES
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import replay_features
from solar_recovery.replay_v3 import Fault
from research.summarize_revision_experiments import latest_phase


def test_observable_feature_prefix_invariance_and_original_state_preserved():
    ends = pd.date_range('2016-01-01', periods=500, freq='h', tz='UTC')
    truth = pd.DataFrame({'pv': 1., 'irradiance': 300.}, index=ends)
    contract = {'latitude': 39., 'longitude': -105., 'capacity_kw_dc': 2.}
    events = observations_from_hourly(truth, 1)
    faults = realistic_faults(truth, contract, ends[0], ends[-1], True)
    events = transport_stress(events, faults)
    origins = ends+pd.Timedelta(minutes=1)
    full = recovery_features(events, origins, contract)
    original = replay_features(events, origins)
    pd.testing.assert_frame_equal(full[original.columns], original)
    prefix = recovery_features([e for e in events if e.receipt <= origins[299]], origins[:300], contract)
    pd.testing.assert_frame_equal(full.iloc[:300], prefix)
    assert np.isfinite(full[sum(FAMILIES.values(), [])]).all().all()
    assert all(e.receipt >= e.end for e in events)
    assert any(e.id.endswith(':duplicate') for e in events)
    assert 0 < full.pv_current.mean() < 1
    assert 0 < full.irradiance_current.mean() < 1


def test_recovery_kernel_preserves_context_and_scores_duplicate_labels_once():
    ends = pd.date_range('2016-06-01', periods=60, freq='h', tz='UTC')
    contract = {'latitude': 39., 'longitude': -105., 'capacity_kw_dc': 2.}
    events = observations_from_hourly(pd.DataFrame({'pv': 1., 'irradiance': 300.}, index=ends), 1)
    features = recovery_features(events, ends+pd.Timedelta(minutes=1), contract)
    state = features.iloc[30].copy()
    state['target_solar_sine'], state['base_median_normalized'], state['base_width90_normalized'] = .5, .5, .8
    cal = RecoveryKernelCalibrator('all', min_scores=1)
    target = ends[32]
    cal.issue('forecast', state.name, 2, np.arange(7.)/3, state, True, target)
    expected = cal.encode(state)
    state['rs_pending_labels'] = 999
    label = next(e for e in events if e.stream == 'pv' and e.end == target)
    cal.receive(label, label.receipt)
    cal.receive(label, label.receipt)
    assert cal.update_count == 1
    np.testing.assert_array_equal(cal.scores[2][0][0].context, expected)


def test_reconnect_outage_overrides_prior_recovery_scoring_phase():
    t = pd.Timestamp('2017-06-01T00:00Z')
    h = pd.Timedelta(hours=1)
    faults = [Fault(t, t+2*h, t+2*h), Fault(t+4*h, t+5*h, t+5*h)]
    phases = latest_phase(pd.date_range(t, periods=7, freq='h'), faults)
    assert phases.iloc[3].phase == 'recovery_0_6'
    assert phases.iloc[4].phase == 'outage'
    assert phases.iloc[4].event_id == 1
    assert phases.iloc[5].recovery_hour == 0
