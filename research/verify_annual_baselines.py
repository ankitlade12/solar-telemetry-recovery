"""Independent prediction, metric, source and receipt-slot checks for annual runs."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.baselines_v3 import geometry
from solar_recovery.metrics import wis
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly
from solar_recovery.replay_v3 import Fault, LAGS, deliver_schedule


def verify(root):
    root = Path(root)
    manifest = json.loads((root/"manifest.json").read_text())
    config = json.loads((root/"config.json").read_text())
    assert manifest["status"].startswith("complete")
    assert digest(root/"config.json") == manifest["config_sha256"]
    for path, expected in manifest["code_sha256"].items():
        assert digest(root/"source"/path) == expected
    for path, expected in manifest["inputs"].items():
        assert digest(Path(path)/"hourly.parquet") == expected["hourly_sha256"]
        assert digest(Path(path)/"contract.json") == expected["contract_sha256"]
    if "reused_training" in manifest:
        reuse = manifest["reused_training"]
        assert digest(Path(reuse["run"])/"manifest.json") == reuse["manifest_sha256"]
        for site, expected in reuse["model_sha256"].items():
            assert digest(Path(reuse["run"])/site/"models.pkl") == expected
    counts, checked_slots, hashes = 0, 0, {}
    all_metrics = pd.read_csv(root/"metrics.csv")
    for site in config["sites"]:
        directory = root/site
        contract = json.loads((directory/"contract_2015.json").read_text())
        truth = pd.concat([pd.read_parquet(f"data/processed/{site}_ac_{year}/hourly.parquet") for year in (2015, 2016)]).sort_index()
        events = observations_from_hourly(truth, config["release_margin_minutes"])
        schedules = json.loads((directory/"event_schedules.json").read_text())
        for scenario in config["scenarios"]:
            path = directory/f"forecasts_{scenario}.parquet"
            scored = pd.read_parquet(path)
            if "reused_training" in manifest:
                parent_path = Path(manifest["reused_training"]["run"])/site/path.name
                previous = pd.read_parquet(parent_path)
                fixed = ~scored.method.str.startswith("multiple_imputation_")
                pd.testing.assert_frame_equal(scored.loc[fixed].reset_index(drop=True),
                    previous.loc[~previous.method.str.startswith("multiple_imputation_")].reset_index(drop=True))
            hashes[str(path.relative_to(root))] = digest(path)
            counts += len(scored)
            assert not scored.duplicated(["origin", "horizon", "method"]).any()
            assert scored.origin.dt.minute.eq(1).all()
            assert (scored.target_end == scored.origin.dt.floor("h")+pd.to_timedelta(scored.horizon, unit="h")).all()
            assert scored.origin.max() < pd.Timestamp(config["evaluation_end"])
            q = scored[[f"q{j:02d}" for j in (5, 10, 25, 50, 75, 90, 95)]].to_numpy()
            assert np.isfinite(q).all() and (q >= 0).all() and (np.diff(q, axis=1) >= 0).all()
            actual = truth.pv.reindex(pd.DatetimeIndex(scored.target_end)).to_numpy()
            np.testing.assert_allclose(actual, scored.actual_kw, equal_nan=True)
            np.testing.assert_array_equal(scored.valid_target, np.isfinite(actual))
            np.testing.assert_array_equal(scored.daylight, geometry(pd.DatetimeIndex(scored.target_end), contract) > 0)
            np.testing.assert_allclose(scored.nwis, wis(actual, q)/contract["capacity_kw_dc"], equal_nan=True)
            for level, lo, hi in ((50, 2, 4), (80, 1, 5), (90, 0, 6)):
                np.testing.assert_allclose(scored[f"coverage{level}"], np.where(np.isfinite(actual), (actual >= q[:, lo]) & (actual <= q[:, hi]), np.nan), equal_nan=True)
            eligible = scored.loc[scored.valid_target & scored.daylight & scored.within_period]
            key = ["period", "phase", "method", "horizon"]
            recalculated = eligible.groupby(key).nwis.mean().sort_index()
            saved = all_metrics.loc[all_metrics.site.eq(site) & all_metrics.scenario.eq(scenario)].set_index(key).nwis.sort_index()
            pd.testing.assert_series_equal(recalculated, saved, check_exact=False, atol=1e-12, rtol=1e-12)
            assert scored.groupby(["origin", "horizon"]).method.nunique().eq(scored.method.nunique()).all()
            # Independently recover sampled visible lag slots from receipt ledgers.
            features = pd.read_parquet(directory/f"features_{scenario}.parquet")
            faults = [Fault(**f) for f in schedules[scenario]]
            schedule = deliver_schedule(events, faults)
            ledger = {stream: {o.end: o for o in schedule if o.stream == stream} for stream in ("pv", "irradiance")}
            indices = np.unique(np.linspace(0, len(features)-1, 100, dtype=int))
            for origin, state in features.iloc[indices].iterrows():
                for stream in ledger:
                    for lag in LAGS:
                        observation = ledger[stream].get(origin.floor("h")-(lag-1)*HOUR)
                        expected = observation.value if observation is not None and observation.receipt <= origin else np.nan
                        observed = state[f"{stream}_lag{lag}"]
                        assert observed == expected or (np.isnan(observed) and np.isnan(expected))
                        checked_slots += 1
    assert counts == manifest["total_forecasts"]
    result = {"status": "passed", "forecasts": counts, "independently_checked_receipt_slots": checked_slots,
        "archived_source_files": len(manifest["code_sha256"]), "forecast_sha256": hashes,
        "non_mi_forecasts_identical_to_training_source": "reused_training" in manifest,
        "verifier_sha256": digest(__file__), "limits": "Structural/data integrity only; does not establish forecast quality or statistical generalization."}
    (root/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k != "forecast_sha256"}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    for directory in args.runs:
        verify(directory)
