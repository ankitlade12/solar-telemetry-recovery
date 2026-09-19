"""Measure loaded four-horizon inference; synthetic pools are workload fixtures.

Run after final analysis to avoid competing with the evaluation. This reads
verified visible features and model files, never held-out target columns or accuracy tables.
It changes no forecast, model, calibration parameter or scientific comparison.
"""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import pickle
import platform
import resource
import time

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_info, threadpool_limits

from solar_recovery.baselines_v3 import geometry
from solar_recovery.calibration import state_key
from solar_recovery.calibration_v2 import IssuedForecast
from solar_recovery.calibration_v3 import ContextCalibrator, full_mask, physical_context
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR


def prepared_calibrator(features, bases, contract, parameters, pool_size):
    """Untimed synthetic state; even the dense 720-score stress pool is artificial."""
    cal = ContextCalibrator("physical_recovery", **parameters)
    origin = features.index[0]
    random = np.random.default_rng(20260912)
    for h in (1, 2, 3, 4):
        state = enriched_state(features.iloc[0], bases[h][0], origin, h, contract)
        context, key, mask = physical_context(state), state_key(state), full_mask(state)
        for j, age in enumerate(np.linspace(5, 719, pool_size)):
            prior = origin-pd.Timedelta(hours=float(age))
            saved_key = key if j % 4 == 0 else tuple((value+1) % 3 for value in key)
            record = IssuedForecast(f"synthetic:{h}:{j}", prior, prior.floor("h")+h*HOUR, h,
                bases[h][0].copy(), bases[h][0].copy(), saved_key, mask,
                context+random.normal(0, .1, len(context)))
            scores = random.normal(0, .02*contract["capacity_kw_dc"], 3)
            cal.scores[h].append((record, scores))
    return cal


def enriched_state(visible, base, origin, h, contract):
    state = visible.copy()
    state["target_solar_sine"] = geometry(pd.DatetimeIndex([origin.floor("h")+h*HOUR]), contract)[0]
    state["base_median_normalized"] = base[3]/contract["capacity_kw_dc"]
    state["base_width90_normalized"] = (base[6]-base[0])/contract["capacity_kw_dc"]
    return state


def loaded_call(model, features, cal=None):
    if len(features) != 1:
        raise ValueError("Benchmark one forecast origin per four-horizon call")
    bases = model.predict(features)
    if set(bases) != {1, 2, 3, 4}:
        raise ValueError("The latency request must contain all four horizons")
    if cal is None:
        return bases
    output, origin = {}, features.index[0]
    for h, values in bases.items():
        state = enriched_state(features.iloc[0], values[0], origin, h, model.contract)
        adjusted, _ = cal.issue(f"benchmark:{origin}:{h}", origin, h, values[0], state,
                               state["target_solar_sine"] > 0, origin.floor("h")+h*HOUR)
        output[h] = adjusted[None, :]
    return output


