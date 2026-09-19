"""Test inclusion/exclusion only; real archive closure is checked after staging."""
import json
from pathlib import Path

import pytest

from research.package_public_release import candidate_files


def test_public_candidate_omits_private_specification_and_copied_papers(tmp_path):
    parent = json.loads(Path("research/FINAL_PROTOCOL_LOCK.json").read_text())
    view = json.loads(Path("release/DEPENDENCY_LOCK.json").read_text())
    mandatory = set(view["files_sha256"]) | {
        "research/FINAL_PROTOCOL_LOCK.json", "research/ANNUAL_DEVELOPMENT_PROTOCOL.md",
        "research/WIND_QUANTILE_CROSSWALK.md", "research/POST_FREEZE_ANALYSIS_LOG.md", "research/hardware.json",
        "research/FINAL_FINDINGS.md", "research/PRD_TRACEABILITY.md", "research/FINAL_PERFORMANCE_EXPOSURE.json",
        "MODEL_CARD.md", "DATA_AVAILABILITY.md", "pyproject.toml", "requirements-pilot.txt",
        "paper/build/manuscript.pdf", "paper/build/final_audit.json", "paper/build/visual_review.json",
        "runs/example/analysis/Summary.csv", "Solar_Forecasting_Research_PRD.docx", "research/sources/copied.pdf",
        "runs/final_evidence_exports_v1/status.json",
        "runs/final_evidence_exports_v1/reproduced_tables/reproduction_comparison.json",
        "runs/final_evidence_exports_v1/analyze_final_evaluation.log"}
    for name in mandatory:
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic file-selection placeholder; not scientific evidence.\n")
    (tmp_path/"research/FINAL_PROTOCOL_LOCK.json").write_text(json.dumps(parent))
    (tmp_path/"release").mkdir()
    (tmp_path/"release/DEPENDENCY_LOCK.json").write_text(json.dumps(view))
    ledger = tmp_path/"paper/claim_evidence.json"
    ledger.write_text(json.dumps({"claims": [{"source_path": "runs/example/analysis/Summary.csv"}]}))
    files = candidate_files(tmp_path, "runs/example")
    assert set(view["files_sha256"]).issubset(files)
    assert "runs/example/analysis/Summary.csv" in files
    assert "runs/final_evidence_exports_v1/status.json" in files
    assert "runs/final_evidence_exports_v1/reproduced_tables/reproduction_comparison.json" in files
    assert "runs/final_evidence_exports_v1/analyze_final_evaluation.log" not in files
    assert "Solar_Forecasting_Research_PRD.docx" not in files
    assert not any(name.startswith("research/sources/") for name in files)
    ledger.write_text(json.dumps({"claims": [{"source_path": "./research/sources/copied.pdf"}]}))
    with pytest.raises(ValueError, match="copied external papers"):
        candidate_files(tmp_path, "runs/example")
