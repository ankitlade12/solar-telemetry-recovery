"""Check scientific table selection/units using explicitly synthetic summaries."""
import json

import pandas as pd
import pytest

from research.export_paper_tables import CASE_LABELS, LABELS, export
from solar_recovery.pilot import digest


def test_table_export_preserves_contrast_sign_units_and_exact_gate_values(tmp_path):
    run, output = tmp_path/"synthetic_run", tmp_path/"tables"
    analysis = run/"analysis"
    analysis.mkdir(parents=True)
    manifest = run/"manifest.json"
    manifest.write_text(json.dumps({"status": "complete frozen evaluation", "data_kind": "synthetic test only"}))
    (run/"verification.json").write_text(json.dumps({"status": "passed synthetic fixture", "manifest_sha256": digest(manifest)}))
    (run/"config.json").write_text(json.dumps({"inference": {"primary_contrast": "physical_recovery_minus_physical_availability"}}))
    summary, cells, contrasts = [], [], []
    for site in ("nist", "colorado"):
        for method in LABELS:
            summary.append({"site": site, "method": method, "population": "recorded_ac", "endpoint": "failure_recovery",
                            "nwis": .094 if method == "physical_recovery" else .1,
                            "coverage90": .9, "nwidth90": .3})
            for horizon in (1, 4):
                cells.append({"site": site, "method": method, "population": "recorded_ac", "case_id": "clean",
                              "case_group": "primary", "endpoint": "all", "horizon": horizon,
                              "nwis": .1005 if method == "physical_recovery" else .1, "events": 0})
        for phase in ("recovery_0_6", "recovery_6_24"):
            for horizon, events in ((1, 32), (4, 31)):
                cells.append({"site": site, "method": "raw", "population": "recorded_ac", "case_id": "joint_gradual",
                              "case_group": "primary", "endpoint": phase, "horizon": horizon, "nwis": .1, "events": events})
            contrasts.append({"site": site, "population": "recorded_ac", "block_days": 7, "pool": "faulted_primary",
                              "endpoint": phase, "contrast": "physical_recovery_minus_physical_availability",
                              "difference": -.001234, "ci_lower": -.002, "ci_upper": .0005})
        for case in CASE_LABELS:
            contrasts.append({"site": site, "population": "recorded_ac", "block_days": 7, "pool": case,
                              "endpoint": "recovery", "contrast": "physical_recovery_minus_physical_availability",
                              "difference": -.001, "ci_lower": -.002, "ci_upper": .0005})
        contrasts.append({"site": site, "population": "recorded_ac", "block_days": 7, "pool": "clean", "endpoint": "all",
                          "contrast": "physical_recovery_minus_physical", "difference": .0005, "ci_lower": -.001, "ci_upper": .002})
    for name, records in (("Summary", summary), ("Cells", cells), ("Contrasts", contrasts),
                          ("Support", [{"synthetic": True}]), ("Diagnostics", [{"synthetic": True}])):
        pd.DataFrame(records).to_csv(analysis/f"{name}.csv", index=False)
    (analysis/"manifest.json").write_text(json.dumps({"source_manifest_sha256": digest(manifest),
        "files_sha256": {path.name: digest(path) for path in analysis.glob("*.csv")}}))
    export(run, output)
    assert len(list(output.glob("*.tex"))) == 4
    primary = pd.read_csv(output/"primary_claim_rows.csv")
    assert len(primary) == 4
    assert primary.difference.eq(-.001234).all()
    assert "-1.234 [-2.000, 0.500]" in (output/"primary_table.tex").read_text()
    assert "31" in (output/"primary_table.tex").read_text()
    facts = pd.read_csv(output/"engineering_gate_facts.csv")
    assert facts.signal_point_gate_5pct.all() and facts.clean_point_gate.all()
    assert facts.relative_failure_recovery_difference.to_numpy() == pytest.approx([-.06, -.06])
    assert facts.clean_difference.to_numpy() == pytest.approx([.0005, .0005])
    for label in LABELS.values():
        assert label in (output/"main_table.tex").read_text()
    with pytest.raises(FileExistsError):
        export(run, output)
    (analysis/"Summary.csv").write_text("changed evidence\n")
    with pytest.raises(ValueError, match="Changed analysis table"):
        export(run, tmp_path/"changed_tables")
