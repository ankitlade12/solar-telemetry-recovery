import json

import numpy as np
import pandas as pd
import pytest

from research.final_evaluation import assert_freeze, combine_years, final_scores
from solar_recovery.baselines_v4 import carry_forward_inputs, DressedPreviousDay
from solar_recovery.pilot import digest
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import Fault, replay_features
from solar_recovery.replay_v4 import stale_schedule


def example():
    ends = pd.date_range("2020-06-01", periods=80, freq="h", tz="UTC")
    truth = pd.DataFrame({"pv": np.arange(80.), "irradiance": np.arange(80.)*10}, index=ends)
    events = observations_from_hourly(truth, 1)
    features = replay_features(events, ends+pd.Timedelta(minutes=1))
    return truth, events, features


def test_previous_day_uses_target_hour_and_received_fallback():
    _, _, features = example()
    sample = features.iloc[-1:].copy()
    model = DressedPreviousDay()
    for h in (1, 2, 3, 4):
        assert model.point(sample, h).item() == 79+h-24
    sample.loc[:, "pv_lag24"] = np.nan
    assert model.point(sample, 1).item() == 79


def test_carry_forward_only_uses_older_visible_slots_and_is_prefix_invariant():
    _, _, features = example()
    sample = features.iloc[-5:].copy()
    sample.loc[:, ["pv_lag1", "pv_lag2", "pv_lag48"]] = np.nan
    filled = carry_forward_inputs(sample)
    np.testing.assert_array_equal(filled.pv_lag1, sample.pv_lag3)
    assert filled.pv_lag48.eq(0).all()
    pd.testing.assert_frame_equal(filled.iloc[:2], carry_forward_inputs(sample.iloc[:2]))
    assert filled.filter(regex="age$|fraction$|current$|recovery$").eq(0).all().all()


def test_stale_transport_changes_transport_age_without_refreshing_measurement():
    truth, events, _ = example()
    origin = truth.index[60]+pd.Timedelta(minutes=1)
    fault = Fault(origin, origin+pd.Timedelta(hours=5), origin+pd.Timedelta(hours=5), "none")
    delivered = stale_schedule(events, [fault])
    features = replay_features(delivered, pd.date_range(origin-pd.Timedelta(hours=1), periods=7, freq="h"))
    assert features.iloc[2].pv_transport_age == 0
    assert features.iloc[2].pv_age == 2
    assert features.iloc[2].pv_last == 59
    assert np.isnan(features.iloc[2].pv_lag1)
    assert features.iloc[-1].pv_age == 0
    repeated = [o for o in delivered if o.id.startswith("stale:")]
    assert len(repeated) == 10
    assert all(o.end == truth.index[59] for o in repeated)


def test_year_overlap_keeps_missing_and_rejects_conflicting_values():
    t = pd.DatetimeIndex(["2017-01-01T00:00Z"])
    a = pd.DataFrame({"pv": [np.nan], "irradiance": [np.nan]}, index=t)
    b = a.copy()
    assert combine_years([a, b]).isna().all().all()
    a.pv = 1.; b.pv = 2.
    with pytest.raises(ValueError, match="Conflicting"):
        combine_years([a, b])


def test_protocol_refuses_changed_config_and_frozen_file(tmp_path):
    config, code, lock = (tmp_path/x for x in ("config.json", "code.py", "lock.json"))
    config.write_text('{}'); code.write_text('pass\n')
    lock.write_text(json.dumps({"config_sha256": digest(config), "files_sha256": {str(code): digest(code)}}))
    assert_freeze(config, lock)
    code.write_text('changed\n')
    with pytest.raises(ValueError, match="Frozen input/code changed"):
        assert_freeze(config, lock)
    config.write_text('{"changed": true}')
    with pytest.raises(ValueError, match="Configuration differs"):
        assert_freeze(config, lock)


def test_final_score_flags_ambiguity_without_deleting_valid_truth():
    truth, _, features = example()
    features = features.iloc[-3:-1]
    end = features.index[0].floor("h")+pd.Timedelta(hours=1)
    truth.loc[end, "pv"] = 0.
    contract = {"capacity_kw_dc": 100., "latitude": 39., "longitude": -105.}
    config = {"evaluation_start": "2020-06-02T00:00Z", "evaluation_end": "2020-07-01T00:00Z"}
    scored = final_scores({1: np.tile(np.arange(7.), (2, 1))}, features, truth, contract, [], config, "raw")
    assert scored.zero_with_bright_poa.tolist() == [True, False]
    assert scored.valid_target.all()
    assert scored.actual_lead_minutes.eq(59).all()
    assert (scored.target_end-scored.target_start).eq(pd.Timedelta(hours=1)).all()


def test_final_runner_end_to_end_on_explicit_synthetic_years(tmp_path, monkeypatch):
    from pathlib import Path
    from research.final_evaluation import run
    from solar_recovery.baselines_v3 import PROFILES, geometry
    config = json.loads(Path("configs/final_evaluation_v4.json").read_text())
    config.update(sites=["synthetic"], input_root=str(tmp_path/"inputs"),
        training_start="2016-06-03T00:00Z", train_end="2016-07-01T00:00Z",
        forecast_start="2017-06-03T00:00Z", warmup_end="2017-06-04T00:00Z",
        evaluation_start="2017-06-04T04:00Z", evaluation_end="2017-06-06T00:00Z",
        quantile_profile="synthetic_test", imputation_profile="synthetic_test", imputation_neighbors=5,
        imputation_rounds=2, horizons=[1, 4])
    config["cases"] = [config["cases"][0], next(c for c in config["cases"] if c["id"] == "stale_transport")]
    monkeypatch.setitem(PROFILES, "synthetic_test", {"max_iter": 15, "max_leaf_nodes": 7,
        "min_samples_leaf": 10, "learning_rate": .1})
    contract = {"capacity_kw_dc": 100., "latitude": 39., "longitude": -105.}
    for year in (2016, 2017):
        root = tmp_path/"inputs"/"synthetic"/str(year)/"primary"
        root.mkdir(parents=True)
        ends = pd.date_range(f"{year}-06-01", periods=24*30+1, freq="h", tz="UTC")
        solar = geometry(ends, contract)
        frame = pd.DataFrame({"pv": 80*solar, "irradiance": 1000*solar}, index=ends)
        frame.to_parquet(root/"hourly.parquet")
        (root/"contract.json").write_text(json.dumps({**contract, "hourly_sha256": digest(root/"hourly.parquet")}))
    path, lock = tmp_path/"config.json", tmp_path/"lock.json"
    path.write_text(json.dumps(config))
    lock.write_text(json.dumps({"config_sha256": digest(path), "files_sha256": {}}))
    output = tmp_path/"run"
    run(path, lock, output)
    manifest = json.loads((output/"manifest.json").read_text())
    assert manifest["status"] == "complete frozen evaluation"
    scored = pd.read_parquet(output/"synthetic"/"forecasts_clean.parquet")
    assert {"previous_day", "carry_forward", "physical_availability", "mi_recency"} <= set(scored.method)
    assert not ((scored.origin >= pd.Timestamp(config["warmup_end"])) &
                (scored.origin < pd.Timestamp(config["evaluation_start"]))).any()
    assert set(scored.actual_lead_minutes) == {59., 239.}
    with pytest.raises(FileExistsError):
        run(path, lock, output)
