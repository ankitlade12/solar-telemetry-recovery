"""Controlled development ablation using the frozen daytime-probe base outputs."""
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from solar_recovery.calibration_v2 import SignedCalibrator
from solar_recovery.data import solar_elevation
from solar_recovery.pilot import digest, score_predictions
from solar_recovery.replay import HOUR, Outage, deliver_schedule, observations_from_hourly
from solar_recovery.report import markdown_table


def run(output="runs/nist_2015_calibration_v2"):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Use a fresh experiment directory")
    parent = Path("runs/nist_2015_daytime_probe_v1")
    config = json.loads(Path("configs/pilot_nist_2015.json").read_text())
    contract = json.loads(Path("runs/nist_2015_pilot_v1/contract.json").read_text())
    original_manifest = json.loads((parent/"manifest.json").read_text())
    frame = pd.read_parquet(Path(config["data_directory"])/"hourly.parquet")
    assert digest(Path(config["data_directory"])/"hourly.parquet") == contract["hourly_sha256"]
    features = pd.read_parquet(parent/"features.parquet")
    columns = [f"q{q:02d}" for q in (5, 10, 25, 50, 75, 90, 95)]
    # The calibration stage reads no evaluator labels from the prior run.
    saved = pd.read_parquet(parent/"forecasts.parquet", columns=["origin", "horizon", "method"]+columns)
    saved = saved[saved.method.eq("quantile_raw")]
    base = {h: saved[saved.horizon.eq(h)].set_index("origin").reindex(features.index)[columns].to_numpy()
            for h in config["horizons"]}
    faults = [Outage(**event) for event in original_manifest["events"]]
    events = deliver_schedule(observations_from_hourly(frame), faults)
    labels = [event for event in events if event.stream == "pv"]
    definitions = {
        "expand_all": {"method": "rolling", "daylight_only": False, "expansion_only": True},
        "signed_all": {"method": "rolling", "daylight_only": False},
        "expand_day": {"method": "rolling", "expansion_only": True},
        "signed_day": {"method": "rolling"},
        "recency_day": {"method": "recency"},
        "context_day": {"method": "context"},
        "mask_day": {"method": "mask"},
        "recovery_day": {"method": "recovery"},
        "aci_bounded_day": {"method": "aci_bounded"}}
    calibrators = {name: SignedCalibrator(**kwargs) for name, kwargs in definitions.items()}
    target_daylight = {h: solar_elevation(features.index+(h-.5)*HOUR, contract["latitude"], contract["longitude"]) > 0
                       for h in config["horizons"]}
    output.mkdir(parents=True)
    started, pointer, rows = time.perf_counter(), 0, []
    for i, (origin, state) in enumerate(features.iterrows()):
        while pointer < len(labels) and labels[pointer].receipt <= origin:
            for cal in calibrators.values():
                cal.receive(labels[pointer], origin)
            pointer += 1
        for h in config["horizons"]:
            raw = base[h][i]
            forecasts = {"raw": (raw, {"fallback": "uncalibrated", "pool_size": 0, "effective_n": 0.,
                                       "matching_size": 0, "nesting_repaired": False})}
            for name, cal in calibrators.items():
                forecasts[name] = cal.issue(f"{origin.isoformat()}:{h}", origin, h, raw, state, bool(target_daylight[h][i]))
            for name, (quantiles, info) in forecasts.items():
                rows.append({"origin": origin, "target_end": origin+h*HOUR, "horizon": h, "method": name,
                             **dict(zip(columns, quantiles)), **{"base_"+k: v for k, v in zip(columns, raw)}, **info})
        if i % 500 == 0:
            print(f"Calibrated {i}/{len(features)} origins", flush=True)
    predictions = pd.DataFrame(rows)
    scored = score_predictions(predictions, frame, contract, config, faults)
    scored["scenario"] = "daytime_irradiance_first_complete_backfill"
    scored["phase_detail"] = scored.phase
    scored.loc[scored.phase.eq("recovery") & scored.recovery_hour.lt(6), "phase_detail"] = "recovery_0_to_6h"
    scored.loc[scored.phase.eq("recovery") & scored.recovery_hour.ge(6), "phase_detail"] = "recovery_6_to_24h"
    scored.to_parquet(output/"forecasts.parquet", index=False)
    eligible = scored[scored.valid_target & scored.daylight & scored.within_split].copy()
    summary = eligible.groupby(["split", "phase_detail", "method"]).agg(n=("nwis", "size"),
        nwis=("nwis", "mean"), coverage50=("coverage50", "mean"), coverage80=("coverage80", "mean"),
        coverage90=("coverage90", "mean"), width90_kw=("width90_kw", "mean"),
        repair_fraction=("nesting_repaired", "mean"), events=("event_id", lambda x: len(set(x)-{-1}))).reset_index()
    summary.to_csv(output/"metrics.csv", index=False)
    raw_q = scored[columns].to_numpy()
    assert np.isfinite(raw_q).all() and (raw_q >= 0).all() and (np.diff(raw_q, axis=1) >= 0).all()
    assert not scored.duplicated(["origin", "horizon", "method"]).any()
    np.testing.assert_array_equal(scored.q50, scored.base_q50)
    assert scored.groupby(["origin", "horizon"])[["base_"+c for c in columns]].nunique().eq(1).all().all()
    manifest = {"status": "controlled development ablation; not confirmatory", "parent": str(parent),
        "parent_forecast_sha256": digest(parent/"forecasts.parquet"), "parent_features_sha256": digest(parent/"features.parquet"),
        "source_data_sha256": contract["hourly_sha256"], "definitions": definitions,
        "common_defaults": {"window_hours": 720, "tau_hours": 336, "shrinkage": 50., "bandwidth": 1.,
                            "min_scores": 30, "gamma": .005, "alpha_bounds": [.01, .99]},
        "code_sha256": {str(p): digest(p) for p in sorted(Path("solar_recovery").glob("*.py"))},
        "runner_sha256": digest(__file__), "total_forecasts": len(scored), "elapsed_seconds": time.perf_counter()-started,
        "checks_passed": ["source data hash", "finite ordered nonnegative quantiles", "unique forecast keys",
                          "identical bases across all methods", "unchanged medians"],
        "alpha_clip_counts": {name: cal.alpha_clip_count for name, cal in calibrators.items()},
        "limitations": ["single development site-year and fault seed", "complete immediate backfill only",
                        "empirical mask/context variants, not full reproductions of published comparators",
                        "bounded ACI is not the original unbounded algorithm; no inherited guarantee",
                        "equal parameter choices, no method-specific tuning"]}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    table = summary[summary.split.eq("development_evaluation") & summary.phase_detail.eq("recovery_0_to_6h")]
    report = f"""# Signed calibration development ablation

The same frozen base forecasts, delivered features, targets and daytime-restoration schedule are used for every method. This isolates calibration choices; no new model is trained and no untouched test period is used. All results are development evidence.

## First six recovery hours

{markdown_table(table.drop(columns=['split', 'phase_detail']))}

Lower normalized WIS is better; coverage50/80/90 targets are 0.50/0.80/0.90. Forecast records overlap across horizons. Complete phase/split metrics are in `metrics.csv`; no significance or novelty claim follows from this table.

## Controlled comparisons

- `expand_all` versus `signed_all`: permit signed correction with the same all-hours uniform pool.
- `expand_day` versus `signed_day`: the same sign comparison with daylight-only feedback.
- `signed_all` versus `signed_day`: isolate the daylight scope.
- `signed_day` versus `recency_day`: isolate recency weights.
- `recency_day` versus `context_day`, `mask_day` or `recovery_day`: additional conditioning with the same recency-weighted global component.
- `signed_day` versus `aci_bounded_day`: fixed versus receipt-gated adaptive miscoverage levels, both with uniform rolling pools.

Signed adjustment is followed by outward interval nesting and median containment, then nonnegative clipping. Repairs are counted. This keeps interval identities and does not move the base median. Calibration uses only labels delivered by each origin and stores the originally issued interval for adaptive feedback.

The adaptive comparator clips miscoverage levels to [0.01, 0.99] and caps requested score quantiles at the largest available score. It is a finite engineering variant, not an exact reproduction of the original ACI's possible unbounded/empty sets. Neither its original guarantee nor ordinary split-conformal exchangeability coverage is claimed. Context/mask/recovery variants are transparent empirical comparators, not replacements for faithful published-method reproduction.

## Provenance

`manifest.json` records parent/data/code hashes, parameters, validation checks and adaptive clipping counts. `forecasts.parquet` records final/base quantiles, pool support, signed corrections, adaptive levels and evaluator truth added after prediction. The original pilot artifacts remain unchanged. Run `python3 -m research.run_calibration_v2` only into a fresh output directory (the module's `run(output=...)` accepts a new path).

References: Romano, Patterson and Candès, [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222), 2019; Gibbs and Candès, [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170), 2021. Weighted, delayed and bounded adaptations here are explicitly empirical.
"""
    (output/"README.md").write_text(report)
    print(f"Completed {len(scored):,} forecasts in {output}", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runs/nist_2015_calibration_v2")
    args = parser.parse_args()
    run(args.output)
