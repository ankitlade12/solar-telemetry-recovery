"""Run a bounded development experiment; no confirmatory claims are implied."""
import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from .calibration import OnlineCalibrator
from .data import solar_elevation
from .metrics import ALPHAS, PAIRS, QUANTILES, wis
from .replay import HOUR, Outage, observations_from_hourly, deliver_schedule, replay_features, utc


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def event_starts(index, seed, spacing_days):
    """Calendar-only schedule, independent of PV/weather values and model errors."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(index.min().ceil("D")+pd.Timedelta(days=3), index.max().floor("D")-pd.Timedelta(days=3),
                         freq=f"{spacing_days}D", tz="UTC")
    # UTC 14-18 gives daytime-oriented origins in Maryland, without future weather.
    return [day+int(rng.integers(14, 19))*HOUR for day in days]


def make_faults(starts, scenario, hours=12, gap=3):
    if scenario == "clean":
        return []
    result = []
    for start in starts:
        pv_return = irradiance_return = start+hours*HOUR
        if scenario == "pv_only":
            irradiance_return = start
        elif scenario == "irradiance_only":
            pv_return = start
        elif scenario in {"irradiance_first", "no_backfill"}:
            irradiance_return -= gap*HOUR
        elif scenario == "pv_first":
            pv_return -= gap*HOUR
        elif scenario != "joint":
            raise ValueError(f"Unknown scenario: {scenario}")
        result.append(Outage(start, pv_return, irradiance_return, scenario != "no_backfill"))
    return result


def phase_at(origin, faults, recovery_hours):
    # Evaluator annotation only: never passed into model/calibration features.
    for event_id, fault in enumerate(faults):
        partial = min(fault.pv_return, fault.irradiance_return)
        restored = max(fault.pv_return, fault.irradiance_return)
        if fault.start <= origin < restored:
            phase = "partial_restoration" if origin >= partial and partial > fault.start else "outage"
            return phase, event_id, float((origin-restored)/HOUR)
        if restored <= origin < restored+recovery_hours*HOUR:
            return "recovery", event_id, float((origin-restored)/HOUR)
    return "background", -1, np.nan


def model_features(features, capacity):
    result = features.drop(columns=[c for c in features if c.endswith("_recovery")]).copy()
    for column in result:
        if column.startswith("pv_lag") or column == "pv_last":
            result[column] /= capacity
        if column.startswith("irradiance_lag") or column == "irradiance_last":
            result[column] /= 1000
    return result


def fit_models(frame, clean, augmented, config, capacity):
    cutoff = utc(config["train_end"])
    start = frame.index.min()+48*HOUR
    mask = (clean.index >= start) & (clean.index < cutoff)
    feature_sets = [model_features(clean.loc[mask], capacity)]
    if config["training_block_augmentation"]:
        feature_sets.append(model_features(augmented.loc[mask], capacity))
    X = pd.concat(feature_sets)
    models, counts = {}, {}
    for horizon in config["horizons"]:
        target_end = X.index+horizon*HOUR
        y = frame.pv.reindex(target_end).to_numpy()/capacity
        eligible = np.isfinite(y) & (target_end <= cutoff)
        if eligible.sum() < 100:
            raise ValueError("Insufficient observed training targets")
        counts[horizon] = {"fit_rows_with_augmentation": int(eligible.sum()),
                           "distinct_target_intervals": len(set(target_end[eligible]))}
        models[horizon] = []
        for quantile in QUANTILES:
            model = HistGradientBoostingRegressor(loss="quantile", quantile=float(quantile),
                         max_iter=config["max_iter"], max_leaf_nodes=config["max_leaf_nodes"],
                         min_samples_leaf=config["min_samples_leaf"], learning_rate=config["learning_rate"],
                         early_stopping=False, random_state=config["seed"])
            model.fit(X.loc[eligible], y[eligible])
            models[horizon].append(model)
    return models, counts


def base_predictions(models, features, capacity):
    X = model_features(features, capacity)
    return {h: np.maximum(0, np.sort(np.column_stack([m.predict(X) for m in models[h]]), axis=1)*capacity)
            for h in models}


def causal_intervals(features, base, events, config, capacity):
    """Calibration consumes only due delivered labels, never the truth dataframe."""
    kwargs = {"window_hours": config["calibration_window_hours"], "tau_hours": config["calibration_tau_hours"],
              "shrinkage": config["calibration_shrinkage"], "bandwidth": config["context_bandwidth"]}
    calibrators = {name: OnlineCalibrator(name, **kwargs) for name in ("rolling", "context", "recovery")}
    calibrators["persistence"] = OnlineCalibrator("rolling", **kwargs)
    labels = sorted([o for o in events if o.stream == "pv"], key=lambda o: (o.receipt, o.end, o.id))
    pointer, rows = 0, []
    for i, (origin, state) in enumerate(features.iterrows()):
        while pointer < len(labels) and labels[pointer].receipt <= origin:
            for cal in calibrators.values():
                cal.receive(labels[pointer], origin)
            pointer += 1
        for horizon in config["horizons"]:
            raw = base[horizon][i]
            # Persistence has the same delivery information; zero only if no history.
            last = state["pv_last"] if np.isfinite(state["pv_last"]) else 0.
            outputs = {"quantile_raw": (raw, {"pool_size": 0, "matching_size": 0, "effective_n": 0.,
                                               "freshest_score_age_h": np.nan, "fallback": "not_calibrated"})}
            for name, cal in calibrators.items():
                model_base = np.full(7, last) if name == "persistence" else raw
                # Scores pooled on this one site; no cross-capacity mixing in pilot.
                outputs[name] = cal.issue(f"{origin.isoformat()}:{horizon}", origin, horizon, model_base, state)
            for name, (quantiles, info) in outputs.items():
                record = {"origin": origin, "target_end": origin+horizon*HOUR, "horizon": horizon,
                          "method": name, **info}
                record.update({f"q{j:02d}": value for j, value in zip((5, 10, 25, 50, 75, 90, 95), quantiles)})
                record.update({f"base_q{j:02d}": value for j, value in zip((5, 10, 25, 50, 75, 90, 95),
                                                                           np.full(7, last) if name == "persistence" else raw)})
                record.update({k: float(v) for k, v in state.items() if k.endswith(("_age", "_recovery", "_missing_fraction"))})
                rows.append(record)
    return pd.DataFrame(rows)


def score_predictions(predictions, truth, contract, config, faults):
    scored = predictions.copy()
    # Hidden truth is first joined here, after all predictions are immutable.
    scored["actual_kw"] = truth.pv.reindex(pd.DatetimeIndex(scored.target_end)).to_numpy()
    scored["valid_target"] = np.isfinite(scored.actual_kw)
    scored["daylight"] = solar_elevation(pd.DatetimeIndex(scored.target_end)-HOUR/2,
                                          contract["latitude"], contract["longitude"]) > 0
    phases = {t: phase_at(t, faults, config["recovery_window_hours"]) for t in scored.origin.unique()}
    scored["phase"] = [phases[t][0] for t in scored.origin]
    scored["event_id"] = [phases[t][1] for t in scored.origin]
    scored["recovery_hour"] = [phases[t][2] for t in scored.origin]
    scored["split"] = "calibration"
    scored.loc[scored.origin >= utc(config["calibration_end"]), "split"] = "validation"
    scored.loc[scored.origin >= utc(config["validation_end"]), "split"] = "development_evaluation"
    split_ends = {"calibration": utc(config["calibration_end"]), "validation": utc(config["validation_end"]),
                  "development_evaluation": utc(config["evaluation_end"])}
    scored["within_split"] = [end <= split_ends[split] for end, split in zip(scored.target_end, scored.split)]
    q = scored[[f"q{j:02d}" for j in (5, 10, 25, 50, 75, 90, 95)]].to_numpy()
    scored["wis_kw"] = wis(scored.actual_kw.to_numpy(), q)
    scored["nwis"] = scored.wis_kw/contract["capacity_kw_dc"]
    scored["mae_kw"] = abs(scored.actual_kw-scored.q50)
    for alpha, (lo, hi) in zip(ALPHAS, PAIRS):
        name = int(round(100*(1-alpha)))
        scored[f"coverage{name}"] = np.where(scored.valid_target,
                    (scored.actual_kw.to_numpy() >= q[:, lo]) & (scored.actual_kw.to_numpy() <= q[:, hi]), np.nan)
        scored[f"width{name}_kw"] = q[:, hi]-q[:, lo]
    return scored


def run(config_path, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Run directories are immutable; choose a new name")
    config = json.loads(Path(config_path).read_text())
    source = Path(config["data_directory"])
    contract = json.loads((source/"contract.json").read_text())
    if digest(source/"hourly.parquet") != contract["hourly_sha256"]:
        raise ValueError("Normalized data hash mismatch")
    frame = pd.read_parquet(source/"hourly.parquet")
    events = observations_from_hourly(frame, config["normal_receipt_lag_minutes"])
    capacity = contract["capacity_kw_dc"]
    all_origins = frame.index[frame.index < utc(config["evaluation_end"])]
    starts = event_starts(all_origins, config["seed"], config["event_spacing_days"])
    training_starts = event_starts(all_origins, config["seed"]+1, config["event_spacing_days"])
    output.mkdir(parents=True)
    (output/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    (output/"contract.json").write_text(json.dumps(contract, indent=2)+"\n")
    print("Building causal features and training fixed quantile models", flush=True)
    began = time.perf_counter()
    clean = replay_features(events, all_origins, config["normal_receipt_lag_minutes"])
    augmentation = replay_features(deliver_schedule(events, make_faults(training_starts, "irradiance_first",
                                    config["outage_hours"], config["restoration_gap_hours"])),
                                   all_origins, config["normal_receipt_lag_minutes"])
    with threadpool_limits(limits=1):
        models, train_counts = fit_models(frame, clean, augmentation, config, capacity)
        # Pickle is for locally generated trusted artifacts only.
        import pickle
        with (output/"models.pkl").open("wb") as handle:
            pickle.dump(models, handle)
        print(f"Training complete after {time.perf_counter()-began:.1f}s", flush=True)
        results, schedules = [], {}
        scenarios = ["clean", "pv_only", "irradiance_only", "joint", "irradiance_first", "pv_first", "no_backfill"]
        for scenario in scenarios:
            print(f"Replaying {scenario}", flush=True)
            faults = make_faults(starts, scenario, config["outage_hours"], config["restoration_gap_hours"])
            schedule = deliver_schedule(events, faults)
            features = clean if scenario == "clean" else replay_features(schedule, all_origins, config["normal_receipt_lag_minutes"])
            features = features.loc[features.index >= utc(config["train_end"])]
            features.to_parquet(output/f"features_{scenario}.parquet")
            base = base_predictions(models, features, capacity)
            predictions = causal_intervals(features, base, schedule, config, capacity)
            scored = score_predictions(predictions, frame, contract, config, faults)
            scored["scenario"] = scenario
            results.append(scored)
            scored.to_parquet(output/f"forecasts_{scenario}.parquet", index=False)
            schedules[scenario] = [{k: v.isoformat() if isinstance(v, pd.Timestamp) else v for k, v in asdict(f).items()} for f in faults]
    combined = pd.concat(results, ignore_index=True)
    eligible = combined[combined.valid_target & combined.daylight & combined.within_split]
    group = ["split", "scenario", "phase", "method", "horizon"]
    summary = eligible.groupby(group).agg(n=("nwis", "size"), nwis=("nwis", "mean"), wis_kw=("wis_kw", "mean"),
             mae_kw=("mae_kw", "mean"), coverage50=("coverage50", "mean"), coverage80=("coverage80", "mean"),
             coverage90=("coverage90", "mean"), width90_kw=("width90_kw", "mean"),
             events=("event_id", lambda x: len(set(x)-{-1}))).reset_index()
    summary.to_csv(output/"metrics.csv", index=False)
    (output/"event_schedules.json").write_text(json.dumps(schedules, indent=2)+"\n")
    source_hashes = {str(p): digest(p) for p in sorted(Path("solar_recovery").glob("*.py"))}
    manifest = {"status": "development pilot, no confirmatory inference", "elapsed_seconds": time.perf_counter()-began,
                "platform": platform.platform(), "python": platform.python_version(),
                "versions": {p: version(p) for p in ("numpy", "pandas", "scikit-learn", "pyarrow", "matplotlib")},
                "code_sha256": source_hashes, "config_sha256": digest(config_path),
                "training_counts": train_counts, "total_forecasts": len(combined),
                "invalid_truth_forecasts": int((~combined.valid_target).sum()),
                "split_crossing_forecasts": int((~combined.within_split).sum()),
                "normal_receipt_assumption": contract["receipt_assumption"],
                "limitations": ["One site, one scenario seed, no baseline hyperparameter tuning",
                                "All reported evaluation is development data; do not reuse it as a pristine final test",
                                "No statistical significance, cross-site result, or novelty demonstrated",
                                "ACI, mask-conditional and multiple-imputation comparators remain to implement"]}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    from .report import create_report
    create_report(output, combined, summary, contract, config)
    print(f"Pilot complete: {output}; {len(combined):,} forecasts", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pilot_nist_2015.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.config, args.output)
