"""Receipt-gated calibration comparisons on immutable annual base forecasts."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import shutil
import time

import numpy as np
import pandas as pd

from solar_recovery.baselines_v3 import geometry
from solar_recovery.calibration_v2 import SignedCalibrator
from solar_recovery.calibration_v3 import ContextCalibrator
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly
from solar_recovery.replay_v3 import Fault, deliver_schedule
from research.run_annual_baselines import score, summarize

METHODS = ["raw", "rolling", "recency", "physical", "physical_availability", "physical_recovery", "mask50", "aci_bounded"]


def causal_forecasts(features, bases, events, contract, parameters, methods=None):
    methods = METHODS if methods is None else methods
    if "raw" not in methods or len(set(methods)) != len(methods) or set(methods)-set(METHODS):
        raise ValueError("Unique supported methods including raw are required")
    calibrators = {name: (ContextCalibrator(name, **parameters) if name in {"physical", "physical_availability", "physical_recovery", "mask50"}
                         else SignedCalibrator(method=name, **parameters)) for name in methods if name != "raw"}
    labels = sorted((o for o in events if o.stream == "pv"), key=lambda o: (o.receipt, o.end, o.id))
    pointer = 0
    results = {name: {h: [] for h in bases} for name in methods}
    diagnostics = []
    solar = {h: geometry(features.index.floor("h")+h*HOUR, contract) for h in bases}
    for i, (origin, visible) in enumerate(features.iterrows()):
        updates = {name: cal.update_count for name, cal in calibrators.items()}
        while pointer < len(labels) and labels[pointer].receipt <= origin:
            for cal in calibrators.values():
                cal.receive(labels[pointer], origin)
            pointer += 1
        for h in bases:
            base = bases[h][i]
            target = origin.floor("h")+h*HOUR
            state = visible.copy()
            state["target_solar_sine"] = solar[h][i]
            state["base_median_normalized"] = base[3]/contract["capacity_kw_dc"]
            state["base_width90_normalized"] = (base[6]-base[0])/contract["capacity_kw_dc"]
            results["raw"][h].append(base.copy())
            for name, cal in calibrators.items():
                adjusted, info = cal.issue(f"{origin.isoformat()}:{h}", origin, h, base, state, solar[h][i] > 0, target)
                results[name][h].append(adjusted)
                diagnostics.append({"origin": origin, "horizon": h, "method": name,
                    "label_updates_at_origin_all_horizons": cal.update_count-updates[name], **info})
    arrays = {name: {h: np.asarray(values) for h, values in by_horizon.items()} for name, by_horizon in results.items()}
    return arrays, pd.DataFrame(diagnostics), {name: {"updates": cal.update_count, "alpha_clips": cal.alpha_clip_count,
        "pending_forecasts": sum(map(len, cal.pending.values()))} for name, cal in calibrators.items()}


def run(parent, output, sites, scenarios):
    parent, output = Path(parent), Path(output)
    if output.exists():
        raise FileExistsError("Run directories are immutable")
    parent_manifest = json.loads((parent/"manifest.json").read_text())
    if not parent_manifest["status"].startswith("complete"):
        raise ValueError("Base run must be complete")
    config = json.loads((parent/"config.json").read_text())
    parameters = {"daylight_only": True, "window_hours": 720, "tau_hours": 336, "shrinkage": 50.,
                  "bandwidth": 1., "min_scores": 30, "gamma": .001}
    output.mkdir(parents=True)
    setup = {"parent": str(parent), "sites": sites, "scenarios": scenarios, "parameters": parameters,
             "methods": METHODS, "base_family": "validation-selected quantile", "status": "development, not confirmatory"}
    (output/"config.json").write_text(json.dumps(setup, indent=2)+"\n")
    sources = [*sorted(Path("solar_recovery").glob("*.py")), Path("research/run_annual_baselines.py"), Path("research/run_annual_calibration.py")]
    code_hashes = {}
    for path in sources:
        target = output/"source"/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        code_hashes[str(path)] = digest(path)
    manifest = {"status": "running development calibration", "parent_manifest_sha256": digest(parent/"manifest.json"),
        "selected_profiles_sha256": digest(parent/"selected_profiles.csv"), "code_sha256": code_hashes,
        "config_sha256": digest(output/"config.json"), "python": platform.python_version(),
        "versions": {p: version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "pyarrow")},
        "total_forecasts": 0, "updates": {}, "inputs": {}}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    selected = pd.read_csv(parent/"selected_profiles.csv")
    summaries, overall, began = [], [], time.perf_counter()
    for site in sites:
        root = output/site
        root.mkdir()
        contract = json.loads((parent/site/"contract_2015.json").read_text())
        truth = pd.concat([pd.read_parquet(f"data/processed/{site}_ac_{year}/hourly.parquet") for year in (2015, 2016)]).sort_index()
        for year in (2015, 2016):
            path = f"data/processed/{site}_ac_{year}"
            if digest(Path(path)/"hourly.parquet") != parent_manifest["inputs"][path]["hourly_sha256"]:
                raise ValueError("Changed source observations")
        events = observations_from_hourly(truth, config["release_margin_minutes"])
        schedules = json.loads((parent/site/"event_schedules.json").read_text())
        selected_method = selected.loc[selected.site.eq(site) & selected.family.eq("quantile"), "method"].item()
        for scenario in scenarios:
            print(f"Calibrating {site}/{scenario} with {selected_method}", flush=True)
            path = parent/site/f"forecasts_{scenario}.parquet"
            features = pd.read_parquet(parent/site/f"features_{scenario}.parquet")
            # Do not load hidden target columns into the online routine.
            base_frame = pd.read_parquet(path, columns=["origin", "horizon", "method", *[f"q{j:02d}" for j in (5, 10, 25, 50, 75, 90, 95)]])
            base_frame = base_frame.loc[base_frame.method.eq(selected_method)]
            bases = {}
            for h in config["horizons"]:
                part = base_frame.loc[base_frame.horizon.eq(h)].set_index("origin").reindex(features.index)
                q = part[[f"q{j:02d}" for j in (5, 10, 25, 50, 75, 90, 95)]].to_numpy()
                if not np.isfinite(q).all():
                    raise ValueError("Incomplete base forecast alignment")
                bases[h] = q
            faults = [Fault(**f) for f in schedules[scenario]]
            results, diagnostics, counts = causal_forecasts(features, bases, deliver_schedule(events, faults), contract, parameters)
            scored = pd.concat([score(base, features, truth, contract, faults, method, config) for method, base in results.items()], ignore_index=True)
            scored["site"], scored["scenario"], scored["base_method"] = site, scenario, selected_method
            scored.to_parquet(root/f"forecasts_{scenario}.parquet", index=False)
            diagnostics.to_parquet(root/f"diagnostics_{scenario}.parquet", index=False)
            summaries.append(summarize(scored, ["site", "scenario", "period", "phase", "method", "horizon"]))
            overall.append(summarize(scored, ["site", "scenario", "period", "method", "horizon"]))
            manifest["total_forecasts"] += len(scored)
            manifest["updates"][f"{site}/{scenario}"] = counts
            manifest["inputs"][f"{site}/{scenario}"] = {"forecast_sha256": digest(path),
                "features_sha256": digest(parent/site/f"features_{scenario}.parquet"),
                "event_schedules_sha256": digest(parent/site/"event_schedules.json")}
            (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(f"Completed {site}/{scenario}: {len(scored):,} forecasts; elapsed {time.perf_counter()-began:.1f}s", flush=True)
    pd.concat(summaries, ignore_index=True).to_csv(output/"metrics.csv", index=False)
    pd.concat(overall, ignore_index=True).to_csv(output/"overall_metrics.csv", index=False)
    manifest.update({"status": "complete development calibration, no final-year evaluation", "elapsed_seconds": time.perf_counter()-began,
        "limitations": ["Fixed calibration parameters, no calibration-parameter tuning in this run",
            "Physical and physical+recovery share identical context/recency parameters; only the recovery-state blend differs",
            "Mask50 is a shrinkage empirical control, not the distributional-imputation algorithm of Fan et al.",
            "All intervals are empirical; finite weighted ranks, nesting repairs and bounded ACI change classical guarantees",
            "All inspected 2016 performance is development; pending labels may never arrive under permanent loss"]})
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Complete: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sites", nargs="+", default=["nist", "colorado"], choices=["nist", "colorado"])
    parser.add_argument("--scenarios", nargs="+", default=["clean", "joint_gradual"], choices=["clean", "pv_only", "irradiance_only", "joint_immediate", "joint_gradual", "joint_none", "irradiance_first", "pv_first"])
    args = parser.parse_args()
    run(args.parent, args.output, args.sites, args.scenarios)
