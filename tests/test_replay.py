from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from solar_recovery.replay import (Observation, Outage, VisibleHistory, HOUR,
                                  deliver_schedule, observations_from_hourly, replay_features)


def fixture():
    index = pd.date_range("2020-01-01", periods=72, freq="h", tz="UTC")
    frame = pd.DataFrame({"pv": np.arange(72.), "irradiance": np.arange(72.)*10}, index=index)
    return index, observations_from_hourly(frame)


def test_undelivered_data_rejected():
    index, observations = fixture()
    with pytest.raises(ValueError, match="Undelivered"):
        VisibleHistory().receive(observations[20], index[0])


def test_future_values_cannot_change_earlier_features():
    index, observations = fixture()
    changed = [replace(o, value=o.value+100000) if o.end > index[30] else o for o in observations]
    pd.testing.assert_frame_equal(replay_features(observations, index[:31]), replay_features(changed, index[:31]))


def test_future_restoration_plan_is_not_a_feature():
    index, observations = fixture()
    a = deliver_schedule(observations, [Outage(index[10], index[20], index[20])])
    b = deliver_schedule(observations, [Outage(index[10], index[30], index[25])])
    pd.testing.assert_frame_equal(replay_features(a, index[:20]), replay_features(b, index[:20]))


def test_missing_lag_keeps_its_time_slot_and_zero_is_valid():
    index, observations = fixture()
    fault = Outage(index[10], index[16], index[13], backfill=False)
    features = replay_features(deliver_schedule(observations, [fault]), index)
    assert features.loc[index[0], "pv_lag1"] == 0
    assert np.isnan(features.loc[index[12], "pv_lag1"])
    assert features.loc[index[12], "pv_last"] == 9
    assert features.loc[index[13], "irradiance_recovery"] == 0
    assert features.loc[index[13], "pv_recovery"] == -1
    assert features.loc[index[16], "pv_recovery"] == 0
    assert features.loc[index[16], "pv_missing_fraction"] > 0


def test_only_old_backfill_does_not_restore_live_stream():
    index, observations = fixture()
    fault = Outage(index[10], index[16], index[13])
    events = [o for o in deliver_schedule(observations, [fault]) if not (o.stream == "pv" and o.end >= index[16])]
    features = replay_features(events, index[:18])
    assert features.loc[index[16], "pv_transport_age"] == 0
    assert features.loc[index[16], "pv_age"] == 1
    assert features.loc[index[16], "pv_recovery"] == -1


def test_receipt_boundary_and_normal_lag():
    index, observations = fixture()
    delayed = [replace(o, receipt=o.receipt+pd.Timedelta(minutes=5)) for o in observations]
    features = replay_features(delayed, index[:4], baseline_lag_minutes=5)
    assert np.isnan(features.loc[index[1], "pv_lag1"])
    assert features.loc[index[1], "pv_last"] == 0
    assert features.loc[index[1], "pv_age"] == 0


def test_deterministic_schedule_and_conflicting_revisions():
    index, observations = fixture()
    fault = Outage(index[10], index[16], index[13])
    assert deliver_schedule(observations, [fault]) == deliver_schedule(list(reversed(observations)), [fault])
    view = VisibleHistory()
    view.receive(observations[0], index[0])
    view.receive(observations[0], index[0])
    with pytest.raises(ValueError, match="Conflicting"):
        view.receive(replace(observations[0], value=999), index[0])


def test_naive_timestamps_rejected():
    with pytest.raises(ValueError, match="timezone"):
        Observation("bad", "pv", "2020-01-01", "2020-01-01", 1.)
