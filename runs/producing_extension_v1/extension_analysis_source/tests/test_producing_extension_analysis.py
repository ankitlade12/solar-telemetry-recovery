"""Exercise table, bootstrap, plotting and workbook paths with synthetic scores."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.analyze_producing_extension import INTERRUPTION_CASES, analyze, reproduce_tables
from solar_recovery.pilot import digest


def test_extension_analysis_artifacts_on_synthetic_single_site_grid(tmp_path):
    config = json.loads(Path("configs/final_evaluation_v4.json").read_text())
    config["sites"] = ["reserve10"]
    config["cases"] = [c for c in config["cases"] if c["id"] in INTERRUPTION_CASES]
    config.update(evaluation_start="2017-02-01T04:00Z", evaluation_end="2017-03-01T00:00Z")
    config["inference"]["bootstrap_replicates"] = 50
    (tmp_path/"config.json").write_text(json.dumps(config))
    (tmp_path/"manifest.json").write_text(json.dumps({"status": "complete frozen evaluation", "data_kind": "synthetic analysis test only"}))
    origins = pd.date_range("2017-02-01T04:01Z", "2017-02-28T20:01Z", freq="8h")
    for site in config["sites"]:
        root = tmp_path/site
        root.mkdir()
        (root/"contract_primary.json").write_text(json.dumps({"capacity_kw_dc": 10.}))
        for case in config["cases"]:
            rows, diagnostics = [], []
            for i, origin in enumerate(origins):
                phase = "normal" if case["id"] == "clean" else ["outage", "recovery_0_6", "recovery_6_24"][i % 3]
                if case["id"] in ("pv_only", "irradiance_only") and phase == "outage":
                    phase = "partial_restoration"
                for h in (1, 4):
                    for method in config["primary_methods"]:
                        rows.append({"site": site, "case_id": case["id"], "case_group": "primary", "origin": origin,
                            "horizon": h, "method": method, "valid_target": True, "daylight": True,
                            "within_period": True, "period": "evaluation", "phase": phase,
                            "zero_with_bright_poa": False, "nwis": .1, "nmae": .1,
                            "coverage50": .5, "coverage80": .8, "coverage90": .9, "nwidth90": .3,
                            "event_id": -1 if case["id"] == "clean" else i//3,
                            "recovery_hour": 2. if phase == "recovery_0_6" else 10. if phase == "recovery_6_24" else np.nan})
                        if method != "raw":
                            diagnostics.append({"origin": origin, "horizon": h, "method": method,
                                "fallback": "none", "pool_size": 100, "effective_n": 80.,
                                "label_updates_at_origin_all_horizons": 2,
                                "freshest_score_age_h": float(h), "nesting_repaired": False})
            pd.DataFrame(rows).to_parquet(root/f"forecasts_{case['id']}.parquet", index=False)
            pd.DataFrame(diagnostics).to_parquet(root/f"diagnostics_{case['id']}.parquet", index=False)
    (tmp_path/"extension_context.json").write_text(json.dumps({"original_parent_authenticated": True, "data_kind": "synthetic fixture, no real parent authentication claim"}))
    (tmp_path/"verification.json").write_text(json.dumps({"status": "passed synthetic fixture",
        "manifest_sha256": digest(tmp_path/"manifest.json"),
        "files_sha256": {str(p.relative_to(tmp_path)): digest(p) for p in tmp_path.rglob("*")
            if p.is_file() and "analysis" not in p.relative_to(tmp_path).parts}}))
    analyze(tmp_path)
    output = tmp_path/"analysis"
    result = json.loads((output/"manifest.json").read_text())
    assert result["status"] == "complete analysis"
    assert result["tables"]["UpdateActivity"] > 0
    interruption = pd.read_csv(output/"InterruptionComparison.csv")
    for _, part in interruption.groupby(["site", "population", "horizon"]):
        assert set(part.case_id) == INTERRUPTION_CASES
        assert part.n.nunique() == 1
        assert part.events.nunique() == 1
        assert part.n.iloc[0] < len(origins)
    contrasts = pd.read_csv(output/"Contrasts.csv")
    assert np.allclose(contrasts.loc[contrasts.supported, "difference"], 0.)
    assert (output/"Final_Evaluation_Evidence.xlsx").exists()
    assert len(list((output/"figures").glob("*.pdf"))) == 3
    before = digest(output/"manifest.json")
    replicate = tmp_path/"reproduced_tables"
    reproduce_tables(tmp_path, replicate)
    comparison = json.loads((replicate/"reproduction_comparison.json").read_text())
    assert len(comparison["comparisons"]) == 8
    assert all(item["matched"] for item in comparison["comparisons"].values())
    assert digest(output/"manifest.json") == before
    with pytest.raises(FileExistsError):
        reproduce_tables(tmp_path, replicate)
    (tmp_path/"config.json").write_text((tmp_path/"config.json").read_text()+"\n")
    with pytest.raises(ValueError, match="Changed source artifact"):
        reproduce_tables(tmp_path, tmp_path/"changed_reproduction")
