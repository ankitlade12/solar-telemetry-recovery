"""Generate an auditable development report from saved, scored forecasts."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import solar_elevation


def markdown_table(frame):
    header = "| " + " | ".join(frame.columns) + " |"
    lines = [header, "| " + " | ".join(["---"]*len(frame.columns)) + " |"]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(f"{x:.4f}" if isinstance(x, float) else str(x) for x in row) + " |")
    return "\n".join(lines)


def create_report(output, combined, summary, contract, config):
    output = Path(output)
    eligible = combined.loc[combined.valid_target & combined.daylight & combined.within_split].copy()
    development = eligible[eligible.split == "development_evaluation"].copy()
    aggregate = development.groupby(["scenario", "phase", "method"]).agg(
        n=("nwis", "size"), nwis=("nwis", "mean"), coverage90=("coverage90", "mean"),
        width90_kw=("width90_kw", "mean"), events=("event_id", lambda x: len(set(x)-{-1}))).reset_index()
    aggregate.to_csv(output/"development_summary.csv", index=False)
    selected = aggregate[(aggregate.scenario == "irradiance_first") & (aggregate.phase == "recovery")]
    # Pair identical target/origin/horizon/method against the clean delivery run.
    clean = development[development.scenario == "clean"][["origin", "horizon", "method", "nwis"]]
    paired = development.merge(clean.rename(columns={"nwis": "clean_nwis"}), on=["origin", "horizon", "method"], validate="many_to_one")
    paired["excess_nwis"] = paired.nwis-paired.clean_nwis
    recovery = paired[(paired.phase == "recovery") & (paired.scenario == "irradiance_first")]
    curve = recovery.groupby(["recovery_hour", "method"]).agg(
        nwis=("nwis", "mean"), excess_nwis=("excess_nwis", "mean"), n=("nwis", "size"),
        events=("event_id", "nunique")).reset_index()
    curve.to_csv(output/"recovery_curve.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for method in ("quantile_raw", "rolling", "context", "recovery"):
        part = curve[curve.method == method]
        axes[0].plot(part.recovery_hour, part.nwis, marker=".", label=method)
        axes[1].plot(part.recovery_hour, part.excess_nwis, marker=".", label=method)
    axes[0].set_ylabel("Mean WIS / DC nameplate capacity")
    axes[1].set_ylabel("Excess normalized WIS over clean delivery")
    axes[1].axhline(0, color="grey", lw=.8)
    for ax in axes:
        ax.set_xlabel("Hours after scheduled full restoration")
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("Development pilot: irradiance restored before PV; daylight targets, 1–4 h horizons")
    fig.savefig(output/"recovery_curve.png", dpi=180)
    fig.savefig(output/"recovery_curve.pdf")
    plt.close(fig)
    # Calendar-first example selection: no selection by forecast error.
    faults = json.loads((output/"event_schedules.json").read_text())["irradiance_first"]
    scheduled_development = sum(pd.Timestamp(config["validation_end"]) <= pd.Timestamp(f["pv_return"])
                                < pd.Timestamp(config["evaluation_end"]) for f in faults)
    observed_events = int(selected.events.max()) if len(selected) else 0
    full_restorations = pd.DatetimeIndex([f["pv_return"] for f in faults])
    daylight_restorations = int((solar_elevation(full_restorations, contract["latitude"], contract["longitude"]) > 0).sum())
    first = next(f for f in faults if pd.Timestamp(f["start"]) >= pd.Timestamp(config["validation_end"]))
    start, restored = pd.Timestamp(first["start"]), pd.Timestamp(first["pv_return"])
    sample = combined[(combined.scenario == "irradiance_first") & (combined.horizon == 1)
                      & (combined.origin >= start-pd.Timedelta(hours=12))
                      & (combined.origin < restored+pd.Timedelta(hours=24))
                      & combined.method.isin(["rolling", "recovery"])].copy()
    sample.to_csv(output/"example_event.csv", index=False)
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True, constrained_layout=True)
    for ax, method in zip(axes, ["rolling", "recovery"]):
        part = sample[sample.method == method].sort_values("origin")
        ax.fill_between(part.origin, part.q05, part.q95, alpha=.22, label="90% interval")
        ax.plot(part.origin, part.q50, label="median", lw=1)
        ax.plot(part.origin, part.actual_kw, label="observed target", color="black", lw=1)
        ax.axvspan(start, pd.Timestamp(first["irradiance_return"]), color="red", alpha=.09)
        ax.axvspan(pd.Timestamp(first["irradiance_return"]), restored, color="orange", alpha=.15)
        ax.set_ylabel(f"{method}\nDC power (kW)")
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=8, loc="upper right")
    axes[1].set_xlabel("Forecast origin (UTC); target is the following completed hour")
    fig.suptitle("First scheduled October event: red = joint outage, orange = PV still unavailable")
    fig.savefig(output/"example_event.png", dpi=180)
    fig.savefig(output/"example_event.pdf")
    plt.close(fig)
    indexed = selected.set_index("method")
    if {"rolling", "recovery"} <= set(indexed.index):
        delta = 100*(indexed.loc["recovery", "nwis"]/indexed.loc["rolling", "nwis"]-1)
        conclusion = (f"For the preselected irradiance-first recovery slice, recovery calibration changes mean normalized WIS "
                      f"by {delta:+.2f}% relative to rolling calibration (lower is better). "
                      "This is descriptive evidence from one site and one schedule seed, not a significance or novelty claim.")
    else:
        conclusion = "The designated recovery slice has insufficient observations for a comparison."
    report = f"""# NIST 2015 development pilot

