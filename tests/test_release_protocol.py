import copy
import json
from pathlib import Path

import pytest

from research.release_protocol import derive, validate_release_view, verification_protocol
from solar_recovery.pilot import digest


def test_public_view_preserves_scientific_dependencies_and_private_freeze(tmp_path):
    parent_path = Path("research/FINAL_PROTOCOL_LOCK.json")
    before = digest(parent_path)
    output = tmp_path/"release.json"
    derive(parent_path, output)
    parent, view = json.loads(parent_path.read_text()), json.loads(output.read_text())
    validate_release_view(view, parent)
    assert len(view["files_sha256"]) == len(parent["files_sha256"])-1
    assert digest(parent_path) == before
    altered = copy.deepcopy(view)
    altered["files_sha256"]["solar_recovery/replay.py"] = "0"*64
    with pytest.raises(ValueError, match="scientific dependency"):
        validate_release_view(altered, parent)
    altered = copy.deepcopy(view)
    altered["site_case_count"] = 1
    with pytest.raises(ValueError, match="frozen field"):
        validate_release_view(altered, parent)
    frozen, provenance = verification_protocol("configs/final_evaluation_v4.json", parent_path, output)
    assert frozen == parent
    private_present = Path("Solar_Forecasting_Research_PRD.docx").is_file()
    assert provenance["private_prd_bytes_verified"] == private_present
    assert provenance["scientific_dependencies_verified"] == 82
    if private_present:
        original, original_provenance = verification_protocol("configs/final_evaluation_v4.json", parent_path)
        assert original == parent and original_provenance["private_prd_bytes_verified"]
    else:
        with pytest.raises(FileNotFoundError):
            verification_protocol("configs/final_evaluation_v4.json", parent_path)
