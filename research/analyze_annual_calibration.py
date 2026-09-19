"""Paired development analysis of matched annual calibration controls."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows

from research.analyze_annual_baselines import paired_events, table
from solar_recovery.pilot import digest


def analyze(root):
    root = Path(root)
    config = json.loads((root/"config.json").read_text())
    metrics = pd.read_csv(root/"metrics.csv")
    development = metrics.loc[metrics.period.eq("development_evaluation")]
    summary = development.groupby(["site", "phase", "method"])[["nwis", "coverage90", "nwidth90"]].mean().reset_index()
    event_rows, diagnostics = [], []
    for site in config["sites"]:
        for scenario in config["scenarios"]:
            scored = pd.read_parquet(root/site/f"forecasts_{scenario}.parquet")
            scored = scored.loc[scored.valid_target & scored.daylight & scored.within_period & scored.period.eq("development_evaluation")]
            eligible = scored.loc[scored.event_id.ge(0)]
            for left, right in (("physical_recovery", "physical"), ("physical", "recency"),
                                ("mask50", "recency"), ("aci_bounded", "rolling")):
                diff = paired_events(eligible.loc[eligible.method.eq(left)], eligible.loc[eligible.method.eq(right)], f"{left}_minus_{right}")
                diff["site"], diff["scenario"] = site, scenario
                event_rows.append(diff)
            diag = pd.read_parquet(root/site/f"diagnostics_{scenario}.parquet")
            joined = scored.merge(diag, on=["origin", "horizon", "method"], validate="one_to_one")
            joined["unsupported"] = joined.fallback.eq("insufficient_scores")
            statistics = joined.groupby(["site", "scenario", "phase", "method"])[["pool_size", "effective_n", "freshest_score_age_h", "nesting_repaired", "unsupported"]].mean().reset_index()
            diagnostics.append(statistics)
    differences = pd.concat(event_rows, ignore_index=True)
    diagnostic = pd.concat(diagnostics, ignore_index=True)
    rng, rows = np.random.default_rng(20260912), []
    for (site, scenario, phase, contrast), group in differences.groupby(["site", "scenario", "phase", "contrast"]):
        values = group.difference.to_numpy()
        distribution = rng.choice(values, (10000, len(values)), replace=True).mean(axis=1)
        lo, hi = np.quantile(distribution, [.025, .975])
        rows.append({"site": site, "scenario": scenario, "phase": phase, "contrast": contrast,
            "events": len(values), "mean_nwis_difference": values.mean(), "ci_lower": lo, "ci_upper": hi})
    contrasts = pd.DataFrame(rows)
    tables = {"PhaseSummary": summary, "PairedEvents": differences, "EventBootstrap": contrasts, "Diagnostics": diagnostic}
    for name, frame in tables.items():
        frame.to_csv(root/f"{name}.csv", index=False)
    workbook = Workbook()
    readme = workbook.active
    readme.title = "Readme"
    readme.append(["Run", str(root)])
    readme.append(["Scope", "2016 development; fixed calibration parameters; only evaluated scenarios"])
    readme.append(["Bootstrap", "10000 paired event resamples, seed 20260912, per site/scenario/phase; exploratory unadjusted intervals"])
    readme.append(["Weighting", "Equal horizon/scenario cells in phase summary; equal event means in bootstrap"])
    readme.append(["Interpretation", "Recovery key also groups age/missing fractions. An availability-only grouping ablation remains useful."])
    readme.append(["Guarantees", "Empirical weighted/rolling rules, finite quantile caps, nesting repairs and bounded ACI; no formal coverage claim"])
    for name, frame in tables.items():
        sheet = workbook.create_sheet(name)
        for row in dataframe_to_rows(frame, index=False, header=True):
            sheet.append([None if isinstance(v, float) and not np.isfinite(v) else v for v in row])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    workbook.save(root/"Calibration_Development_Evidence.xlsx")
    saved = load_workbook(root/"Calibration_Development_Evidence.xlsx", read_only=True)
    assert saved["EventBootstrap"].max_row == len(contrasts)+1
    saved.close()
    focus = contrasts.loc[contrasts.contrast.eq("physical_recovery_minus_physical") & contrasts.phase.isin(["recovery_0_6", "recovery_6_24"])]
    fig, axes = plt.subplots(1, len(config["sites"]), figsize=(9, 4), constrained_layout=True, squeeze=False)
    for ax, site in zip(axes[0], config["sites"]):
        part = focus.loc[focus.site.eq(site)].set_index("phase").reindex(["recovery_0_6", "recovery_6_24"])
        x = part.mean_nwis_difference.to_numpy()
        ax.errorbar([0, 1], x, yerr=np.maximum(0., np.vstack([x-part.ci_lower, part.ci_upper-x])), fmt="o", capsize=4)
        ax.axhline(0., color="gray", linestyle="--")
        ax.set(xticks=[0, 1], xticklabels=["0–6 h", "6–24 h"], title=site.upper() if site == "nist" else site.title(),
               xlabel="Time after full live restoration", ylabel="Recovery blend minus physical context: NWIS")
    fig.suptitle("Gradual joint backfill: paired event differences (development)")
    for extension in ("png", "pdf"):
        fig.savefig(root/f"matched_recovery_comparison.{extension}", dpi=200)
    plt.close(fig)
    early = summary.loc[summary.phase.eq("recovery_0_6") & summary.method.isin(["raw", "recency", "physical", "physical_recovery"])]
    text = """# Matched annual calibration findings

