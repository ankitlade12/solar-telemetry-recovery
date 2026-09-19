"""Post-run diagnostics; never changes forecasts or their evaluator truth."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from solar_recovery.pilot import digest
from solar_recovery.report import markdown_table


def run():
    output = Path("runs/nist_2015_daytime_probe_v1")
    source = output/"forecasts.parquet"
    clean_path = Path("runs/nist_2015_pilot_v1/forecasts_clean.parquet")
    frame, clean = pd.read_parquet(source), pd.read_parquet(clean_path)
    eligible = frame[frame.valid_target & frame.daylight & frame.within_split & frame.split.eq("development_evaluation")].copy()
    quantiles = [f"q{q:02d}" for q in (5, 10, 25, 50, 75, 90, 95)]
    base = ["base_"+q for q in quantiles]
    eligible["nonzero_correction"] = np.any(abs(eligible[quantiles].to_numpy()-eligible[base].to_numpy()) > 1e-9, axis=1)
    support = eligible.groupby(["phase", "method"]).agg(n=("nwis", "size"),
        nonzero_corrections=("nonzero_correction", "sum"), median_pool=("pool_size", "median"),
        median_matching_pool=("matching_size", "median"), nwis=("nwis", "mean")).reset_index()
    support.to_csv(output/"calibration_support.csv", index=False)
    paired = eligible.merge(clean[["origin", "horizon", "method", "nwis"]].rename(columns={"nwis": "clean_nwis"}),
                             on=["origin", "horizon", "method"], validate="one_to_one")
    assert len(paired) == len(eligible)
    paired["excess_nwis"] = paired.nwis-paired.clean_nwis
    curve = paired[paired.phase.eq("recovery")].groupby(["recovery_hour", "method"]).agg(
        excess_nwis=("excess_nwis", "mean"), n=("nwis", "size"), events=("event_id", "nunique")).reset_index()
    curve.to_csv(output/"paired_recovery_curve.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    for method in ["quantile_raw", "rolling", "context", "recovery"]:
        part = curve[curve.method.eq(method)].set_index("recovery_hour").reindex(range(24))
        ax.plot(part.index, part.excess_nwis, marker=".", label=method)
    ax.axhline(0, color="grey", lw=.8)
    ax.set(xlabel="Hours after scheduled full restoration", ylabel="Excess normalized WIS over clean delivery",
           title="Daytime restoration: matched origin, horizon and method")
    ax.grid(alpha=.2)
    ax.legend(fontsize=8)
    fig.savefig(output/"paired_recovery_curve.png", dpi=180)
    fig.savefig(output/"paired_recovery_curve.pdf")
    plt.close(fig)
    selected = support[support.phase.eq("recovery")]
    n_recovery = int(selected[selected.method.eq("recovery")].nonzero_corrections.iloc[0])
    count = int(selected[selected.method.eq("recovery")].n.iloc[0])
    text = f"""# Daytime recovery diagnostics

The recovery-conditioned calibrator makes **{n_recovery} nonzero interval corrections across {count} scorable daylight recovery forecasts** in the development period. Its unchanged output is a substantive finding about this implementation and setting, not a demonstrated benefit. Base intervals are already broad, and this implementation cannot shrink them. Available calibration history is not the same as adequate state-matched support.

{markdown_table(selected)}

![Paired recovery diagnostic](paired_recovery_curve.png)

Each point subtracts clean-delivery WIS from the degraded-delivery WIS for the same origin, horizon and method. Gaps indicate no eligible daylight targets for that recovery hour. This pairing removes the direct confounding from comparing different target hours in an absolute-WIS curve; selection due to missing targets and changing sample counts remains. Lines overlap where forecasts coincide. No confidence intervals or significance claims are made.

The rolling and recovery variants have not demonstrated an advantage in this pilot. The next methodological step is to examine over-wide base intervals, daytime-matched calibration, bidirectional interval adjustment with coherent quantile nesting, and state-support shrinkage, using development data only. Better target completeness, stronger baselines and independent evaluation are still required before any paper claim.

These are post-run diagnostics. The source forecast files are unchanged; `diagnostics_manifest.json` records their hashes and the analysis script hash. Run `python3 -m research.analyze_daytime_probe` to reproduce.
"""
    (output/"DIAGNOSTICS.md").write_text(text)
    (output/"diagnostics_manifest.json").write_text(json.dumps({"forecast_sha256": digest(source),
        "clean_forecast_sha256": digest(clean_path), "analysis_code_sha256": digest(__file__),
        "joined_forecast_count": len(paired), "status": "post-run exploratory diagnostics"}, indent=2)+"\n")
    print(f"Paired daytime diagnostics saved to {output}")


if __name__ == "__main__":
    run()
