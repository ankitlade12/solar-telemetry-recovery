import numpy as np
import pandas as pd
import pytest

from solar_recovery.data import hourly_from_minutes, solar_elevation


def minute_data():
    index = pd.date_range("2020-01-01 12:00Z", periods=120, freq="min")
    return pd.DataFrame({"utc_measured_on": np.repeat(index, 2), "metric_id": [82610, 82595]*120,
                         "value": [0., 100.]*120})


def test_left_aligned_hourly_target_and_missing_not_zero():
    raw = minute_data()
    raw.loc[0, "value"] = np.nan
    result, audit, _ = hourly_from_minutes(raw)
    assert result.index[0] == pd.Timestamp("2020-01-01 13:00Z")
    assert np.isnan(result.iloc[0].pv)
    assert result.iloc[1].pv == 0
    assert result.iloc[0].irradiance == 100
    assert audit["valid_pv_hours"] == 1


def test_duplicate_conflict_and_negative_exclusion():
    raw = minute_data()
    raw.loc[0, "value"] = -1
    result, _, excluded = hourly_from_minutes(raw)
    assert len(excluded) == 1 and np.isnan(result.iloc[0].pv)
    conflict = pd.concat([raw, raw.iloc[[1]].assign(value=999)], ignore_index=True)
    with pytest.raises(ValueError, match="Conflicting"):
        hourly_from_minutes(conflict)


def test_geometric_daylight_does_not_need_future_weather():
    times = pd.DatetimeIndex(["2020-03-20 12:00Z", "2020-03-20 00:00Z"])
    elevations = solar_elevation(times, 0, 0)
    assert elevations[0] > 85 and elevations[1] < -85
