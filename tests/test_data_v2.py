import numpy as np
import pandas as pd
import pytest

from solar_recovery.data_v2 import normalize, SITES


def minute_frame():
    native = pd.date_range("2016-01-01", periods=60, freq="min")
    return pd.DataFrame({"measured_on": list(native)*2, "utc_measured_on": pd.NaT,
                         "metric_id": [315]*60+[313]*60, "value": [-1.]*30+[3.]*30+[-3.]*60})


def test_ac_transform_follows_hourly_averaging_and_retains_negative_irradiance():
    hourly, excluded, audit = normalize(minute_frame(), SITES[4], 1.)
    assert hourly.index[0] == pd.Timestamp("2016-01-01T08:00Z")
    assert hourly.pv.iloc[0] == pytest.approx(.001)
    assert hourly.pv_signed_mean_kw.iloc[0] == pytest.approx(.001)
    assert hourly.irradiance.iloc[0] == -3.
    assert not len(excluded)
    assert audit["negative_hourly_ac_means_clipped"] == 0


def test_invalid_sensor_sentinel_is_missing_but_negative_ac_is_a_defined_transform():
    raw = minute_frame()
    raw.loc[raw.metric_id.eq(315), "value"] = -1.
    raw.loc[60, "value"] = -7999.
    hourly, excluded, audit = normalize(raw, SITES[4], 1.)
    assert hourly.pv.iloc[0] == 0
    assert hourly.pv_signed_mean_kw.iloc[0] < 0
    assert np.isnan(hourly.irradiance.iloc[0])
    assert hourly.irradiance_sample_count.iloc[0] == 59
    assert len(excluded) == 1 and audit["negative_hourly_ac_means_clipped"] == 1


def test_conflicting_or_mixed_timestamp_contract_is_rejected():
    raw = minute_frame()
    raw.loc[0, "utc_measured_on"] = pd.Timestamp("2016-01-01T07:00")
    with pytest.raises(ValueError, match="Mixed"):
        normalize(raw, SITES[4], 1.)
    raw["utc_measured_on"] = raw.measured_on+pd.Timedelta(hours=6)
    with pytest.raises(ValueError, match="conflicts"):
        normalize(raw, SITES[4], 1.)


def test_one_minute_alignment_changes_bin_membership_before_averaging():
    native = pd.date_range("2016-01-01", periods=121, freq="min")
    raw = pd.DataFrame({"measured_on": list(native)*2, "utc_measured_on": pd.NaT,
        "metric_id": [315]*121+[313]*121, "value": list(np.arange(121.))*2})
    ordinary, _, _ = normalize(raw, SITES[4], 1.)
    right, _, _ = normalize(raw, SITES[4], 1., timestamp_shift_minutes=-1)
    end = pd.Timestamp("2016-01-01T08:00Z")
    assert ordinary.loc[end, "pv"] == pytest.approx(.0295)
    assert right.loc[end, "pv"] == pytest.approx(.0305)
    assert right.loc[end, "pv_sample_count"] == 60


def test_narrow_quality_limits_remove_samples_without_imputing_them():
    raw = minute_frame()
    raw.loc[60, "value"] = 1600.
    baseline, _, _ = normalize(raw, SITES[4], 1.)
    tight, excluded, _ = normalize(raw, SITES[4], 1.,
        bounds={"ac_min_kw": -.01, "ac_max_kw": 1.2, "poa_min_w_m2": -10., "poa_max_w_m2": 1500.})
    assert np.isfinite(baseline.irradiance.iloc[0])
    assert np.isnan(tight.irradiance.iloc[0])
    assert tight.irradiance_sample_count.iloc[0] == 59
    assert len(excluded) == 1
