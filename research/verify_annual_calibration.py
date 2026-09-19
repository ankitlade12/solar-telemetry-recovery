"""Check annual calibrated predictions, receipt-gated update counts and sources."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.baselines_v3 import geometry
from solar_recovery.calibration_v2 import signed_adjustment
from solar_recovery.metrics import wis
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly
from solar_recovery.replay_v3 import Fault, deliver_schedule


def verify(root):
    root = Path(root)
    config = json.loads((root/"config.json").read_text())
    manifest = json.loads((root/"manifest.json").read_text())
    parent = Path(config["parent"])
    assert manifest["status"].startswith("complete")
    assert digest(parent/"manifest.json") == manifest["parent_manifest_sha256"]
    assert digest(parent/"selected_profiles.csv") == manifest["selected_profiles_sha256"]
    assert digest(root/"config.json") == manifest["config_sha256"]
    for path, expected in manifest["code_sha256"].items():
        assert digest(root/"source"/path) == expected
    selected = pd.read_csv(parent/"selected_profiles.csv")
    total, ledger_updates, repaired_checked = 0, {}, 0
    qcols = [f"q{j:02d}" for j in (5, 10, 25, 50, 75, 90, 95)]
    for site in config["sites"]:
        contract = json.loads((parent/site/"contract_2015.json").read_text())
        truth = pd.concat([pd.read_parquet(f"data/processed/{site}_ac_{y}/hourly.parquet") for y in (2015, 2016)]).sort_index()
        schedules = json.loads((parent/site/"event_schedules.json").read_text())
        for scenario in config["scenarios"]:
            recorded_inputs = manifest["inputs"][f"{site}/{scenario}"]
            assert digest(parent/site/f"forecasts_{scenario}.parquet") == recorded_inputs["forecast_sha256"]
            assert digest(parent/site/f"features_{scenario}.parquet") == recorded_inputs["features_sha256"]
            assert digest(parent/site/"event_schedules.json") == recorded_inputs["event_schedules_sha256"]
            forecasts = pd.read_parquet(root/site/f"forecasts_{scenario}.parquet")
            diagnostics = pd.read_parquet(root/site/f"diagnostics_{scenario}.parquet")
            total += len(forecasts)
            assert not forecasts.duplicated(["origin", "horizon", "method"]).any()
            q = forecasts[qcols].to_numpy()
            assert np.isfinite(q).all() and (q >= 0).all() and (np.diff(q, axis=1) >= 0).all()
            actual = truth.pv.reindex(pd.DatetimeIndex(forecasts.target_end)).to_numpy()
            np.testing.assert_allclose(actual, forecasts.actual_kw, equal_nan=True)
            np.testing.assert_allclose(wis(actual, q)/contract["capacity_kw_dc"], forecasts.nwis, equal_nan=True)
            assert (forecasts.target_end == forecasts.origin.dt.floor("h")+pd.to_timedelta(forecasts.horizon, unit="h")).all()
            raw = forecasts.loc[forecasts.method.eq("raw")].set_index(["origin", "horizon"]).sort_index()
            base = pd.read_parquet(parent/site/f"forecasts_{scenario}.parquet")
            choice = selected.loc[selected.site.eq(site) & selected.family.eq("quantile"), "method"].item()
            base = base.loc[base.method.eq(choice)].set_index(["origin", "horizon"]).sort_index()
            np.testing.assert_array_equal(raw[qcols], base[qcols])
            records = forecasts.loc[~forecasts.method.eq("raw")].merge(diagnostics, on=["origin", "horizon", "method"], validate="one_to_one")
            baseline = raw.reindex(pd.MultiIndex.from_frame(records[["origin", "horizon"]]))
            np.testing.assert_array_equal(records.q50, baseline.q50)
            corrections = records[["correction50", "correction80", "correction90"]].to_numpy()
            sampled = np.unique(np.linspace(0, len(records)-1, 2000, dtype=int))
            for index in sampled:
                expected, repaired = signed_adjustment(baseline[qcols].iloc[index].to_numpy(), corrections[index])
                np.testing.assert_array_equal(expected, records[qcols].iloc[index])
                assert repaired == records.nesting_repaired.iloc[index]
                repaired_checked += 1
            faults = [Fault(**f) for f in schedules[scenario]]
            events = deliver_schedule(observations_from_hourly(truth, 1), faults)
            receipts = {o.end: o.receipt for o in events if o.stream == "pv"}
            origins = pd.DatetimeIndex(raw.index.get_level_values("origin").unique()).sort_values()
            updates, issued_daylight = 0, 0
            for h in sorted(raw.index.get_level_values("horizon").unique()):
                ends = origins.floor("h")+int(h)*HOUR
                eligible = geometry(ends, contract) > 0
                issued_daylight += int(eligible.sum())
                updates += sum(end in receipts and receipts[end] <= origins[-1] for end in ends[eligible])
            for method, count in manifest["updates"][f"{site}/{scenario}"].items():
                assert count["updates"] == updates
                assert count["pending_forecasts"] == issued_daylight-updates
            ledger_updates[f"{site}/{scenario}"] = updates
    assert total == manifest["total_forecasts"]
    result = {"status": "passed", "forecasts": total, "independently_counted_label_updates_per_method": ledger_updates,
              "checked_interval_repairs": repaired_checked, "verifier_sha256": digest(__file__),
              "limits": "Integrity/update-count checks and tested prefix invariance do not establish coverage guarantees or generalization."}
    (root/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    verify(args.run)
