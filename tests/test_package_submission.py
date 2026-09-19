import json
from pathlib import Path
import zipfile

import pytest

from research.package_submission import checked_path, verify_claim_ledger, write_archive
from solar_recovery.pilot import digest


def test_archive_preserves_bytes_manifest_and_stable_order(tmp_path):
    workspace = tmp_path/"workspace"
    workspace.mkdir()
    (workspace/"a.txt").write_bytes(b"Evidence with exact bytes.\n")
    (workspace/"b.bin").write_bytes(bytes(range(256))*100)
    a = write_archive(tmp_path/"first.zip", workspace, ["b.bin", "a.txt"], "synthetic archive test")
    b = write_archive(tmp_path/"second.zip", workspace, ["a.txt", "b.bin"], "synthetic archive test")
    assert a["sha256"] == b["sha256"]
    assert a["all_entries_reopened_and_verified"]
    with zipfile.ZipFile(tmp_path/"first.zip") as archive:
        manifest = json.loads(archive.read("PACKAGE_MANIFEST.json"))
        assert manifest["files"]["a.txt"]["sha256"] == digest(workspace/"a.txt")
        assert archive.read("b.bin") == (workspace/"b.bin").read_bytes()
    with pytest.raises(FileExistsError):
        write_archive(tmp_path/"first.zip", workspace, ["a.txt"], "test")


def test_claim_checks_source_hash_unique_row_and_unrounded_values(tmp_path):
    source = tmp_path/"facts.csv"
    source.write_text("site,difference\nnist,-0.00123\ncolorado,0.00045\n")
    claim = {"id": "example", "statement": "Synthetic numerical check", "source_path": "facts.csv",
             "source_sha256": digest(source), "where": {"site": "nist"}, "values": {"difference": -.00123}}
    ledger = {"status": "reviewed against cited artifacts", "claims": [claim]}
    verify_claim_ledger(tmp_path, ledger)
    claim["values"]["difference"] = .00123
    with pytest.raises(ValueError, match="value mismatch"):
        verify_claim_ledger(tmp_path, ledger)
    claim["values"]["difference"] = -.00123
    source.write_text("site,difference\nnist,-0.002\n")
    with pytest.raises(ValueError, match="Changed claim source"):
        verify_claim_ledger(tmp_path, ledger)


def test_archive_sources_cannot_escape_workspace(tmp_path):
    workspace = tmp_path/"workspace"
    workspace.mkdir()
    (tmp_path/"outside.txt").write_text("outside")
    with pytest.raises(ValueError, match="out-of-workspace"):
        checked_path(workspace, "../outside.txt")
