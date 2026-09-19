import numpy as np
import pandas as pd
import pytest

from solar_recovery.calibration import OnlineCalibrator, weighted_quantile
from solar_recovery.metrics import wis, expand, interval_score
from solar_recovery.replay import Observation, VisibleHistory, HOUR


def test_delayed_label_freezes_pool_then_updates_once_with_origin_state():
    origin = pd.Timestamp("2020-01-01 10:00Z")
    features = VisibleHistory().features(origin)
    cal = OnlineCalibrator("recovery")
    base = np.array([1, 2, 3, 4, 5, 6, 7.])
    cal.issue("forecast", origin, 1, base, features)
    label = Observation("label", "pv", origin+HOUR, origin+6*HOUR, 10.)
    with pytest.raises(ValueError, match="unavailable"):
        cal.receive(label, origin+5*HOUR)
    assert cal.update_count == 0
    assert cal.correction(origin+5*HOUR, 1, features)[1]["pool_size"] == 0
    cal.receive(label, origin+6*HOUR)
    cal.receive(label, origin+6*HOUR)
    assert cal.update_count == 1
    record, scores = cal.scores[1][0]
    assert record.origin == origin
    np.testing.assert_array_equal(scores, [5., 4., 3.])
    assert cal.correction(origin+6*HOUR, 1, features)[1]["freshest_score_age_h"] == 6


def test_scores_use_base_intervals_not_previous_correction():
    origin = pd.Timestamp("2020-01-01 10:00Z")
    features = VisibleHistory().features(origin)
    cal = OnlineCalibrator()
    base = np.arange(1., 8.)
    cal.issue("a", origin, 1, base, features)
    cal.receive(Observation("a_y", "pv", origin+HOUR, origin+HOUR, 20.), origin+HOUR)
    final, _ = cal.issue("b", origin+HOUR, 1, base, features)
    assert final[-1] > base[-1]
    cal.receive(Observation("b_y", "pv", origin+2*HOUR, origin+2*HOUR, 20.), origin+2*HOUR)
    np.testing.assert_array_equal(cal.scores[1][0][1], cal.scores[1][1][1])


def test_score_formula_and_nested_expansion():
    q = np.array([1, 2, 3, 4, 5, 6, 7.])
    assert wis(4., q) == pytest.approx(1.2/3.5)
    assert interval_score(0., 1., 3., .5) == 6
    final = expand(q, [20., 1., 0.])
    assert np.all(np.diff(final) >= 0) and final[0] >= 0
    assert final[3] == 4
    assert weighted_quantile([1, 5, 10], [.2, .3, .5], .5) == 5


def test_duplicate_forecast_id_is_rejected():
    origin = pd.Timestamp("2020-01-01 10:00Z")
    cal = OnlineCalibrator()
    features = VisibleHistory().features(origin)
    cal.issue("same", origin, 1, np.arange(7.), features)
    with pytest.raises(ValueError, match="unique"):
        cal.issue("same", origin, 1, np.arange(7.), features)
