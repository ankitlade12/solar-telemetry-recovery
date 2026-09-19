"""Independent integrity checks on completed pilot artifacts."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text())
    config = json.loads((directory/"config.json").read_text())
    for filename, expected in manifest["code_sha256"].items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected, filename
    truth = pd.read_parquet(Path(config["data_directory"])/"hourly.parquet")
    quantiles = [f"q{j:02d}" for j in (5, 10, 25, 50, 75, 90, 95)]
    base_columns = ["base_"+q for q in quantiles]
    expected_scenarios = {"clean", "pv_only", "irradiance_only", "joint", "irradiance_first", "pv_first", "no_backfill"}
    result = {"checks_passed": [], "scenarios": {}, "total_forecasts": 0}
    files = sorted(directory.glob("forecasts_*.parquet"))
    assert {p.stem.removeprefix("forecasts_") for p in files} == expected_scenarios
    for path in files:
        frame = pd.read_parquet(path)
        scenario = path.stem.removeprefix("forecasts_")
        assert not frame.duplicated(["origin", "horizon", "method"]).any()
        assert frame.groupby(["origin", "horizon"]).size().eq(5).all()
        assert set(frame.horizon) == set(config["horizons"])
        assert frame.target_end.eq(frame.origin+pd.to_timedelta(frame.horizon, unit="h")).all()
        q = frame[quantiles].to_numpy()
        assert np.isfinite(q).all() and (q >= 0).all() and (np.diff(q, axis=1) >= 0).all()
        np.testing.assert_array_equal(frame.q50, frame.base_q50)
        np.testing.assert_allclose(frame.actual_kw, truth.pv.reindex(pd.DatetimeIndex(frame.target_end)).to_numpy(), equal_nan=True)
        assert frame.valid_target.eq(frame.actual_kw.notna()).all()
        assert frame.loc[~frame.valid_target, "wis_kw"].isna().all()
        assert (frame.loc[frame.valid_target, "wis_kw"] >= 0).all()
        learned = frame[frame.method != "persistence"]
        assert learned.groupby(["origin", "horizon"])[base_columns].nunique().eq(1).all().all()
        calibrated = frame[frame.method != "quantile_raw"]
        supported = calibrated.pool_size > 0
        assert (calibrated.loc[supported, "freshest_score_age_h"] >= calibrated.loc[supported, "horizon"]).all()
        assert (calibrated.loc[supported, "effective_n"] <= calibrated.loc[supported, "pool_size"]+1e-7).all()
        eligible = frame[frame.valid_target & frame.daylight & frame.within_split]
        result["scenarios"][scenario] = {"forecasts": len(frame), "eligible_daylight_forecasts": len(eligible),
            "development_recovery_events": int(eligible[(eligible.split == "development_evaluation") & (eligible.phase == "recovery")].event_id.nunique())}
        result["total_forecasts"] += len(frame)
    assert result["total_forecasts"] == manifest["total_forecasts"]
    result["checks_passed"] = ["code hashes", "seven complete scenario files", "unique origin/horizon/method forecasts",
        "four configured horizons and five methods at each origin", "correct target timestamps",
        "finite nonnegative ordered quantiles", "unchanged calibrated medians", "truth alignment and missing-target preservation",
        "identical base forecasts across learned-model methods", "calibration score ages and effective sample sizes"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="runs/nist_2015_pilot_v1")
    args = parser.parse_args()
    result = verify(args.run)
    (Path(args.run)/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
