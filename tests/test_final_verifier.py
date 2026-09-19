import numpy as np
import pandas as pd

from research.verify_final_evaluation import expected_label_updates, expected_phases, independently_score
from solar_recovery.metrics import wis
from solar_recovery.replay import Observation
from solar_recovery.replay_v3 import Fault


def test_scheduled_phase_boundaries_and_isolated_channel():
    start = pd.Timestamp("2017-06-01T00:00Z")
    origins = start+pd.to_timedelta([-1, 0, 2, 3, 11, 12, 17, 18, 35, 36], unit="h")
    asynchronous = Fault(start, start+pd.Timedelta(hours=3), start+pd.Timedelta(hours=12))
    result = expected_phases(origins, [asynchronous])
    assert result.phase.tolist() == ["normal", "outage", "outage", "partial_restoration", "partial_restoration",
        "recovery_0_6", "recovery_0_6", "recovery_6_24", "recovery_6_24", "normal"]
    assert result.event_id.tolist() == [-1, 0, 0, 0, 0, 0, 0, 0, 0, -1]
    np.testing.assert_allclose(result.recovery_hour, [np.nan]*5+[0, 5, 6, 23, np.nan], equal_nan=True)
    isolated = Fault(start, start+pd.Timedelta(hours=12), start)
    result = expected_phases(origins, [isolated])
    assert result.phase.iloc[1:5].eq("partial_restoration").all()
    assert expected_phases(origins, []).phase.eq("normal").all()


def test_independent_pinball_score_matches_interval_formula_with_missing_target():
    q = np.sort(np.random.default_rng(19).uniform(0, 20, (100, 7)), axis=1)
    y = np.random.default_rng(20).uniform(0, 30, 100)
    y[4] = np.nan
    np.testing.assert_allclose(independently_score(y, q), wis(y, q), rtol=1e-12, atol=1e-12, equal_nan=True)


def test_update_count_respects_receipt_delay_and_duplicate_target(monkeypatch):
    import research.verify_final_evaluation as verifier
    monkeypatch.setattr(verifier, "geometry", lambda ends, contract: np.ones(len(ends)))
    origins = pd.date_range("2017-06-01T00:01Z", periods=3, freq="h")
    schedule = [Observation("late", "pv", pd.Timestamp("2017-06-01T01:00Z"), pd.Timestamp("2017-06-01T03:00Z"), 1.),
        Observation("first", "pv", pd.Timestamp("2017-06-01T02:00Z"), pd.Timestamp("2017-06-01T02:01Z"), 2.),
        Observation("repeat", "pv", pd.Timestamp("2017-06-01T02:00Z"), pd.Timestamp("2017-06-01T02:02Z"), 2.)]
    updates, pending = expected_label_updates(pd.DataFrame(index=origins), schedule, {}, [1, 2])
    np.testing.assert_array_equal(updates, [0, 0, 2])
    assert pending == 4
