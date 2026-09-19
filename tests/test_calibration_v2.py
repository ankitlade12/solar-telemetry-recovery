from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from solar_recovery.calibration_v2 import SignedCalibrator, signed_adjustment
from solar_recovery.replay import HOUR, Observation, VisibleHistory


def fixture():
    origin = pd.Timestamp("2020-01-01T10:00Z")
    return origin, VisibleHistory().features(origin), np.array([0., 1., 2., 5., 8., 9., 10.])


def test_signed_corrections_shrink_and_projection_only_enlarges_adjusted_sets():
    _, _, base = fixture()
    result, repaired = signed_adjustment(base, [-2., -2., -2.])
    np.testing.assert_array_equal(result, [2., 3., 4., 5., 6., 7., 8.])
    assert not repaired
    result, repaired = signed_adjustment(base, [-100., 2., -5.])
    assert repaired and np.all(np.diff(result) >= 0)
    assert result[3] == base[3]
    # A wider middle interval must remain contained in the outer interval.
    assert result[0] <= -1+1 and result[-1] >= 11


def test_calibration_accepts_negative_scores_instead_of_clipping_them():
    origin, state, base = fixture()
    cal = SignedCalibrator(min_scores=1)
    cal.issue("a", origin, 1, base, state, True)
    cal.receive(Observation("y", "pv", origin+HOUR, origin+HOUR, 5.), origin+HOUR)
    result, info = cal.issue("b", origin+HOUR, 1, base, state, True)
    assert info["correction90"] == -5
    assert result[-1]-result[0] < base[-1]-base[0]


def test_night_forecasts_do_not_enter_daylight_pool_or_adaptive_updates():
    origin, state, base = fixture()
    cal = SignedCalibrator("aci_bounded", min_scores=1)
    _, info = cal.issue("night", origin, 1, base, state, False)
    cal.receive(Observation("night_y", "pv", origin+HOUR, origin+HOUR, 0.), origin+HOUR)
    assert info["fallback"] == "outside_daylight_scope"
    assert not cal.scores[1] and cal.update_count == 0
    np.testing.assert_array_equal(cal.alpha[1], [.5, .2, .1])


def test_delayed_aci_feedback_uses_issued_interval_once():
    origin, state, base = fixture()
    cal = SignedCalibrator("aci_bounded", min_scores=1, gamma=.1)
    cal.issue("a", origin, 1, base, state, True)
    label = Observation("y", "pv", origin+HOUR, origin+5*HOUR, 20.)
    with pytest.raises(ValueError, match="Unavailable"):
        cal.receive(label, origin+4*HOUR)
    np.testing.assert_array_equal(cal.alpha[1], [.5, .2, .1])
    cal.receive(label, origin+5*HOUR)
    expected = np.array([.45, .12, .01])
    np.testing.assert_allclose(cal.alpha[1], expected)
    cal.receive(label, origin+5*HOUR)
    np.testing.assert_allclose(cal.alpha[1], expected)
    assert cal.update_count == 1


def test_future_labels_cannot_change_previous_forecasts():
    origin, state, base = fixture()
    a, b = SignedCalibrator(min_scores=1), SignedCalibrator(min_scores=1)
    for i in range(6):
        now = origin+i*HOUR
        if i:
            label = Observation(str(i), "pv", now, now, 3.+i)
            a.receive(label, now)
            b.receive(label, now)
        qa, _ = a.issue(str(i), now, 1, base, state, True)
        qb, _ = b.issue(str(i), now, 1, base, state, True)
        np.testing.assert_array_equal(qa, qb)
    future = Observation("future", "pv", origin+6*HOUR, origin+6*HOUR, 1000.)
    b.receive(future, future.receipt)
    # Previously returned arrays and stored original intervals remain unchanged.
    np.testing.assert_array_equal(qa, qb)


def test_backlog_retains_original_forecast_state_and_rejects_conflicts():
    origin, state, base = fixture()
    cal = SignedCalibrator("recovery", min_scores=1)
    cal.issue("a", origin, 1, base, state, True)
    label = Observation("y", "pv", origin+HOUR, origin+10*HOUR, 7.)
    cal.receive(label, label.receipt)
    record, _ = cal.scores[1][0]
    assert record.origin == origin
    assert record.final[3] == 5.
    with pytest.raises(ValueError, match="Conflicting"):
        cal.receive(replace(label, id="revision", value=100.), label.receipt)


def test_time_reversal_and_invalid_base_are_rejected():
    origin, state, base = fixture()
    cal = SignedCalibrator()
    cal.issue("a", origin, 1, base, state, True)
    with pytest.raises(ValueError, match="backward"):
        cal.issue("b", origin-HOUR, 1, base, state, True)
    with pytest.raises(ValueError, match="ordered"):
        signed_adjustment(base[::-1], np.zeros(3))


def test_rejected_future_label_does_not_advance_calibration_clock():
    origin, state, base = fixture()
    cal = SignedCalibrator()
    future = Observation("future", "pv", origin+3*HOUR, origin+4*HOUR, 5.)
    with pytest.raises(ValueError, match="Unavailable"):
        cal.receive(future, origin+2*HOUR)
    cal.issue("valid", origin, 1, base, state, True)
    assert cal.last_now == origin


def test_expansion_ablation_retains_the_same_negative_score_but_clips_adjustment():
    origin, state, base = fixture()
    signed = SignedCalibrator(min_scores=1)
    expansion = SignedCalibrator(min_scores=1, expansion_only=True)
    for cal in [signed, expansion]:
        cal.issue("a", origin, 1, base, state, True)
        cal.receive(Observation("y", "pv", origin+HOUR, origin+HOUR, 5.), origin+HOUR)
    a, _ = signed.issue("b", origin+HOUR, 1, base, state, True)
    b, _ = expansion.issue("b", origin+HOUR, 1, base, state, True)
    np.testing.assert_array_equal(signed.scores[1][0][1], expansion.scores[1][0][1])
    np.testing.assert_array_equal(b, base)
    assert a[-1]-a[0] < b[-1]-b[0]
