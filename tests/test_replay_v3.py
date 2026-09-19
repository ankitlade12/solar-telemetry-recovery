import numpy as np
import pandas as pd
import pytest

from solar_recovery.replay import Observation, observations_from_hourly
from solar_recovery.replay_v3 import Fault, VisibleHistory, calendar_faults, deliver_schedule, replay_features
from solar_recovery.calibration_v2 import SignedCalibrator


def test_release_margin_populates_exact_completed_bin_and_24_hour_history():
    ends = pd.date_range("2020-06-01", periods=30, freq="h", tz="UTC")
    frame = pd.DataFrame({"pv": np.arange(30.), "irradiance": np.arange(30.)}, index=ends)
    features = replay_features(observations_from_hourly(frame, 1), ends+pd.Timedelta(minutes=1))
    assert features.iloc[-1].pv_lag1 == 29
    assert features.iloc[-1].pv_lag24 == 6
    assert features.iloc[-1].pv_age == 0
    # Not-yet-released bin is inaccessible at an hour boundary.
    early = replay_features(observations_from_hourly(frame, 1), ends)
    assert early.iloc[-1].pv_lag1 == 28


def test_gradual_backfill_does_not_block_live_and_cannot_restore_on_old_data():
    ends = pd.date_range("2020-06-01", periods=10, freq="h", tz="UTC")
    frame = pd.DataFrame({"pv": np.arange(10.), "irradiance": np.arange(10.)}, index=ends)
    events = observations_from_hourly(frame, 1)
    fault = Fault(ends[2]+pd.Timedelta(minutes=1), ends[6]+pd.Timedelta(minutes=1), ends[6]+pd.Timedelta(minutes=1), "gradual", 90)
    scheduled = deliver_schedule(events, [fault])
    old = [o for o in scheduled if o.stream == "pv" and ends[2] <= o.end < ends[6]]
    assert [o.receipt for o in old] == [fault.pv_return+pd.Timedelta(minutes=90*i) for i in range(1, 5)]
    live = next(o for o in scheduled if o.stream == "pv" and o.end == ends[6])
    assert live.receipt == fault.pv_return
    # Live resumes even though all four old slots remain absent.
    features = replay_features(scheduled, ends+pd.Timedelta(minutes=1))
    assert features.iloc[6].pv_recovery == 0
    assert features.iloc[6].pv_lag1 == 6
    assert np.isnan(features.iloc[6].pv_lag2)
    assert {o.id: (o.end, o.value) for o in scheduled} == {o.id: (o.end, o.value) for o in events}
    state = VisibleHistory()
    state.receive(events[0], ends[0]+pd.Timedelta(minutes=1))
    state.features(ends[0]+pd.Timedelta(minutes=1))
    state.features(ends[4]+pd.Timedelta(minutes=1))
    state.receive(old[0], old[0].receipt)
    assert state.features(old[0].receipt)["pv_recovery"] == -1


def test_immediate_none_and_future_plan_do_not_change_prefix():
    ends = pd.date_range("2020-06-01", periods=40, freq="h", tz="UTC")
    frame = pd.DataFrame({"pv": np.arange(40.), "irradiance": np.arange(40.)}, index=ends)
    events = observations_from_hourly(frame, 1)
    start, restore = ends[10]+pd.Timedelta(minutes=1), ends[14]+pd.Timedelta(minutes=1)
    for mode in ("immediate", "none", "gradual"):
        schedule = deliver_schedule(events, [Fault(start, restore, restore, mode)])
        prefix = ends[:10]+pd.Timedelta(minutes=1)
        pd.testing.assert_frame_equal(replay_features(events, prefix), replay_features(schedule, prefix))
        if mode == "none":
            assert len(schedule) == len(events)-8
        elif mode == "immediate":
            assert all(o.receipt == restore for o in schedule if ends[10] <= o.end < ends[14])


def test_calendar_faults_are_reproducible_and_cover_day_and_night_hours():
    a = calendar_faults("2020-01-01T00:00Z", "2021-01-01T00:00Z", 42)
    b = calendar_faults("2020-01-01T00:00Z", "2021-01-01T00:00Z", 42)
    assert a == b
    assert len(set(f.start.hour for f in a)) > 15
    with pytest.raises(ValueError):
        deliver_schedule([], [a[0], a[0]])


def test_calibrator_uses_explicit_target_end_and_waits_for_its_receipt():
    t = pd.Timestamp("2020-06-01T00:00Z")
    ends = pd.date_range(t, periods=30, freq="h")
    data = pd.DataFrame({"pv": 1., "irradiance": 100.}, index=ends)
    state = replay_features(observations_from_hourly(data, 1), ends+pd.Timedelta(minutes=1)).iloc[-1]
    origin, target = ends[-1]+pd.Timedelta(minutes=1), ends[-1]+pd.Timedelta(hours=1)
    cal = SignedCalibrator(min_scores=1)
    base = np.arange(7.)
    cal.issue("forecast", origin, 1, base, state, True, target_end=target)
    label = Observation("label", "pv", target, target+pd.Timedelta(minutes=1), 2.)
    with pytest.raises(ValueError, match="Unavailable"):
        cal.receive(label, target)
    assert cal.update_count == 0
    cal.receive(label, label.receipt)
    assert cal.update_count == 1
    cal.receive(label, label.receipt)
    assert cal.update_count == 1
    assert not cal.pending
