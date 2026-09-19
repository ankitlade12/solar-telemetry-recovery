"""Exploratory daytime-restoration probe using the original pilot's frozen model."""
import argparse
import hashlib
import json
from pathlib import Path
import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from solar_recovery.pilot import (event_starts, make_faults, base_predictions, causal_intervals,
                                  score_predictions, digest)
from solar_recovery.replay import HOUR, observations_from_hourly, deliver_schedule, replay_features, utc
from solar_recovery.data import solar_elevation
from solar_recovery.report import markdown_table


def run(parent, output):
    parent, output = Path(parent), Path(output)
    if output.exists():
        raise FileExistsError("Probe output must be fresh")
    config = json.loads((parent/"config.json").read_text())
    contract = json.loads((parent/"contract.json").read_text())
    source = Path(config["data_directory"])/"hourly.parquet"
    assert digest(source) == contract["hourly_sha256"]
    frame = pd.read_parquet(source)
    origins = frame.index[frame.index < utc(config["evaluation_end"])]
    starts = [t-12*HOUR for t in event_starts(origins, config["seed"], config["event_spacing_days"])]
    faults = make_faults(starts, "irradiance_first", config["outage_hours"], config["restoration_gap_hours"])
    schedule = deliver_schedule(observations_from_hourly(frame, config["normal_receipt_lag_minutes"]), faults)
    output.mkdir(parents=True)
    print("Daytime probe: using frozen pilot model, restoration shifted twelve hours earlier", flush=True)
    features = replay_features(schedule, origins, config["normal_receipt_lag_minutes"])
    features = features[features.index >= utc(config["train_end"])]
    # Parent model was generated locally in this workspace, not downloaded.
    with (parent/"models.pkl").open("rb") as handle:
        models = pickle.load(handle)
    with threadpool_limits(limits=1):
        base = base_predictions(models, features, contract["capacity_kw_dc"])
        predictions = causal_intervals(features, base, schedule, config, contract["capacity_kw_dc"])
    scored = score_predictions(predictions, frame, contract, config, faults)
    scored["scenario"] = "irradiance_first_daytime_restoration"
    scored.to_parquet(output/"forecasts.parquet", index=False)
    features.to_parquet(output/"features.parquet")
    eligible = scored[scored.valid_target & scored.daylight & scored.within_split].copy()
    eligible["phase_detail"] = eligible.phase
    eligible.loc[(eligible.phase == "recovery") & (eligible.recovery_hour < 6), "phase_detail"] = "recovery_0_to_6h"
    eligible.loc[(eligible.phase == "recovery") & (eligible.recovery_hour >= 6), "phase_detail"] = "recovery_6_to_24h"
    summary = eligible.groupby(["split", "phase_detail", "method"]).agg(n=("nwis", "size"), nwis=("nwis", "mean"),
        coverage90=("coverage90", "mean"), width90_kw=("width90_kw", "mean"),
        events=("event_id", lambda x: len(set(x)-{-1}))).reset_index()
    summary.to_csv(output/"metrics.csv", index=False)
    development = eligible[eligible.split == "development_evaluation"]
    curve = development[development.phase == "recovery"].groupby(["recovery_hour", "method"]).agg(
        nwis=("nwis", "mean"), n=("nwis", "size"), events=("event_id", "nunique")).reset_index()
    curve.to_csv(output/"recovery_curve.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    for method in ["quantile_raw", "rolling", "context", "recovery"]:
        part = curve[curve.method == method]
        ax.plot(part.recovery_hour, part.nwis, marker=".", label=method)
    ax.set(xlabel="Hours after scheduled full restoration", ylabel="Mean WIS / DC nameplate capacity",
           title="Exploratory daytime-restoration probe; daylight targets, 1–4 h horizons")
    ax.legend(fontsize=8)
    ax.grid(alpha=.2)
    fig.savefig(output/"recovery_curve.png", dpi=180)
    fig.savefig(output/"recovery_curve.pdf")
    plt.close(fig)
    restore = pd.DatetimeIndex([f.pv_return for f in faults])
    n_day = int((solar_elevation(restore, contract["latitude"], contract["longitude"]) > 0).sum())
    quantiles = scored[[f"q{q:02d}" for q in (5, 10, 25, 50, 75, 90, 95)]].to_numpy()
    assert np.isfinite(quantiles).all() and (np.diff(quantiles, axis=1) >= 0).all()
    assert not scored.duplicated(["origin", "horizon", "method"]).any()
    record = {"status": "post-inspection exploratory diagnostic, not confirmatory",
              "parent": str(parent), "parent_model_sha256": digest(parent/"models.pkl"),
              "parent_config": config, "hourly_sha256": digest(source),
              "code_sha256": {str(p): digest(p) for p in sorted(Path("solar_recovery").glob("*.py"))},
              "probe_script_sha256": digest(__file__), "schedule_change": "subtract twelve hours from each original start and restoration",
              "total_forecasts": len(scored), "scheduled_events": len(faults), "daytime_full_restorations": n_day,
              "checks_passed": ["source hash", "finite ordered quantiles", "unique forecast keys"],
              "events": [{"start": f.start.isoformat(), "irradiance_return": f.irradiance_return.isoformat(),
                          "pv_return": f.pv_return.isoformat()} for f in faults]}
    (output/"manifest.json").write_text(json.dumps(record, indent=2)+"\n")
    table = summary[(summary.split == "development_evaluation") & (summary.phase_detail != "background")]
    text = f"""# Daytime restoration: exploratory follow-up

The original 12-hour fault schedule restored both streams at night. This probe shifts the same events twelve hours earlier: PV returns at UTC 14–18, with irradiance restored three hours earlier. {n_day} of {len(faults)} scheduled full restorations occur in geometric daylight. The model, source data, methods and hyperparameters are unchanged; causal calibration is replayed under the new delivery schedule.

This diagnostic was chosen after inspecting the original schedule and preliminary results. It is development evidence, not a new untouched test or a preregistered comparison. Missing native target data still limits which events can be scored. Training augmentation used the original schedule distribution, so this also changes the restoration timing relative to augmentation.

## Development results

Lower normalized WIS is better; nominal coverage is 0.90. Forecasts overlap across horizons and are not independent replicates. Recovery slices refer to time since scheduled restoration, not a guarantee of native sensor health.

{markdown_table(table[['phase_detail', 'method', 'n', 'events', 'nwis', 'coverage90', 'width90_kw']])}

![Daytime recovery](recovery_curve.png)

The initial calibrators only expand intervals. The all-hours calibration pool and daylight evaluation target different distributions; sparse state support and nighttime score mass remain limitations. Do not interpret a nearly overlapping curve as evidence of equivalence or general method failure. Multiple independent sites, seeds, stronger baselines and a frozen protocol remain necessary.

## Reproduction

Run `python3 -m research.run_daytime_probe --parent {parent} --output runs/nist_2015_daytime_probe_v2`. Parent models must be the trusted locally generated artifacts. `metrics.csv`, `forecasts.parquet`, `features.parquet`, the figure's CSV/PDF, and `manifest.json` provide the results and provenance.
"""
    (output/"README.md").write_text(text)
    print(f"Daytime probe complete: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", default="runs/nist_2015_pilot_v1")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.parent, args.output)
