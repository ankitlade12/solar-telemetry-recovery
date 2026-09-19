"""Build local review bundles only after evidence and final-PDF gates pass.

No network, upload, submission, registration or licensing action is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from solar_recovery.pilot import digest


def checked_path(workspace, value):
    candidate = (workspace/value).resolve()
    if not candidate.is_relative_to(workspace.resolve()) or not candidate.is_file():
        raise ValueError(f"Missing or out-of-workspace artifact: {value}")
    return candidate


def verify_claim_ledger(workspace, ledger):
    if ledger.get("status") != "reviewed against cited artifacts" or not ledger.get("claims"):
        raise ValueError("Require an evidence-reviewed claim ledger")
    for claim in ledger["claims"]:
        source = checked_path(workspace, claim["source_path"])
        if digest(source) != claim["source_sha256"]:
            raise ValueError(f"Changed claim source: {claim['id']}")
        if not claim.get("statement") or not claim.get("values") or not claim.get("where"):
            raise ValueError("Each quantitative claim needs a statement, unique row selector and values")
        data = pd.read_csv(source)
        for column, value in claim["where"].items():
            data = data.loc[data[column].eq(value)]
        if len(data) != 1:
            raise ValueError(f"Ambiguous or absent claim row: {claim['id']}")
        for column, expected in claim["values"].items():
            actual = data.iloc[0][column]
            equal = np.isclose(actual, expected, rtol=1e-12, atol=1e-12) if isinstance(expected, (float, int)) and not isinstance(expected, bool) else actual == expected
            if not equal:
                raise ValueError(f"Claim value mismatch: {claim['id']}/{column}")


def write_archive(path, workspace, files, kind):
    """Stable paths/timestamps; stream data and independently reopen every entry."""
    records = {}
    if path.exists():
        raise FileExistsError("Never overwrite a release archive")
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for relative in sorted(set(str(p) for p in files)):
            source = checked_path(workspace, relative)
            canonical = source.relative_to(workspace.resolve()).as_posix()
            if canonical in records or canonical == "PACKAGE_MANIFEST.json":
                raise ValueError(f"Duplicate or reserved archive path: {canonical}")
            info = zipfile.ZipInfo(canonical, date_time=(2026, 9, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            checksum, size = hashlib.sha256(), 0
            with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
                while chunk := reader.read(1024*1024):
                    writer.write(chunk)
                    checksum.update(chunk)
                    size += len(chunk)
            records[canonical] = {"sha256": checksum.hexdigest(), "bytes": size}
        payload = {"kind": kind, "files": records,
            "scope": "Local review package only; no external submission or publication performed"}
        info = zipfile.ZipInfo("PACKAGE_MANIFEST.json", date_time=(2026, 9, 12, 0, 0, 0))
        archive.writestr(info, json.dumps(payload, indent=2)+"\n")
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist()) != set(records)|{"PACKAGE_MANIFEST.json"}:
            raise ValueError("Archive entry set mismatch")
        for name, expected in records.items():
            checksum = hashlib.sha256()
            with archive.open(name) as reader:
                while chunk := reader.read(1024*1024):
                    checksum.update(chunk)
            if checksum.hexdigest() != expected["sha256"]:
                raise ValueError(f"Archive content checksum mismatch: {name}")
    return {"file": path.name, "kind": kind, "files": len(records), "bytes": path.stat().st_size,
            "sha256": digest(path), "all_entries_reopened_and_verified": True}


def package(root, output):
    workspace, root, output = Path.cwd().resolve(), Path(root), Path(output)
    if output.exists():
        raise FileExistsError("Choose a new package directory")
    manifest = json.loads((root/"manifest.json").read_text())
    verification = json.loads((root/"verification.json").read_text())
    analysis = json.loads((root/"analysis/manifest.json").read_text())
    if manifest["status"] != "complete frozen evaluation" or not verification["status"].startswith("passed"):
        raise ValueError("Final evaluation is incomplete or unverified")
    if verification["manifest_sha256"] != digest(root/"manifest.json") or analysis["source_manifest_sha256"] != digest(root/"manifest.json"):
        raise ValueError("Verification/analysis provenance mismatch")
    if not verification.get("files_sha256"):
        raise ValueError("Verification must identify the exact checked file snapshot")
    for directory, checksums in ((root, verification["files_sha256"]), (root/"analysis", analysis["files_sha256"])):
        for name, expected in checksums.items():
            if digest(directory/name) != expected:
                raise ValueError(f"Changed verified evidence: {directory/name}")
    pdf = Path("paper/build/manuscript.pdf")
    audit = json.loads(Path("paper/build/final_audit.json").read_text())
    visual = json.loads(Path("paper/build/visual_review.json").read_text())
    if audit["pdf_sha256"] != digest(pdf) or visual["pdf_sha256"] != digest(pdf):
        raise ValueError("PDF audits describe a different build")
    if audit.get("status") != "final mechanical audit" or audit["draft_marker_count"] or audit["identity_pattern_hits"] or not audit["all_fonts_embedded"] or audit["pages"] > 7 or audit["metadata"].get("/Author"):
        raise ValueError("Final mechanical PDF gates failed")
    if visual.get("status") != "final manuscript visually inspected":
        raise ValueError("Final visual review is still pending")
    ledger_path = Path("paper/claim_evidence.json")
    ledger = json.loads(ledger_path.read_text())
    verify_claim_ledger(workspace, ledger)
    metadata_path = Path("paper/submission_metadata.json")
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("pdf_sha256") != digest(pdf) or not metadata.get("title") or not metadata.get("abstract"):
        raise ValueError("Submission metadata must describe the final PDF")
    if metadata.get("status") != "local review draft; not submitted":
        raise ValueError("Unexpected submission metadata state")
    frozen = json.loads((root/"protocol_lock.json").read_text())
    private_files = set(frozen["files_sha256"])
    for name, expected in frozen["files_sha256"].items():
        if digest(name) != expected:
            raise ValueError(f"Original frozen dependency changed: {name}")
    for directory in ("solar_recovery", "research", "tests", "configs", "examples", "notebooks", "paper", "release"):
        for path in Path(directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and "rendered" not in path.parts:
                private_files.add(str(path))
    for path in root.rglob("*"):
        if path.is_file() and "completion_workflow" not in path.parts:
            private_files.add(str(path))
    for path in Path("data/processed").rglob("*"):
        if path.is_file():
            private_files.add(str(path))
    private_files.update(str(p) for p in Path("data/metadata").rglob("*") if p.is_file())
    private_files.update(str(p) for p in Path("data/raw").glob("*/manifest.json"))
    for directory in ("runs/annual_ac_daylight_causal_v3", "runs/annual_ac_calibration_v3", "runs/clean_environment_v4", "runs/inference_benchmark_v1", "runs/final_evidence_exports_v1"):
        for path in Path(directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                private_files.add(str(path))
    private_files.update(str(p) for p in Path(".").glob("*.md"))
    private_files.update({"pyproject.toml", "requirements-pilot.txt", str(ledger_path), str(metadata_path)})
    output.mkdir(parents=True)
    records = [write_archive(output/"ccwc_anonymous_manuscript.zip", workspace,
        [pdf, metadata_path, Path("paper/REVIEW_BUNDLE_README.md")], "Anonymous-manuscript review bundle; human approval pending")]
    records.append(write_archive(output/"ccwc_private_research.zip", workspace, private_files,
        "Private reproducible research archive; includes original PRD and internal provenance, not an anonymous upload"))
    result = {"status": "local review bundles built and reopened", "archives": records,
        "packer_sha256": digest(Path(__file__)), "final_pdf_sha256": digest(pdf),
        "claim_ledger_sha256": digest(ledger_path),
        "external_actions": "No upload, submission, publication, registration, payment or organizer contact",
        "human_gates": "Authorship/consent, originality and simultaneous-submission check, scientific review, second-person reproduction and disclosure placement remain separate review responsibilities"}
    (output/"manifest.json").write_text(json.dumps(result, indent=2)+"\n")
    print(f"Built and verified {len(records)} local archives in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    package(args.run, args.output)
