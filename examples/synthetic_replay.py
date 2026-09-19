"""Small reproducible demonstration; every measurement is explicitly synthetic."""
import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from research.run_annual_calibration import causal_forecasts
from solar_recovery.baselines_v3 import geometry, PROFILES, QuantileForecaster, target_ends
from solar_recovery.metrics import wis
from solar_recovery.pilot import digest
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import Fault, deliver_schedule, replay_features


def run(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Choose a new output directory")
    output.mkdir(parents=True)
    contract = {"site": "explicitly_synthetic", "capacity_kw_dc": 10., "latitude": 39., "longitude": -105.}
    seed = 1289
    ends = pd.date_range("2020-04-01", periods=24*45+1, freq="h", tz="UTC")
    rng = np.random.default_rng(seed)
    cloud = np.clip(.8+.15*np.sin(np.arange(len(ends))/17)+rng.normal(0, .05, len(ends)), .2, 1.)
    solar = geometry(ends, contract)
    truth = pd.DataFrame({"pv": 8*solar*cloud, "irradiance": 1000*solar*cloud}, index=ends)
    cutoff = ends[24*30]
    events = observations_from_hourly(truth, 1)
    training = replay_features([o for o in events if o.end <= cutoff],
        pd.date_range(ends[48]+pd.Timedelta(minutes=1), cutoff-pd.Timedelta(minutes=59), freq="h"))
    profile = {"max_iter": 30, "max_leaf_nodes": 7, "min_samples_leaf": 10, "learning_rate": .1}
    PROFILES["synthetic_example"] = profile
    with threadpool_limits(limits=1):
        model = QuantileForecaster("synthetic_example", seed, True).fit(training, truth, contract, cutoff, horizons=(1, 4))
        start = cutoff+pd.Timedelta(days=3, hours=12, minutes=1)
        fault = Fault(start, start+pd.Timedelta(hours=12), start+pd.Timedelta(hours=15), "gradual", 15)
        schedule = deliver_schedule(events, [fault])
        origins = pd.date_range(cutoff+pd.Timedelta(days=1, minutes=1), ends[-1]-pd.Timedelta(hours=4, minutes=-1), freq="h")
        features = replay_features(schedule, origins)
        bases = model.predict(features)
        parameters = {"daylight_only": True, "window_hours": 720, "tau_hours": 336, "shrinkage": 50.,
            "bandwidth": 1., "min_scores": 30, "gamma": .001}
        forecasts, diagnostics, counts = causal_forecasts(features, bases, schedule, contract, parameters,
            ["raw", "recency", "physical_availability", "physical_recovery"])
    rows = []
    for method, by_horizon in forecasts.items():
        for h, q in by_horizon.items():
            targets = target_ends(features, h)
            y = truth.pv.reindex(targets).to_numpy()
            rows.append(pd.DataFrame({"origin": features.index, "target_end": targets, "horizon": h,
                "method": method, "actual_kw": y, "daylight": geometry(targets, contract) > 0,
                "nwis": wis(y, q)/contract["capacity_kw_dc"],
                **{f"q{j:02d}": q[:, i] for i, j in enumerate((5, 10, 25, 50, 75, 90, 95))}}))
    scored = pd.concat(rows, ignore_index=True)
    if not np.isfinite(scored.nwis).all():
        raise ValueError("Synthetic example has invalid scores")
    truth.to_parquet(output/"synthetic_measurements.parquet")
    features.to_parquet(output/"visible_features.parquet")
    scored.to_parquet(output/"forecasts.parquet", index=False)
    diagnostics.to_parquet(output/"diagnostics.parquet", index=False)
    summary = scored.loc[scored.daylight].groupby(["method", "horizon"]).agg(n=("nwis", "size"), nwis=("nwis", "mean")).reset_index()
    summary.to_csv(output/"metrics.csv", index=False)
    manifest = {"data_kind": "Entirely synthetic demonstration, not paper performance evidence", "seed": seed,
        "profile": profile, "contract": contract, "cutoff": cutoff.isoformat(),
        "fault": {k: v.isoformat() if isinstance(v, pd.Timestamp) else v for k, v in asdict(fault).items()},
        "forecasts": len(scored), "calibration_updates": counts, "python": platform.python_version(),
        "versions": {p: version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "pyarrow", "threadpoolctl")},
        "code_sha256": {str(p): digest(p) for p in [Path(__file__).relative_to(Path.cwd()),
            *sorted(Path("solar_recovery").glob("*.py")), Path("research/run_annual_calibration.py")]},
        "artifact_sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Completed synthetic example: {len(scored):,} forecast records in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
