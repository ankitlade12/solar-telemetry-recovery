"""Replay archived raw forecasts with post-review shrinkage diagnostics."""
import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.final_evaluation import case_faults, combine_years, final_scores, load_input
from research.revision_calibration import DiagnosticCalibrator
from solar_recovery.baselines_v3 import geometry
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly
from solar_recovery.replay_v3 import Fault, deliver_schedule

METHODS = ("physical_availability", "physical_recovery")
QUANTILES = [f"q{q:02d}" for q in (5, 10, 25, 50, 75, 90, 95)]


def replay(features, bases, events, contract, parameters):
    calibrators = {m: DiagnosticCalibrator(m, **parameters) for m in METHODS}
    labels = sorted((e for e in events if e.stream == "pv"), key=lambda e: (e.receipt, e.end, e.id))
    pointer, diagnostics = 0, []
    predictions = {m: {h: [] for h in bases} for m in METHODS}
    solar = {h: geometry(features.index.floor("h")+h*HOUR, contract) for h in bases}
    for i, (origin, visible) in enumerate(features.iterrows()):
        while pointer < len(labels) and labels[pointer].receipt <= origin:
            for cal in calibrators.values():
                cal.receive(labels[pointer], origin)
            pointer += 1
        for h, values in bases.items():
            base, state = values[i], visible.copy()
            state["target_solar_sine"] = solar[h][i]
            state["base_median_normalized"] = base[3]/contract["capacity_kw_dc"]
            state["base_width90_normalized"] = (base[6]-base[0])/contract["capacity_kw_dc"]
            for method, cal in calibrators.items():
                result, info = cal.issue(f"{origin.isoformat()}:{h}", origin, h, base, state,
                                         solar[h][i] > 0, origin.floor("h")+h*HOUR)
                predictions[method][h].append(result)
                diagnostics.append({"origin": origin, "horizon": h, "method": method, **info})
    return {m: {h: np.asarray(q) for h, q in values.items()} for m, values in predictions.items()}, pd.DataFrame(diagnostics)


