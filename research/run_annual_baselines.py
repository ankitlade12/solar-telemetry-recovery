"""Two-site annual-training development comparison; does not access 2017 data."""
import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path
import pickle
import platform
import shutil
import time

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from solar_recovery.baselines_v3 import (DressedPersistence, ImputedForecaster, PROFILES,
    QuantileForecaster, geometry, target_ends)
from solar_recovery.metrics import wis
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly, utc
from solar_recovery.replay_v3 import calendar_faults, deliver_schedule, replay_features

CONFIG = {
    "seed": 20260911, "release_margin_minutes": 1, "train_end": "2016-01-01T00:00Z",
    "validation_start": "2016-02-01T00:00Z", "validation_end": "2016-07-01T00:00Z",
    "evaluation_end": "2017-01-01T00:00Z", "horizons": [1, 2, 3, 4],
    "profiles": PROFILES, "imputation_neighbors": 50, "imputation_rounds": 10,
    "sites": ["nist", "colorado"], "outage_hours": 12, "restoration_gap_hours": 3,
    "scenarios": {
        "clean": ["joint", "immediate"], "pv_only": ["pv_only", "immediate"],
        "irradiance_only": ["irradiance_only", "immediate"], "joint_immediate": ["joint", "immediate"],
        "joint_gradual": ["joint", "gradual"], "joint_none": ["joint", "none"],
        "irradiance_first": ["irradiance_first", "gradual"], "pv_first": ["pv_first", "gradual"],
    },
    "training_augmentation": [["joint", "immediate", 12], ["pv_only", "none", 24],
                               ["irradiance_first", "gradual", 24]],
    "selection": "Per site and method family: lowest equal-scenario, equal-horizon daylight normalized WIS in Feb-Jun 2016. SI and MI use their own validation-selected profile. All 2016 results are development.",
}


def phase_rows(origins, faults):
    rows = []
    for origin in origins:
        phase, event_id, recovery_hour = "normal", -1, np.nan
        for i, fault in enumerate(faults):
            first, full = min(fault.pv_return, fault.irradiance_return), max(fault.pv_return, fault.irradiance_return)
            if fault.start <= origin < full+24*HOUR:
                event_id = i
                if origin < first:
                    phase = "outage"
                elif origin < full:
                    phase = "partial_restoration"
                else:
                    recovery_hour = float((origin-full)/HOUR)
                    phase = "recovery_0_6" if recovery_hour < 6 else "recovery_6_24"
                break
        rows.append((phase, event_id, recovery_hour))
    return pd.DataFrame(rows, index=origins, columns=["phase", "event_id", "recovery_hour"])


def score(base, features, truth, contract, faults, method, config):
    phases = phase_rows(features.index, faults)
    rows = []
    for h, q in base.items():
        ends = target_ends(features, h)
        actual = truth.pv.reindex(ends).to_numpy()
        part = pd.DataFrame({"origin": features.index, "target_end": ends, "horizon": h, "method": method,
            "actual_kw": actual, "valid_target": np.isfinite(actual), "daylight": geometry(ends, contract) > 0,
            "nwis": wis(actual, q)/contract["capacity_kw_dc"],
            "nmae": abs(actual-q[:, 3])/contract["capacity_kw_dc"],
            "phase": phases.phase.to_numpy(), "event_id": phases.event_id.to_numpy(),
            "recovery_hour": phases.recovery_hour.to_numpy(),
            **{f"q{j:02d}": q[:, i] for i, j in enumerate((5, 10, 25, 50, 75, 90, 95))}})
        for level, lo, hi in ((50, 2, 4), (80, 1, 5), (90, 0, 6)):
            part[f"coverage{level}"] = np.where(np.isfinite(actual), (actual >= q[:, lo]) & (actual <= q[:, hi]), np.nan)
            part[f"nwidth{level}"] = (q[:, hi]-q[:, lo])/contract["capacity_kw_dc"]
        part["period"] = np.select([features.index < utc(config["validation_start"]),
                                    features.index < utc(config["validation_end"])],
                                   ["warmup", "validation"], "development_evaluation")
        boundaries = {"warmup": config["validation_start"], "validation": config["validation_end"],
                      "development_evaluation": config["evaluation_end"]}
        part["within_period"] = [end <= utc(boundaries[period]) for end, period in zip(ends, part.period)]
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def summarize(scored, group):
    valid = scored.loc[scored.valid_target & scored.daylight & scored.within_period]
    return valid.groupby(group).agg(n=("nwis", "size"), nwis=("nwis", "mean"), nmae=("nmae", "mean"),
        coverage50=("coverage50", "mean"), coverage80=("coverage80", "mean"), coverage90=("coverage90", "mean"),
        nwidth90=("nwidth90", "mean"), events=("event_id", lambda x: len(set(x)-{-1}))).reset_index()


