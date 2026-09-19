"""Export reviewable LaTeX tables and exact claim inputs from verified evidence."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.pilot import digest

LABELS = {
    "raw": "Quantile HGB", "rolling": "Rolling calibration", "recency": "Recency calibration",
    "physical": "Physical context", "physical_availability": "Context + availability",
    "physical_recovery": "Context + recovery", "mask50": "50-slot mask blend",
    "aci_bounded": "Bounded adaptive alpha", "single_imputation": "Single imputation",
    "multiple_imputation": "Multiple imputation", "mi_recency": "MI + recency calibration",
    "persistence": "Persistence", "geometric_persistence": "Geometric persistence",
    "previous_day": "Previous day", "carry_forward": "Carry-forward quantiles",
}
CASE_LABELS = {
    "joint_gradual": "Reference joint-gradual", "no_input_age": "No explicit age",
    "no_block_augmentation": "No block augmentation", "privileged_labels": "Privileged labels (diagnostic)",
    "training_2015": "2015-trained weights", "cross_site_weights": "Other-site weights + local calibration",
}


def number(value, decimals=4):
    return "--" if not np.isfinite(value) else f"{value:.{decimals}f}"


def interval(row):
    return f"{number(row.difference*1000, 3)} [{number(row.ci_lower*1000, 3)}, {number(row.ci_upper*1000, 3)}]"


def table(path, caption, label, columns, header, rows, wide=False, note=""):
    environment = "table*" if wide else "table"
    lines = [f"\\begin{{{environment}}}[t]", "\\centering\\footnotesize", f"\\caption{{{caption}}}",
        f"\\label{{{label}}}", "\\setlength{\\tabcolsep}{4pt}", f"\\begin{{tabular}}{{{columns}}}",
        "\\hline", " & ".join(header)+r" \\", "\\hline"]
    lines += [" & ".join(row)+r" \\" for row in rows]
    lines += ["\\hline", "\\end{tabular}"]
    if note:
        lines += ["\\par\\smallskip", "\\begin{minipage}{"+("\\textwidth" if wide else "\\columnwidth")+"}\\scriptsize", note, "\\end{minipage}"]
    lines += [f"\\end{{{environment}}}"]
    path.write_text("\n".join(lines)+"\n")


def export(root, output):
    root, output = Path(root), Path(output)
    manifest = json.loads((root/"manifest.json").read_text())
    verification = json.loads((root/"verification.json").read_text())
    analysis = root/"analysis"
    analyzed = json.loads((analysis/"manifest.json").read_text())
    if manifest["status"] != "complete frozen evaluation" or not verification["status"].startswith("passed"):
        raise ValueError("Require completed, verified measured-data evaluation")
    if verification["manifest_sha256"] != digest(root/"manifest.json") or analyzed["source_manifest_sha256"] != digest(root/"manifest.json"):
        raise ValueError("Verification/analysis does not describe the current completed run")
    for name in ("Summary.csv", "Cells.csv", "Contrasts.csv", "Support.csv", "Diagnostics.csv"):
        if digest(analysis/name) != analyzed["files_sha256"][name]:
            raise ValueError(f"Changed analysis table: {name}")
    if output.exists():
        raise FileExistsError("Generated evidence tables are immutable; choose a new output version")
    output.mkdir(parents=True)
    summary = pd.read_csv(analysis/"Summary.csv")
    cells = pd.read_csv(analysis/"Cells.csv")
    contrasts = pd.read_csv(analysis/"Contrasts.csv")
    config = json.loads((root/"config.json").read_text())
    summary = summary.loc[summary.population.eq("recorded_ac")]
    cells = cells.loc[cells.population.eq("recorded_ac")]
    contrasts = contrasts.loc[contrasts.population.eq("recorded_ac") & contrasts.block_days.eq(7)]
    main = summary.loc[summary.endpoint.eq("failure_recovery")].set_index(["method", "site"])
    rows = []
    for method, label in LABELS.items():
        row = [label]
        for site in ("nist", "colorado"):
            point = main.loc[(method, site)]
            row += [number(point.nwis), number(point.coverage90*100, 1), number(point.nwidth90, 3)]
        rows.append(row)
    table(output/"main_table.tex", "Failure and recovery forecasting: equal primary-scenario/horizon means.",
        "tab:main", "lrrrrrr", ["Method", "NIST NWIS", "$C_{90}$ (\\%)", "$W_{90}/C$", "Colorado NWIS", "$C_{90}$ (\\%)", "$W_{90}/C$"], rows, True,
        "NWIS and width are normalized by DC capacity; lower NWIS is better. Coverage is empirical. Rows share identical observed daylight targets within each case. Counts and all horizon/phase cells are retained in the artifact; overlapping pairs are not independent samples.")
    primary = contrasts.loc[contrasts.pool.eq("faulted_primary") & contrasts.endpoint.isin(["recovery_0_6", "recovery_6_24"]) &
        contrasts.contrast.eq("physical_recovery_minus_physical_availability")]
    rows = []
    for site in ("nist", "colorado"):
        for phase, label in (("recovery_0_6", "0--6 h"), ("recovery_6_24", "6--24 h")):
            point = primary.loc[primary.site.eq(site) & primary.endpoint.eq(phase)].iloc[0]
            support = cells.loc[cells.site.eq(site) & cells.case_group.eq("primary") & cells.method.eq("raw") & cells.endpoint.eq(phase)]
            rows.append(["NIST" if site == "nist" else "Colorado", label, interval(point), str(int(support.events.min()))])
    table(output/"primary_table.tex", "Recovery minus availability: paired 95\\% calendar-block intervals.",
        "tab:primary", "llrl", ["Site", "Phase", "$10^3\\Delta$NWIS [95\\% CI]", "$E_{\\min}$"], rows, False,
        "Positive differences favor availability. The seven-day blocks retain common-weather scenarios. $E_{\\min}$ is the minimum number of distinct events in a case/horizon cell, not an independent sample count. Four main site/phase contrasts are disclosed together.")
    rows = []
    for case, label in CASE_LABELS.items():
        row = [label]
        for site in ("nist", "colorado"):
            point = contrasts.loc[contrasts.site.eq(site) & contrasts.pool.eq(case) & contrasts.endpoint.eq("recovery") &
                contrasts.contrast.eq("physical_recovery_minus_physical_availability")].iloc[0]
            row.append(interval(point))
        rows.append(row)
    table(output/"ablation_table.tex", "Recovery versus availability under the declared ablations and transfer checks.",
        "tab:ablations", "lrr", ["Joint-gradual case", "NIST $10^3\\Delta$NWIS [95\\% CI]", "Colorado $10^3\\Delta$NWIS [95\\% CI]"], rows, True,
        "Exploratory, unadjusted seven-day-block intervals for the combined 0--24 h recovery period. Privileged labels change information access and are not an operational comparator. Other-site weights use target metadata and local causal calibration. Complete duration, delay, seed, quality, alignment and stale-transport sensitivities remain in the supporting tables.")
    rows, facts = [], []
    for site in ("nist", "colorado"):
        clean = cells.loc[cells.site.eq(site) & cells.case_id.eq("clean") & cells.endpoint.eq("all")].groupby("method")["nwis"].mean()
        reference, candidate = float(clean["physical"]), float(clean["physical_recovery"])
        delta, tolerance = candidate-reference, max(.02*reference, .0001)
        point = contrasts.loc[contrasts.site.eq(site) & contrasts.pool.eq("clean") & contrasts.endpoint.eq("all") &
            contrasts.contrast.eq("physical_recovery_minus_physical")].iloc[0]
        rows.append(["NIST" if site == "nist" else "Colorado", number(reference), number(candidate), interval(point), "yes" if delta <= tolerance else "no"])
        ref, rec = main.loc[("physical", site)], main.loc[("physical_recovery", site)]
        facts.append({"site": site, "failure_recovery_physical_nwis": float(ref.nwis),
            "failure_recovery_recovery_nwis": float(rec.nwis), "relative_failure_recovery_difference": float((rec.nwis-ref.nwis)/ref.nwis),
            "signal_point_gate_5pct": bool(rec.nwis <= .95*ref.nwis), "clean_physical_nwis": reference,
            "clean_recovery_nwis": candidate, "clean_difference": delta, "clean_tolerance": tolerance,
            "clean_point_gate": bool(delta <= tolerance), "recovery_coverage90": float(rec.coverage90),
            "coverage90_diagnostic_within_5pp": bool(.85 <= rec.coverage90 <= .95)})
    table(output/"clean_table.tex", "Clean-data tradeoff against the fixed physical-context reference.",
        "tab:clean", "lrrrl", ["Site", "Physical NWIS", "Recovery NWIS", "$10^3\\Delta$NWIS [95\\% CI]", "Tolerance met?"], rows, True,
        "The point-estimate tolerance is an increase no greater than $\\max(0.02\\,\\mathrm{NWIS}_{physical},0.0001)$. Meeting it is not a coverage guarantee or acceptance criterion.")
    primary.to_csv(output/"primary_claim_rows.csv", index=False)
    pd.DataFrame(facts).to_csv(output/"engineering_gate_facts.csv", index=False)
    result = {"status": "exported verified table inputs; narrative interpretation requires review",
        "run": str(root), "code_sha256": digest(Path(__file__)),
        "source_sha256": {str(p.relative_to(root)): digest(p) for p in [root/"manifest.json", root/"verification.json", analysis/"manifest.json",
            analysis/"Summary.csv", analysis/"Cells.csv", analysis/"Contrasts.csv"]},
        "files_sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()},
        "primary_contrast": config["inference"]["primary_contrast"],
        "rounding": "NWIS 4 decimals, coverage percent 1 decimal, normalized width 3 decimals; contrast multiplied by 1000 and rounded to 3 decimals",
        "limits": "Point engineering gates and unadjusted fixed-site intervals do not certify deployment, novelty, conference acceptance or human review"}
    (output/"manifest.json").write_text(json.dumps(result, indent=2)+"\n")
    print(f"Exported four LaTeX tables and exact claim inputs to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--output", default="paper/generated")
    args = parser.parse_args()
    export(args.run, args.output)
