"""Frozen 2017 evaluation. Refuse changed inputs/code/config after protocol lock."""
import argparse
import copy
from dataclasses import asdict, replace
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

from research.run_annual_baselines import score, summarize
from research.run_annual_calibration import causal_forecasts
from solar_recovery.baselines_v3 import QuantileForecaster, ImputedForecaster, DressedPersistence
from solar_recovery.baselines_v4 import CarryForwardQuantile, DressedPreviousDay
from solar_recovery.replay_v4 import stale_schedule
from solar_recovery.pilot import digest
from solar_recovery.replay import observations_from_hourly, utc
from solar_recovery.replay_v3 import calendar_faults, deliver_schedule, replay_features


def combine_years(frames):
    """Partial alignment bins at year boundaries remain missing, never imputed."""
    combined = pd.concat([f[["pv", "irradiance"]] for f in frames]).sort_index()
    if combined.groupby(level=0).nunique(dropna=True).gt(1).any().any():
        raise ValueError("Conflicting nonmissing observations across source years")
    return combined.groupby(level=0).first()


def forecast_sources():
    return [*sorted(Path("solar_recovery").glob("*.py")), Path("research/run_annual_baselines.py"),
        Path("research/run_annual_calibration.py"), Path("research/final_evaluation.py")]


def assert_freeze(config_path, freeze_path):
    frozen = json.loads(Path(freeze_path).read_text())
    if frozen["config_sha256"] != digest(config_path):
        raise ValueError("Configuration differs from frozen protocol")
    for path, expected in frozen["files_sha256"].items():
        if digest(path) != expected:
            raise ValueError(f"Frozen input/code changed: {path}")
    for package, expected in frozen.get("environment", {}).items():
        if version(package) != expected:
            raise ValueError(f"Frozen package version changed: {package}")
    return frozen


def load_input(config, site, year, variant):
    root = Path(config["input_root"])/site/str(year)/variant
    contract = json.loads((root/"contract.json").read_text())
    if digest(root/"hourly.parquet") != contract["hourly_sha256"]:
        raise ValueError("Normalized data hash mismatch")
    return pd.read_parquet(root/"hourly.parquet"), contract


def training_features(frame, config, ablation="none"):
    origins = pd.date_range(utc(config["training_start"])+pd.Timedelta(minutes=1),
        utc(config["train_end"])-pd.Timedelta(hours=1)+pd.Timedelta(minutes=1), freq="h")
    events = observations_from_hourly(frame[["pv", "irradiance"]], 1)
    features = [replay_features(events, origins)]
    augmentations = () if ablation == "no_block" else (("joint", "immediate", 12), ("pv_only", "none", 24), ("irradiance_first", "gradual", 24))
    for j, (scenario, mode, duration) in enumerate(augmentations):
        faults = calendar_faults(config["training_start"], config["train_end"], config["model_seed"]+j+1,
            duration_hours=duration, scenario=scenario, mode=mode)
        features.append(replay_features(deliver_schedule(events, faults), origins))
    result = pd.concat(features)
    if ablation == "no_age":
        result.loc[:, [c for c in result if c.endswith("_age")]] = 0.
    return result


def fit_models(frame, contract, config, ablation="none"):
    features = training_features(frame, config, ablation)
    models = {
        "quantile": QuantileForecaster(config["quantile_profile"], config["model_seed"], True),
        "imputed": ImputedForecaster(config["imputation_profile"], config["model_seed"],
            config["imputation_neighbors"], config["imputation_rounds"], True),
        "persistence": DressedPersistence(False, True),
        "geometric_persistence": DressedPersistence(True, True),
    }
    if ablation == "none":
        models["previous_day"] = DressedPreviousDay(False, True)
        models["carry_forward"] = CarryForwardQuantile(config["quantile_profile"], config["model_seed"], True)
    for model in models.values():
        model.fit(features, frame, contract, config["train_end"], horizons=config["horizons"])
    for h, info in models["quantile"].counts.items():
        if info["quantile_prediction_std"][3] <= 1e-8:
            raise ValueError(f"Degenerate training median at horizon {h}; stop before evaluation")
    return models


def read_old_models(config, site):
    with (Path(config["old_models"])/site/"models.pkl").open("rb") as handle:
        saved = pickle.load(handle)
    return {"quantile": saved[f"quantile_{config['quantile_profile']}"],
        "imputed": saved[f"imputed_{config['imputation_profile']}"],
        "persistence": saved["persistence"], "geometric_persistence": saved["geometric_persistence"]}


def case_faults(config, case):
    faults = calendar_faults(config["forecast_start"], config["evaluation_end"], case["seed"],
        case["duration_hours"], case["gap_hours"], case["scenario"], case["mode"])
    return [] if case["id"] == "clean" else [replace(f, backfill_spacing_minutes=case["backfill_spacing_minutes"]) for f in faults]