def benchmark(root, output, hardware_path, samples=32):
    root, output, hardware_path = Path(root), Path(output), Path(hardware_path)
    if output.exists():
        raise FileExistsError("Choose a new benchmark output directory")
    if samples < 20:
        raise ValueError("At least 20 recorded calls per workload are required")
    manifest = json.loads((root/"manifest.json").read_text())
    verified = json.loads((root/"verification.json").read_text())
    analysis = json.loads((root/"analysis/manifest.json").read_text())
    if manifest["status"] != "complete frozen evaluation" or not verified["status"].startswith("passed") or analysis["status"] != "complete analysis":
        raise ValueError("Wait for completed evaluation, verification and analysis")
    if verified["manifest_sha256"] != digest(root/"manifest.json") or analysis["source_manifest_sha256"] != digest(root/"manifest.json"):
        raise ValueError("Changed completed source manifest")
    config = json.loads((root/"config.json").read_text())
    hardware = json.loads(hardware_path.read_text())
    sources, records, began = {}, [], time.perf_counter()
    output.mkdir(parents=True)
    with threadpool_limits(limits=1):
        pools = threadpool_info()
        for site in config["sites"]:
            model_path = root/site/"models_2016_primary_none.pkl"
            if digest(model_path) != manifest["training"][f"{site}/2016/primary/none"]["model_sha256"]:
                raise ValueError("Changed fitted model")
            with model_path.open("rb") as handle:
                bundle = pickle.load(handle)
            model = bundle["quantile"]
            del bundle
            sources[str(model_path)] = digest(model_path)
            for case in ("clean", "joint_gradual"):
                path = root/site/f"features_{case}.parquet"
                if digest(path) != verified["files_sha256"][str(path.relative_to(root))]:
                    raise ValueError("Changed verified visible features")
                features = pd.read_parquet(path)
                sources[str(path)] = digest(path)
                eligible = features.index >= pd.Timestamp(config["evaluation_start"])
                for h in (1, 2, 3, 4):
                    eligible &= geometry(features.index.floor("h")+h*HOUR, model.contract) > 0
                indices = np.flatnonzero(eligible)
                if len(indices) < samples:
                    raise ValueError("Insufficient daylight origins for declared latency sample")
                selected = indices[np.linspace(0, len(indices)-1, samples).astype(int)]
                for mode, pool_size in (("raw", 0), ("recovery", 0), ("recovery", 360), ("recovery", 720)):
                    for trial, index in enumerate([*selected[:3], *selected]):
                        row = features.iloc[[index]]
                        preliminary = model.predict(row)
                        cal = prepared_calibrator(row, preliminary, model.contract, config["calibration"], pool_size) if mode == "recovery" else None
                        start = time.perf_counter_ns()
                        predicted = loaded_call(model, row, cal)
                        elapsed_ms = (time.perf_counter_ns()-start)/1e6
                        if any(values.shape != (1, 7) or not np.isfinite(values).all() or (values < 0).any() or (np.diff(values, axis=1) < 0).any() for values in predicted.values()):
                            raise ValueError("Invalid timed forecast output")
                        if trial >= 3:
                            records.append({"site": site, "case_id": case, "mode": mode, "synthetic_pool_per_horizon": pool_size,
                                            "origin": row.index[0], "trial": trial-3, "four_horizon_latency_ms": elapsed_ms})
                    print(f"Benchmarked {site}/{case}/{mode}/pool={pool_size}: {samples} calls", flush=True)
    raw = pd.DataFrame(records)
    summary = raw.groupby(["site", "case_id", "mode", "synthetic_pool_per_horizon"]).four_horizon_latency_ms.agg(
        calls="size", median_ms="median", p95_ms=lambda x: x.quantile(.95), minimum_ms="min", maximum_ms="max").reset_index()
    summary["p95_under_one_second"] = summary.p95_ms.lt(1000)
    raw.to_csv(output/"calls.csv", index=False)
    summary.to_csv(output/"summary.csv", index=False)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {"status": "complete loaded-model latency benchmark", "hardware": hardware,
        "hardware_source_sha256": digest(hardware_path), "source_manifest_sha256": digest(root/"manifest.json"),
        "sources_sha256": sources, "code_sha256": digest(Path(__file__)), "python": platform.python_version(),
        "platform": platform.platform(), "versions": {p: version(p) for p in ("numpy", "pandas", "scikit-learn", "threadpoolctl")},
        "threadpools_during_timing": pools, "elapsed_seconds": time.perf_counter()-began,
        "benchmark_process_peak_rss_bytes": int(peak if platform.system() == "Darwin" else peak*1024),
        "sampling": "32 evenly spaced all-four-horizon daylight origins per site/case by default; three unrecorded warmup calls per workload; pandas linear empirical p95",
        "actual_samples_per_workload": samples,
        "scope": "Warm loaded prediction from prepared visible features, four horizons/seven quantiles; recovery includes context construction, corrections and pending-record creation. No held-out target columns are accessed. Synthetic 0/360/720-score pools are controlled workloads, not measured operational histories; 720 is a dense stress case.",
        "exclusions": "Model loading, receipt/history construction, label ingestion/backlog processing, score-pool preparation, network, disk writes and process startup are outside the timer. Untimed predictions prepare each fixture and warm caches. Peak RSS covers the benchmark process including model-bundle loading; it is not training peak memory. Shared personal hardware is not a dedicated-server latency guarantee.",
        "files_sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
    (output/"manifest.json").write_text(json.dumps(result, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--output", required=True)
    parser.add_argument("--hardware", default="research/hardware.json")
    parser.add_argument("--samples", type=int, default=32)
    args = parser.parse_args()
    benchmark(args.run, args.output, args.hardware, args.samples)
