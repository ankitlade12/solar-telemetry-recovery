import numpy as np
import pandas as pd
import pytest

from research.analyze_final_evaluation import calendar_bootstrap, paired_days, SCORES


def test_calendar_resampling_keeps_shared_weather_scenarios_together():
    rows = []
    for day, value in zip(pd.date_range("2017-02-01", periods=28, tz="UTC"), np.arange(28.)):
        for case, sign in (("first", 1), ("second", -1)):
            rows.append({"day": day, "case_id": case, "horizon": 1, "n": 1,
                         "left_nwis": 100+sign*value, "right_nwis": 100})
    result = calendar_bootstrap(pd.DataFrame(rows), "2017-02-01T04:00Z", "2017-03-01T00:00Z", 7, 1000, 1)
    assert result["difference"] == 0
    assert abs(result["ci_lower"]) < 1e-12
    assert abs(result["ci_upper"]) < 1e-12
    assert result["valid_replicates"] == 1000
    assert result["calendar_blocks"] == 4


def test_estimand_weights_case_horizons_equally_not_raw_rows():
    rows = []
    for day in pd.date_range("2017-02-01", periods=14, tz="UTC"):
        rows += [{"day": day, "case_id": "small", "horizon": 1, "n": 1, "left_nwis": 10., "right_nwis": 0.},
                 {"day": day, "case_id": "large", "horizon": 1, "n": 100, "left_nwis": 0., "right_nwis": 0.}]
    result = calendar_bootstrap(pd.DataFrame(rows), "2017-02-01T00:00Z", "2017-02-15T00:00Z", 7, 1000, 9)
    assert result["difference"] == 5.
    assert result["ci_lower"] == result["ci_upper"] == 5.
    assert np.isnan(result["relative_difference"])


def test_paired_aggregation_rejects_mismatched_scoring_counts():
    rows = [{"day": pd.Timestamp("2017-02-01T00:00Z"), "case_id": "case", "horizon": 1,
             "phase": "recovery_0_6", "method": method, "n": count, **{"sum_"+s: 1. for s in SCORES}}
            for method, count in (("left", 1), ("right", 2))]
    with pytest.raises(ValueError, match="same daily scoring counts"):
        paired_days(pd.DataFrame(rows), "left", "right")