def final_scores(predictions, features, truth, contract, faults, config, method):
    # Reuse tested score calculations, replacing development labels explicitly.
    boundaries = {"validation_start": config["evaluation_start"], "validation_end": config["evaluation_start"],
                  "evaluation_end": config["evaluation_end"]}
    scored = score(predictions, features, truth, contract, faults, method, boundaries)
    scored["period"] = scored.period.replace({"development_evaluation": "evaluation"})
    # A prespecified ambiguity flag, never an assertion that these zeros are bad.
    poa = truth.irradiance.reindex(pd.DatetimeIndex(scored.target_end)).to_numpy()
    scored["zero_with_bright_poa"] = scored.actual_kw.eq(0).to_numpy() & (poa > 200.)
    scored["target_start"] = scored.target_end-pd.Timedelta(hours=1)
    scored["actual_lead_minutes"] = (scored.target_end-scored.origin).dt.total_seconds()/60.
    return scored


def run(config_path, freeze_path, output):
    config_path, freeze_path, output = Path(config_path), Path(freeze_path), Path(output)
    frozen = assert_freeze(config_path, freeze_path)
    config = json.loads(config_path.read_text())
    if output.exists():
        raise FileExistsError("Final runs are immutable; never overwrite evaluated forecasts")
    output.mkdir(parents=True)
    shutil.copyfile(config_path, output/"config.json")
    shutil.copyfile(freeze_path, output/"protocol_lock.json")
    for path in forecast_sources():
        target = output/"source"/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    manifest = {"status": "running frozen evaluation", "freeze_sha256": digest(freeze_path),
        "config_sha256": digest(config_path), "code_sha256": {str(p): digest(p) for p in forecast_sources()},
        "python": platform.python_version(), "platform": platform.platform(),
        "versions": {p: version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "pyarrow", "threadpoolctl")},
        "training": {}, "cases": {}, "total_forecasts": 0}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    began, summaries, overall, case_audits, cache = time.perf_counter(), [], [], [], {}
    (output/"initial_calibration_state.json").write_text(json.dumps({"score_pools": {}, "pending_forecasts": {},
        "aci_initial_alpha": [.5, .2, .1], "scope": "Each case starts with empty forecast/score state, followed by the declared January warmup."}, indent=2)+"\n")
    for site in config["sites"]:
        root = output/site
        root.mkdir(exist_ok=True)
        primary_frames = [load_input(config, site, y, "primary")[0] for y in (2016, 2017)]
        for case in config["cases"]:
            if site not in case.get("sites", config["sites"]):
                continue
            case_start = time.perf_counter()
            variant = case["data_variant"]
            training, contract = load_input(config, site, 2016, variant)
            evaluation, _ = load_input(config, site, 2017, variant)
            (root/f"contract_{variant}.json").write_text(json.dumps(contract, indent=2)+"\n")
            truth = combine_years([training, evaluation])
            # Reuse identical fitted models when quality limits change no inputs.
            identical = all(a[["pv", "irradiance"]].equals(b[["pv", "irradiance"]])
                            for a, b in zip((training, evaluation), primary_frames))
            model_variant = "primary" if identical else variant
            model_site = next(x for x in config["sites"] if x != site) if case["training_source"] == "other_site" else site
            model_year = "2016" if case["training_source"] == "other_site" else case["training_source"]
            ablation = case.get("model_ablation", "none")
            model_key = (model_site, model_year, model_variant, ablation)
            with threadpool_limits(limits=1):
                if model_key not in cache:
                    if model_year == "2015":
                        models = read_old_models(config, model_site)
                    else:
                        fit_frame, fit_contract = load_input(config, model_site, 2016, model_variant)
                        print(f"Fitting {model_site}/{model_variant}/{ablation} on observed 2016 daylight targets", flush=True)
                        models = fit_models(fit_frame, fit_contract, config, ablation)
                    cache[model_key] = models
                    (output/model_site).mkdir(exist_ok=True)
                    model_file = output/model_site/f"models_{model_year}_{model_variant}_{ablation}.pkl"
                    with model_file.open("wb") as handle:
                        pickle.dump(models, handle)
                    manifest["training"]["/".join(model_key)] = {
                        "model_sha256": digest(model_file), "quantile_counts": models["quantile"].counts,
                        "donor_count": len(models["imputed"].imputer.pairs),
                        "latest_donor_end": models["imputed"].imputer.donor_ends.max().isoformat(),
                        "earliest_donor_end": models["imputed"].imputer.donor_ends.min().isoformat()}
                models = cache[model_key]
                if model_site != site:
                    # Transfer normalized fitted quantile weights. Target static
                    # capacity/location are known; no target-site model fitting.
                    models = dict(models)
                    models["quantile"] = copy.deepcopy(models["quantile"])
                    models["quantile"].contract = contract
                margin = case["receipt_minutes"]
                events = observations_from_hourly(truth, margin)
                faults = case_faults(config, case)
                schedule = deliver_schedule(events, faults)
                if case.get("stale_transport", False):
                    schedule = stale_schedule(events, faults)
                origins = pd.date_range(utc(config["forecast_start"])+pd.Timedelta(minutes=margin),
                    utc(config["evaluation_end"])-pd.Timedelta(hours=1)+pd.Timedelta(minutes=margin), freq="h")
                features = replay_features(schedule, origins, margin)
                # Preserve observer state through the four-hour split gap, but
                # issue no forecast in the purged interval.
                features = features.loc[~((features.index >= utc(config["warmup_end"])) &
                                          (features.index < utc(config["evaluation_start"])))]
                if ablation == "no_age":
                    features.loc[:, [c for c in features if c.endswith("_age")]] = 0.
                features.to_parquet(root/f"features_{case['id']}.parquet")
                bases = models["quantile"].predict(features)
                methods = config["primary_methods"] if case["group"] == "primary" else config["sensitivity_methods"]
                print(f"Evaluating {site}/{case['id']} ({len(methods)} calibration outputs)", flush=True)
                label_schedule = events if case.get("privileged_labels", False) else schedule
                calibrated, diagnostics, counts = causal_forecasts(features, bases, label_schedule, contract, config["calibration"], methods)
                predictions = calibrated
                if case["group"] == "primary":
                    imputed = models["imputed"].predict(features)
                    predictions.update(imputed)
                    mi_calibrated, mi_diag, mi_counts = causal_forecasts(features, imputed["multiple_imputation"],
                        schedule, contract, config["calibration"], ["raw", "recency"])
                    predictions["mi_recency"] = mi_calibrated["recency"]
                    mi_diag["method"] = "mi_recency"
                    diagnostics = pd.concat([diagnostics, mi_diag], ignore_index=True)
                    counts["mi_recency"] = mi_counts["recency"]
                    for name in ("persistence", "geometric_persistence", "previous_day", "carry_forward"):
                        predictions[name] = models[name].predict(features)
                scored = pd.concat([final_scores(values, features, truth, contract, faults, config, method)
                                    for method, values in predictions.items()], ignore_index=True)
            scored["site"], scored["scenario"], scored["case_id"], scored["case_group"] = site, case["scenario"], case["id"], case["group"]
            scored["model_version"] = manifest["freeze_sha256"][:16]
            scored["capacity_kw_dc"] = contract["capacity_kw_dc"]
            path = root/f"forecasts_{case['id']}.parquet"
            scored.to_parquet(path, index=False)
            diagnostics.to_parquet(root/f"diagnostics_{case['id']}.parquet", index=False)
            (root/f"schedule_{case['id']}.json").write_text(json.dumps([{k: v.isoformat() if isinstance(v, pd.Timestamp) else v
                for k, v in asdict(f).items()} for f in faults], indent=2)+"\n")
            group = ["site", "case_id", "case_group", "period", "phase", "method", "horizon"]
            summaries.append(summarize(scored, group))
            overall.append(summarize(scored, [c for c in group if c != "phase"]))
            manifest["total_forecasts"] += len(scored)
            audit = {"site": site, "case_id": case["id"], "case_group": case["group"], "data_variant": variant,
                "model_training_source": case["training_source"], "model_site": model_site, "model_ablation": ablation,
                "privileged_labels": case.get("privileged_labels", False), "inputs_equal_primary": identical,
                "forecasts": len(scored), "invalid_targets": int((~scored.valid_target).sum()),
                "outside_period_targets": int((~scored.within_period).sum()), "elapsed_seconds": time.perf_counter()-case_start}
            case_audits.append(audit)
            manifest["cases"][f"{site}/{case['id']}"] = {**audit, "forecasts_sha256": digest(path),
                "features_sha256": digest(root/f"features_{case['id']}.parquet"), "calibration_updates": counts}
            pd.concat(summaries, ignore_index=True).to_csv(output/"metrics.csv", index=False)
            pd.concat(overall, ignore_index=True).to_csv(output/"overall_metrics.csv", index=False)
            (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(f"Completed {site}/{case['id']}: {len(scored):,} forecasts, {audit['elapsed_seconds']:.1f}s", flush=True)
    pd.DataFrame(case_audits).to_csv(output/"case_audit.csv", index=False)
    manifest.update({"status": "complete frozen evaluation", "elapsed_seconds": time.perf_counter()-began,
        "interpretation": "Predeclared fixed-site evaluation and sensitivities; no distribution-free guarantee or population generalization. Wall time is shared-machine end-to-end time, not a latency benchmark."})
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Complete: {output}; {manifest['total_forecasts']:,} forecasts", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/final_evaluation_v4.json")
    parser.add_argument("--freeze", default="research/FINAL_PROTOCOL_LOCK.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.config, args.freeze, args.output)