This experiment uses the same validation-selected quantile forecasts for all calibration methods, with fixed common window/recency settings. Physical context excludes explicit recovery age. The candidate adds a blend toward matching coarse recovery states; those states also include age/missing-fraction bins. These are empirical controls, not a reproduction of the full published CACP or mask-conditional algorithms.

## Early recovery

The table averages horizon cells within the first six hours after full live restoration, for the gradual joint-backfill scenario, on July–December 2016 development data. Coverage is a fraction for nominal 90% intervals.

"""+table(early[["site", "method", "nwis", "coverage90", "nwidth90"]], 6)+"""

## Incremental recovery contribution

The paired comparison subtracts physical-context NWIS from the recovery blend on the same forecasts, then averages within events. Negative values favor the recovery blend. Percentile intervals resample event means 10,000 times within site/scenario/phase (seed 20260912). They are exploratory, unadjusted for multiple comparisons and conditional on these sites and this schedule; they are not a population-wide guarantee.

"""+table(focus[["site", "phase", "events", "mean_nwis_difference", "ci_lower", "ci_upper"]], 6)+"""

![Matched recovery comparison](matched_recovery_comparison.png)

The small, mixed differences do not establish a recovery-specific improvement. Generic empirical calibration improves several raw-interval diagnostics, but performance and coverage remain phase/site dependent. Do not replace this conclusion with a comparison only against raw forecasts. Availability-only grouping, calibration-parameter and delivery sensitivities remain necessary before the final protocol is frozen.

Full phase results, additional method contrasts and score-pool/repair diagnostics are in the CSV files and `Calibration_Development_Evidence.xlsx`. Diagnostic means use the same eligible daylight, valid-target development forecasts as performance summaries. The independent verifier checks immutable base/median agreement, target/score consistency, sampled interval repairs and expected receipt-gated update counts. The unit suite also tests prefix invariance under changed future labels.

This is development evidence. Reserved 2017 forecast performance has not been examined. See [the closest-method crosswalk](../../research/CLOSEST_METHOD_CROSSWALK.md) and [the annual protocol](../../research/ANNUAL_DEVELOPMENT_PROTOCOL.md) for implementation differences and limitations.
"""
    (root/"FINDINGS.md").write_text(text)
    (root/"analysis_manifest.json").write_text(json.dumps({"analyzer_sha256": digest(__file__), "helper_sha256": digest("research/analyze_annual_baselines.py"),
        "run_manifest_sha256": digest(root/"manifest.json"), "bootstrap_replicates": 10000, "seed": 20260912}, indent=2)+"\n")
    print(table(focus[["site", "phase", "events", "mean_nwis_difference", "ci_lower", "ci_upper"]], 6), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    analyze(args.run)
