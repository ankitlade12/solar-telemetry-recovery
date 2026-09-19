"""Paired event diagnostics for the controlled development calibration ablation."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from solar_recovery.pilot import digest
from solar_recovery.report import markdown_table


def run():
    output = Path("runs/nist_2015_calibration_v2")
    frame = pd.read_parquet(output/"forecasts.parquet")
    eligible = frame[frame.valid_target & frame.daylight & frame.within_split & frame.split.eq("development_evaluation")]
    keys = ["origin", "horizon", "event_id", "phase_detail"]
    pivot = eligible.pivot(index=keys, columns="method", values="nwis").reset_index()
    comparisons = [("signed_day", "expand_day"), ("context_day", "recency_day"), ("recovery_day", "recency_day")]
    phases = ["recovery_0_to_6h", "recovery_6_to_24h"]
    rng = np.random.default_rng(20260911)
    rows, event_rows = [], []
    for phase in phases:
        part = pivot[pivot.phase_detail.eq(phase)]
        for method, reference in comparisons:
            delta = part[method]-part[reference]
            events = delta.groupby(part.event_id).mean()
            draws = rng.choice(events.to_numpy(), size=(5000, len(events)), replace=True).mean(axis=1)
            low, high = np.quantile(draws, [.025, .975])
            rows.append({"phase": phase, "comparison": f"{method} − {reference}", "events": len(events),
                         "forecast_rows": len(part), "pooled_delta_nwis": float(delta.mean()),
                         "equal_event_delta_nwis": float(events.mean()), "bootstrap_low": low, "bootstrap_high": high})
            event_rows.extend({"phase": phase, "comparison": f"{method} − {reference}",
                               "event_id": int(event), "delta_nwis": float(value)} for event, value in events.items())
    results = pd.DataFrame(rows)
    results.to_csv(output/"event_comparisons.csv", index=False)
    pd.DataFrame(event_rows).to_csv(output/"event_differences.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for ax, phase in zip(axes, phases):
        part = results[results.phase.eq(phase)]
        y = np.arange(len(part))
        ax.hlines(y, part.bootstrap_low, part.bootstrap_high, color="black", lw=1.5)
        ax.scatter(part.equal_event_delta_nwis, y, color="black", s=25)
        ax.axvline(0, color="grey", ls="--", lw=1)
        ax.set_yticks(y, part.comparison.str.replace("_day", "", regex=False))
        ax.set_title(phase.replace("_", " "))
        ax.set_xlabel("Paired event-mean Δ normalized WIS\nnegative favors the first method")
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.ticklabel_format(axis="x", style="sci", scilimits=(-3, 3))
        ax.grid(axis="x", alpha=.2)
    fig.suptitle("Development diagnostics: 8 events per slice; exploratory 95% event-bootstrap intervals")
    fig.savefig(output/"event_comparisons.png", dpi=180)
    fig.savefig(output/"event_comparisons.pdf")
    plt.close(fig)
    text = f"""# Event-level calibration diagnostics

These paired comparisons use the same forecast origins, targets, horizons and scheduled events. Each event contributes one mean difference, so the uncertainty calculation does not treat overlapping forecasts as independent samples. Negative values favor the first named method.

{markdown_table(results)}

![Event comparisons](event_comparisons.png)

Intervals are percentile bootstrap intervals from 5,000 resamples of eight event means per slice. They are exploratory and conditional on this one site, period and fault schedule. They assume events are exchangeable/independent enough for the resampling approximation; native outages, serial dependence and missing-event selection may violate that assumption. These intervals are not final-test inference, a cross-site result, or a multiplicity-adjusted claim. A small sample can also produce deceptively narrow intervals when methods behave similarly.

`pooled_delta_nwis` weights all eligible forecast rows equally; `equal_event_delta_nwis` weights events equally and is the plotted estimate. A difference between them reflects event-size weighting, not an inconsistency. Exact event differences and figure data are included in adjacent CSV files.

The table should guide development, not establish a winner. In particular, any benefit from signed/daylight calibration must be separated from additional recovery conditioning, and early gains must be checked against later recovery performance and coverage.
"""
    (output/"EVENT_DIAGNOSTICS.md").write_text(text)
    (output/"event_diagnostics_manifest.json").write_text(json.dumps({"source_forecast_sha256": digest(output/"forecasts.parquet"),
        "analysis_sha256": digest(__file__), "bootstrap_seed": 20260911, "replicates": 5000,
        "resampling_unit": "event mean within a fixed site and development slice"}, indent=2)+"\n")
    print(results.to_string(index=False))


if __name__ == "__main__":
    run()
