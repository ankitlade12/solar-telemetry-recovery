"""Connect the final review manuscript's empirical numbers to verified CSV rows."""
import json
from pathlib import Path

import pandas as pd

from research.package_submission import verify_claim_ledger
from solar_recovery.pilot import digest


def prepare():
    run = Path("runs/final_2017_v4")
    analysis = run/"analysis"
    latency = Path("runs/inference_benchmark_v1")
    output = Path("paper/claim_sources")
    ledger_path = Path("paper/claim_evidence.json")
    if output.exists() or ledger_path.exists():
        raise FileExistsError("Claim sources and reviewed ledgers are immutable")
    manifests = {folder: json.loads((folder/"manifest.json").read_text()) for folder in (run, analysis, latency)}
    verification = json.loads((run/"verification.json").read_text())
    assert verification["status"] == "passed automated final verification"
    assert verification["manifest_sha256"] == digest(run/"manifest.json")
    for folder in (analysis, latency):
        for name, checksum in manifests[folder]["files_sha256"].items():
            assert digest(folder/name) == checksum, f"Changed source: {folder/name}"
    config = json.loads((run/"config.json").read_text())
    summary = pd.read_csv(analysis/"Summary.csv")
    contrasts = pd.read_csv(analysis/"Contrasts.csv")
    support = pd.read_csv(analysis/"Support.csv")
    diagnostics = pd.read_csv(analysis/"Diagnostics.csv")
    cells = pd.read_csv(analysis/"Cells.csv")
    timing = pd.read_csv(latency/"summary.csv")
    output.mkdir()
    design = {"run": run.name, "sites": len(config["sites"]), "completed_site_cases": len(manifests[run]["cases"]),
        "primary_scenarios": sum(c["group"] == "primary" for c in config["cases"]),
        "sensitivity_scenarios": sum(c["group"] != "primary" for c in config["cases"]),
        "primary_outputs": int(summary.method.nunique()), "horizons": len(config["horizons"]),
        "forecast_records": verification["forecasts"], "direct_history_slot_checks": verification["receipt_slots_checked"],
        "bootstrap_replicates": config["inference"]["bootstrap_replicates"]}
    pd.DataFrame([design]).to_csv(output/"design.csv", index=False)
    selected = support.loc[support.population.eq("recorded_ac") & support.case_group.eq("primary") &
        ~support.case_id.eq("clean") & support.endpoint.isin(["recovery_0_6", "recovery_6_24"])]
    support_facts = selected.groupby(["site", "endpoint"]).agg(cells=("n", "size"),
        pairs_min=("n", "min"), pairs_max=("n", "max"), pairs_sum=("n", "sum"),
        events_min=("events", "min"), events_max=("events", "max"),
        low_pair_support_cells=("low_case_support", "sum"), low_event_support_cells=("low_event_support", "sum")).reset_index()
    for index, row in support_facts.iterrows():
        diag = diagnostics.loc[diagnostics.site.eq(row.site) & diagnostics.case_group.eq("primary") &
            diagnostics.method.eq("physical_recovery") & diagnostics.phase.eq(row.endpoint)]
        support_facts.loc[index, "max_insufficient_score_fraction"] = diag.fallback_fraction.max()
    support_facts.to_csv(output/"support.csv", index=False)
    ambiguity = []
    for site in config["sites"]:
        part = cells.loc[cells.site.eq(site) & cells.case_group.eq("primary") & cells.endpoint.eq("failure_recovery")]
        a = part.loc[part.population.eq("recorded_ac")].set_index(["case_id", "method", "horizon"]).sort_index()
        b = part.loc[part.population.eq("exclude_bright_zero")].set_index(["case_id", "method", "horizon"]).sort_index()
        assert a.index.equals(b.index)
        ambiguity.append({"site": site, "compared_cells": len(a), "same_pair_counts": bool(a.n.equals(b.n)),
            "maximum_removed_pairs_per_cell": int((a.n-b.n).max())})
    pd.DataFrame(ambiguity).to_csv(output/"ambiguity.csv", index=False)
    cost = {"benchmark": latency.name, "workloads": len(timing), "calls": int(timing.calls.sum()),
        "calls_per_workload_min": int(timing.calls.min()), "calls_per_workload_max": int(timing.calls.max()),
        "median_ms_min": timing.median_ms.min(), "median_ms_max": timing.median_ms.max(),
        "p95_ms_min": timing.p95_ms.min(), "p95_ms_max": timing.p95_ms.max(),
        "maximum_call_ms": timing.maximum_ms.max(), "all_workload_p95_under_one_second": bool(timing.p95_under_one_second.all()),
        "benchmark_peak_rss_bytes": manifests[latency]["benchmark_process_peak_rss_bytes"],
        "benchmark_peak_rss_mib": manifests[latency]["benchmark_process_peak_rss_bytes"]/2**20,
        "installed_memory_gib": manifests[latency]["hardware"]["installed_memory_gib"]}
    pd.DataFrame([cost]).to_csv(output/"cost.csv", index=False)
    claims = []

    def add(path, frame, keys, measures, label):
        for i, row in enumerate(frame.to_dict("records")):
            claims.append({"id": f"{label}_{i+1}", "statement": label.replace("_", " ")+": "+
                ", ".join(f"{k}={row[k]}" for k in keys), "source_path": str(path), "source_sha256": digest(path),
                "where": {k: row[k] for k in keys}, "values": {k: row[k] for k in measures}})

    main = summary.loc[summary.population.eq("recorded_ac") & summary.endpoint.eq("failure_recovery")]
    add(analysis/"Summary.csv", main, ["site", "population", "endpoint", "method"],
        ["nwis", "coverage90", "nwidth90", "forecast_target_pairs", "strata"], "main_method_table")
    chosen = contrasts.population.eq("recorded_ac") & ((contrasts.pool.eq("faulted_primary") &
        contrasts.endpoint.isin(["recovery_0_6", "recovery_6_24"]) &
        contrasts.contrast.eq("physical_recovery_minus_physical_availability")) |
        (~contrasts.pool.eq("faulted_primary") & contrasts.endpoint.eq("recovery") & contrasts.block_days.eq(7) &
        contrasts.contrast.eq("physical_recovery_minus_physical_availability")) |
        (contrasts.pool.eq("clean") & contrasts.block_days.eq(7) & contrasts.contrast.eq("physical_recovery_minus_physical")))
    add(analysis/"Contrasts.csv", contrasts.loc[chosen], ["site", "population", "pool", "endpoint", "contrast", "block_days"],
        ["difference", "ci_lower", "ci_upper", "relative_difference", "strata", "paired_rows", "rejected_fraction"], "paired_effect")
    interrupted = pd.read_csv(analysis/"InterruptionComparison.csv")
    add(analysis/"InterruptionComparison.csv", interrupted.loc[interrupted.population.eq("recorded_ac")],
        ["site", "population", "case_id", "horizon", "method"], ["nwis", "coverage90", "n", "events"], "interruption_figure")
    diag = diagnostics.loc[diagnostics.case_id.eq("joint_gradual") & diagnostics.phase.eq("recovery_0_6") & diagnostics.method.eq("physical_recovery")]
    add(analysis/"Diagnostics.csv", diag, ["site", "case_id", "phase", "method"],
        ["n", "fallback_fraction", "global_fallback_fraction"], "early_matching_fallback")
    gates = Path("paper/generated/engineering_gate_facts.csv")
    gate_frame = pd.read_csv(gates)
    add(gates, gate_frame, ["site"], [c for c in gate_frame if c != "site"], "engineering_gates")
    add(latency/"summary.csv", timing, ["site", "case_id", "mode", "synthetic_pool_per_horizon"],
        ["calls", "median_ms", "p95_ms", "maximum_ms", "p95_under_one_second"], "latency_workload")
    for filename, keys in [("design.csv", ["run"]), ("support.csv", ["site", "endpoint"]),
                           ("ambiguity.csv", ["site"]), ("cost.csv", ["benchmark"])]:
        frame = pd.read_csv(output/filename)
        add(output/filename, frame, keys, [c for c in frame if c not in keys], filename.replace(".csv", "_facts"))
    source_paths = [run/"manifest.json", run/"config.json", run/"verification.json", analysis/"manifest.json",
        analysis/"Support.csv", analysis/"Diagnostics.csv", analysis/"Cells.csv", latency/"manifest.json", latency/"summary.csv"]
    provenance = {"generator_sha256": digest(Path(__file__)),
        "sources_sha256": {str(p): digest(p) for p in source_paths},
        "derivations": {"design": "Counts from completed config, verification and method summary",
            "support": "Per-site/window extrema and sums over recorded-AC primary faulted cells; diagnostic maximum separately",
            "ambiguity": "Matched primary failure/recovery cell counts before/after the declared scoring exclusion",
            "cost": "Extrema and call sums across all sixteen measured workloads; memory from benchmark manifest"}}
    (output/"provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False)+"\n")
    ledger = {"status": "reviewed against cited artifacts", "reviewer": "Codex source-row and numerical consistency review; human scientific review pending",
        "scope": "Empirical numbers in manuscript tables, abstract, findings narrative and figures; protocol settings trace to the original frozen sources",
        "claims": claims, "derivation_record": str(output/"provenance.json"),
        "protocol_sources_sha256": {str(p): digest(p) for p in [Path("research/FINAL_PROTOCOL_LOCK.json"),
            Path("research/FINAL_EVALUATION_PROTOCOL.md"), run/"config.json", run/"nist/contract_primary.json", run/"colorado/contract_primary.json"]},
        "figure_sources": [{"figure": str(p), "sha256": digest(p)} for p in sorted((analysis/"figures").glob("*.pdf"))],
        "limits": "Exact row checks do not prove interpretation, external validity, author consent or independent human reproduction"}
    verify_claim_ledger(Path.cwd(), ledger)
    ledger_path.write_text(json.dumps(ledger, indent=2, allow_nan=False)+"\n")
    print(f"Verified {len(claims)} source-row claims and wrote {ledger_path}")


if __name__ == "__main__":
    prepare()