{conclusion}

## Scope and interpretation

Real measured DC power and measured plane-of-array irradiance from PVDAQ system 4902, {contract['capacity_kw_dc']} kW DC nameplate. The simulated faults affect information delivery, never the physical target. Original operational receipt times are unavailable: immediate receipt at a completed hour is an explicit normal-operation assumption. Native gaps and excluded measurements remain unavailable in every scenario.

The fixed quantile model is trained through June; July–mid-August warms calibration, mid-August–September is validation, and October–December is development evaluation. Forecasts whose targets cross a split end are excluded from that split's metrics. Online calibration continues causally across splits. All these dates are now development data and must not be presented as a pristine final test.

**Schedule limitation:** only {daylight_restorations} of {len(faults)} scheduled full restorations occur during geometric daylight. Starting 12-hour faults during the day places restoration at night, weakening the test of immediate daytime recovery. A separate exploratory daytime-restoration probe is documented in the repository; this schedule alone cannot settle that research question.

Seven delivery scenarios × four horizons × five methods are saved. Baselines are calibrated persistence, raw boosted quantiles, rolling calibration, and context-weighted calibration. Recovery calibration mixes state-matched and global empirical score distributions. All boosted methods share the same frozen model and block-augmented training. The methods are empirical; finite-sample conformal coverage is not established.

## Preselected recovery slice

Irradiance is restored three hours before PV during 12-hour events. Recovery means the first 24 hours after scheduled full restoration; observable feature state can still reflect native sensor gaps. Of {scheduled_development} events with full restoration scheduled within the development period, {observed_events} have scorable daylight recovery forecasts. Rows pool eligible daylight forecasts over 1–4-hour horizons; `n` counts overlapping forecasts, and `events` counts distinct scheduled events.

{markdown_table(selected[['method', 'n', 'events', 'nwis', 'coverage90', 'width90_kw']])}

Nominal coverage is 0.90. Assess coverage and width together with WIS; narrower intervals alone are not a success. This first calibrator only expands base intervals and cannot sharpen an already over-wide model. Calibration pools include all available hours, while primary metrics use daylight; that mismatch is an explicit limitation to investigate. Primary reporting uses solar geometry at the target-hour midpoint, independent of measured future weather. Nighttime forecasts and validity flags remain in the Parquet files for audits.

![Recovery curve](recovery_curve.png)

The paired excess-WIS curve compares each degraded forecast with the same method, origin and horizon under clean delivery. The clean method has its own causally updated calibration history. Hourly points can contain different target subsets; counts are in `recovery_curve.csv`. No confidence bands or claims of recovery time are warranted from this plot alone.

![Example event](example_event.png)

The example is the first scheduled event in October, selected by date. Missing observations appear as gaps.

## Artifacts and reproduction

- `metrics.csv`: split/scenario/phase/method/horizon metrics and counts.
- `development_summary.csv`: pooled development metrics for every available scenario/phase/method.
- `forecasts_*.parquet`: immutable issued quantiles, original base quantiles, delivered-state fields, calibration support and evaluator annotations.
- `features_*.parquet`: information visible at each forecast origin.
- `event_schedules.json`: reproducible delivery interventions.
- `manifest.json`, `config.json`, `contract.json`: code/config/data hashes, package versions, training counts and assumptions.
- `models.pkl`: locally generated trusted model artifact; never load untrusted pickle files.
- CSV files alongside PNG/PDF figures contain their source data.

From the repository root, run `python3 -m solar_recovery.pilot --config configs/pilot_nist_2015.json --output runs/nist_2015_pilot_v2` to reproduce into a fresh directory. Run directories are immutable.

## Required before a paper claim

Resolve catalog quality flags and sensor-quality exclusions; assess daytime completeness and exclusion sensitivity. Add independently selected sites and an untouched final period; freeze the protocol before inspecting those results. Implement and fairly tune adaptive conformal, mask-conditional, and imputation comparators; add multiple fault seeds, durations, normal receipt delays, ablations and event/site-level uncertainty. Distinguish delayed backfill from permanent loss. Report negative findings and verify whether the proposed method adds value beyond context weighting.

No acceptance probability, cross-site robustness, statistical significance, operational receipt fidelity or new theoretical guarantee follows from this pilot.
"""
    (output/"README.md").write_text(report)