def run(output, sites=None, daylight_training=False, reuse_trained_run=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Run directories are immutable")
    output.mkdir(parents=True)
    config = dict(CONFIG)
    config["sites"] = sites or CONFIG["sites"]
    config["daylight_training"] = daylight_training
    reused_manifest = None
    if reuse_trained_run is not None:
        reuse_trained_run = Path(reuse_trained_run)
        previous_config = json.loads((reuse_trained_run/"config.json").read_text())
        if previous_config != config:
            raise ValueError("Reusing trained models requires exactly matching experimental configuration")
        reused_manifest = json.loads((reuse_trained_run/"manifest.json").read_text())
        if not reused_manifest["status"].startswith("complete"):
            raise ValueError("Training source run has not completed")
    (output/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    source_paths = [*sorted(Path("solar_recovery").glob("*.py")), Path(__file__).relative_to(Path.cwd())]
    sources = {}
    for path in source_paths:
        destination = output/"source"/path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        sources[str(path)] = digest(path)
    manifest = {"status": "running development baseline comparison", "code_sha256": sources,
        "config_sha256": digest(output/"config.json"), "python": platform.python_version(),
        "versions": {p: version(p) for p in ("numpy", "pandas", "scikit-learn", "scipy", "pyarrow", "threadpoolctl")},
        "training": {}, "inputs": {}, "total_forecasts": 0}
    if reused_manifest is not None:
        manifest["reused_training"] = {"run": str(reuse_trained_run),
            "manifest_sha256": digest(reuse_trained_run/"manifest.json"), "model_sha256": {},
            "reason": "Reuse identical fitted trees and donor bank; stochastic prediction now uses origin-keyed draws. Training used deterministic mean imputation and is unchanged."}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    began, summaries, selections = time.perf_counter(), [], []
    for site in config["sites"]:
        root = output/site
        root.mkdir()
        frames, contracts = [], []
        for year in (2015, 2016):
            source = Path(f"data/processed/{site}_ac_{year}")
            contract = json.loads((source/"contract.json").read_text())
            if digest(source/"hourly.parquet") != contract["hourly_sha256"]:
                raise ValueError("Data hash mismatch")
            manifest["inputs"][str(source)] = {"hourly_sha256": contract["hourly_sha256"], "contract_sha256": digest(source/"contract.json")}
            if reused_manifest is not None and manifest["inputs"][str(source)] != reused_manifest["inputs"][str(source)]:
                raise ValueError("Training source input hash mismatch")
            frames.append(pd.read_parquet(source/"hourly.parquet"))
            contracts.append(contract)
            shutil.copyfile(source/"contract.json", root/f"contract_{year}.json")
            shutil.copyfile(source/"audit.json", root/f"audit_{year}.json")
        if any(contracts[0][k] != contracts[1][k] for k in ("capacity_kw_dc", "latitude", "longitude", "specification")):
            raise ValueError("Site contracts changed between years")
        contract = contracts[0]
        truth = pd.concat(frames).sort_index()
        if not truth.index.is_unique:
            raise ValueError("Overlapping source years need an explicit reconciliation")
        events = observations_from_hourly(truth, config["release_margin_minutes"])
        origins = pd.date_range("2015-01-03T00:01Z", "2016-12-31T23:01Z", freq="h")
        clean = replay_features(events, origins)
        training_origins = origins[origins < utc(config["train_end"])]
        training = [clean.loc[training_origins]]
        for j, (scenario, mode, duration) in enumerate(config["training_augmentation"]):
            faults = calendar_faults("2015-01-01T00:00Z", config["train_end"], config["seed"]+j+1,
                duration_hours=duration, scenario=scenario, mode=mode)
            training.append(replay_features(deliver_schedule(events, faults), training_origins))
        train_features = pd.concat(training)
        print(f"{site}: training on {len(train_features):,} clean/augmented rows from 2015", flush=True)
        models = {}
        with threadpool_limits(limits=1):
            if reused_manifest is not None:
                model_source = reuse_trained_run/site/"models.pkl"
                manifest["reused_training"]["model_sha256"][site] = digest(model_source)
                with model_source.open("rb") as handle:
                    models = pickle.load(handle)
                print(f"{site}: reused fitted models from {reuse_trained_run}", flush=True)
            else:
                for profile in config["profiles"]:
                    models[f"quantile_{profile}"] = QuantileForecaster(profile, config["seed"], daylight_training).fit(
                        train_features, truth, contract, config["train_end"])
                    models[f"imputed_{profile}"] = ImputedForecaster(profile, config["seed"], config["imputation_neighbors"],
                        config["imputation_rounds"], daylight_training).fit(train_features, truth, contract, config["train_end"])
                    print(f"{site}: trained {profile}; elapsed {time.perf_counter()-began:.1f}s", flush=True)
                for geometric in (False, True):
                    name = "geometric_persistence" if geometric else "persistence"
                    models[name] = DressedPersistence(geometric, daylight_training).fit(train_features, truth, contract, config["train_end"])
            manifest["training"][site] = {"quantile_counts": models["quantile_compact"].counts,
                "imputation_donors": len(models["imputed_compact"].imputer.pairs),
                "latest_donor_end": models["imputed_compact"].imputer.donor_ends.max().isoformat()}
            with (root/"models.pkl").open("wb") as handle:
                pickle.dump(models, handle)
            schedule_record, site_overall = {}, []
            for scenario_name, (scenario, mode) in config["scenarios"].items():
                faults = [] if scenario_name == "clean" else calendar_faults(config["train_end"], config["evaluation_end"],
                    config["seed"]+100, config["outage_hours"], config["restoration_gap_hours"], scenario, mode)
                schedule_record[scenario_name] = [{k: v.isoformat() if isinstance(v, pd.Timestamp) else v
                                                  for k, v in asdict(f).items()} for f in faults]
                features = clean if not faults else replay_features(deliver_schedule(events, faults), origins)
                features = features.loc[features.index >= utc(config["train_end"])]
                features.to_parquet(root/f"features_{scenario_name}.parquet")
                chunks = []
                for name, model in models.items():
                    predictions = model.predict(features)
                    if name.startswith("imputed_"):
                        predictions = {f"{method}_{model.profile}": values for method, values in predictions.items()}
                    else:
                        predictions = {name: predictions}
                    for method, values in predictions.items():
                        chunks.append(score(values, features, truth, contract, faults, method, config))
                scored = pd.concat(chunks, ignore_index=True)
                scored["site"], scored["scenario"] = site, scenario_name
                scored.to_parquet(root/f"forecasts_{scenario_name}.parquet", index=False)
                manifest["total_forecasts"] += len(scored)
                summaries.append(summarize(scored, ["site", "scenario", "period", "phase", "method", "horizon"]))
                site_overall.append(summarize(scored, ["site", "scenario", "period", "method", "horizon"]))
                print(f"{site}: {scenario_name}, {len(scored):,} forecasts; elapsed {time.perf_counter()-began:.1f}s", flush=True)
        overall = pd.concat(site_overall, ignore_index=True)
        overall.to_csv(root/"overall_metrics.csv", index=False)
        validation = overall.loc[overall.period.eq("validation")].groupby("method").nwis.mean()
        for family in ("quantile", "single_imputation", "multiple_imputation"):
            names = [f"{family}_{p}" for p in config["profiles"]]
            choice = validation[names].idxmin()
            selections.append({"site": site, "family": family, "method": choice,
                               "validation_nwis": float(validation[choice])})
        (root/"event_schedules.json").write_text(json.dumps(schedule_record, indent=2)+"\n")
        (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    pd.concat(summaries, ignore_index=True).to_csv(output/"metrics.csv", index=False)
    pd.DataFrame(selections).to_csv(output/"selected_profiles.csv", index=False)
    manifest.update({"status": "complete development comparison; no 2017 performance accessed",
        "elapsed_seconds": time.perf_counter()-began,
        "limitations": ["Two geographic sites, one evaluation schedule seed, fixed 12-hour interruptions",
            "MI Setup-2 adaptation: observed targets, joint-channel donor extension, HGB and extra causal features",
            "MI training residual variance can underestimate uncertainty; no normal coverage guarantee",
            "Geometric persistence is an explicit engineering approximation, not an irradiance forecast",
            "Colorado fixed UTC offset and one-minute timestamp-bin interpretation remain assumptions",
            "Forecasts issue HH:01 for targets ending HH+h:00: actual endpoint lead h hours minus one minute",
            "2016 is development, including July-December diagnostics; no confirmatory significance"]})
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Complete: {output}; {manifest['total_forecasts']:,} forecasts", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sites", nargs="+", choices=CONFIG["sites"])
    parser.add_argument("--daylight-training", action="store_true")
    parser.add_argument("--reuse-trained-run")
    args = parser.parse_args()
    run(args.output, args.sites, args.daylight_training, args.reuse_trained_run)