def run(parent, site, case_id, output, shrinkages):
    parent, output = Path(parent), Path(output)
    if output.exists():
        raise FileExistsError("Revision runs must use a fresh output directory")
    if not shrinkages or len(set(shrinkages)) != len(shrinkages) or any(not np.isfinite(s) or s <= 0 for s in shrinkages):
        raise ValueError("Specify unique finite positive shrinkage constants")
    config = json.loads((parent/"config.json").read_text())
    lock = json.loads((parent/"protocol_lock.json").read_text())
    if digest(parent/"config.json") != lock["config_sha256"]:
        raise ValueError("Parent configuration differs from its lock")
    case = next(c for c in config["cases"] if c["id"] == case_id)
    if case.get("privileged_labels") or case.get("stale_transport") or case.get("model_ablation"):
        raise ValueError("This revision runner supports ordinary receipt scenarios only")
    # Verify replay dependencies, not absent historical author documents or unused model fits.
    required = [p for p in lock["files_sha256"] if p.startswith("solar_recovery/")]
    required += ["research/final_evaluation.py", "research/run_annual_baselines.py", "research/run_annual_calibration.py"]
    required += [str(Path(config["input_root"])/site/str(year)/case["data_variant"]/name)
                 for year in (2016, 2017) for name in ("hourly.parquet", "contract.json")]
    for path in required:
        if digest(path) != lock["files_sha256"][path]:
            raise ValueError(f"Frozen replay dependency changed: {path}")
    for package, expected in lock.get("environment", {}).items():
        if version(package) != expected:
            raise ValueError(f"Frozen package version changed: {package}")
    root = parent/site
    paths = [root/f"features_{case_id}.parquet", root/f"forecasts_{case_id}.parquet", root/f"schedule_{case_id}.json"]
    manifest = json.loads((parent/"manifest.json").read_text())
    audit = manifest["cases"][f"{site}/{case_id}"]
    for path, field in zip(paths[:2], ("features_sha256", "forecasts_sha256")):
        if digest(path) != audit[field]:
            raise ValueError(f"Archived input changed: {path}")
    features, archived = pd.read_parquet(paths[0]), pd.read_parquet(paths[1])
    frames = [load_input(config, site, year, case["data_variant"]) for year in (2016, 2017)]
    truth, contract = combine_years([f for f, _ in frames]), frames[0][1]
    faults = [Fault(**f) for f in json.loads(paths[2].read_text())]
    if [asdict(f) for f in faults] != [asdict(f) for f in case_faults(config, case)]:
        raise ValueError("Archived schedule differs from frozen configuration")
    events = deliver_schedule(observations_from_hourly(truth, case["receipt_minutes"]), faults)
    bases = {h: archived.loc[archived.method.eq("raw") & archived.horizon.eq(h)].set_index("origin").reindex(features.index)[QUANTILES].to_numpy()
             for h in config["horizons"]}
    if not all(np.isfinite(q).all() for q in bases.values()):
        raise ValueError("Incomplete raw forecast alignment")
    output.mkdir(parents=True)
    record = {"status": "running", "scope": "Post-review exploratory; previously inspected 2017 data; no equivalence claim",
              "parent": str(parent), "site": site, "case": case_id, "shrinkages": shrinkages,
              "verified_replay_dependencies": {p: lock["files_sha256"][p] for p in required},
              "parent_lock_sha256": digest(parent/"protocol_lock.json"),
              "inputs": {str(p): digest(p) for p in paths}, "code": {str(p): digest(p) for p in
              (Path(__file__), Path("research/revision_calibration.py"))}}
    (output/"manifest.json").write_text(json.dumps(record, indent=2)+"\n")
    summaries = []
    for shrinkage in shrinkages:
        print(f"Replaying {site}/{case_id}, shrinkage={shrinkage}", flush=True)
        parameters = {**config["calibration"], "shrinkage": shrinkage}
        predictions, diagnostics = replay(features, bases, events, contract, parameters)
        if shrinkage == config["calibration"]["shrinkage"]:
            for method in METHODS:
                for h in bases:
                    expected = archived.loc[archived.method.eq(method) & archived.horizon.eq(h)].set_index("origin").reindex(features.index)[QUANTILES].to_numpy()
                    np.testing.assert_array_equal(predictions[method][h], expected)
            record["original_forecasts_reproduced_exactly"] = True
        scored = pd.concat([final_scores(predictions[m], features, truth, contract, faults, config, m) for m in METHODS], ignore_index=True)
        eligible = scored.loc[scored.valid_target & scored.daylight & scored.within_period & scored.period.eq("evaluation")]
        joined = eligible[["origin", "horizon", "method", "phase", "event_id", "nwis"]].merge(diagnostics, on=["origin", "horizon", "method"], validate="one_to_one")
        joined.to_parquet(output/f"diagnostics_{shrinkage:g}.parquet", index=False)
        scored.to_parquet(output/f"forecasts_{shrinkage:g}.parquet", index=False)
        for keys, group in joined.groupby(["method", "phase", "horizon"]):
            row = dict(zip(("method", "phase", "horizon"), keys))
            row.update(shrinkage=shrinkage, pairs=len(group), events=group.event_id.nunique(), mean_nwis=group.nwis.mean(),
                       insufficient_fraction=group.fallback.eq("insufficient_scores").mean(),
                       no_match_fraction=group.fallback.eq("global_pool").mean())
            for column in ("local_effective_n", "mixing_strength", "effective_n"):
                for q in (.1, .5, .9):
                    row[f"{column}_p{int(q*100)}"] = group[column].quantile(q)
            summaries.append(row)
        pd.DataFrame(summaries).to_csv(output/"support_summary.csv", index=False)
        (output/"manifest.json").write_text(json.dumps(record, indent=2)+"\n")
    record["status"] = "complete exploratory shrinkage replay"
    record["outputs"] = {p.name: digest(p) for p in output.iterdir() if p.name != "manifest.json"}
    (output/"manifest.json").write_text(json.dumps(record, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", default="runs/producing_extension_v1")
    parser.add_argument("--site", default="reserve10")
    parser.add_argument("--case", default="joint_gradual")
    parser.add_argument("--shrinkages", nargs="+", type=float, default=[50., 10., 1.])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.parent, args.site, args.case, args.output, args.shrinkages)
