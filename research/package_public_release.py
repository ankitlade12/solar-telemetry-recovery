"""Assemble and exercise a local public-release candidate; never publish it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from research.package_submission import checked_path, write_archive
from research.release_protocol import PRIVATE_PRD, validate_release_view
from solar_recovery.pilot import digest


def candidate_files(workspace, run):
    workspace, run = Path(workspace), Path(run)
    view = json.loads((workspace/"release/DEPENDENCY_LOCK.json").read_text())
    parent = json.loads((workspace/"research/FINAL_PROTOCOL_LOCK.json").read_text())
    validate_release_view(view, parent)
    files = set(view["files_sha256"])
    def add_tree(relative, predicate=lambda p: True):
        for path in (workspace/relative).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and predicate(path):
                files.add(path.relative_to(workspace).as_posix())
    for directory in ("solar_recovery", "tests", "configs", "examples", "notebooks", "release", "data/processed", "data/metadata"):
        add_tree(directory)
    files.update(p.relative_to(workspace).as_posix() for p in (workspace/"research").glob("*.py"))
    files.update(p.relative_to(workspace).as_posix() for p in (workspace/"research").glob("*CROSSWALK.md"))
    files.update(p.relative_to(workspace).as_posix() for p in (workspace/"data/raw").glob("*/manifest.json"))
    for directory in (str(run), "runs/inference_benchmark_v1", "runs/clean_environment_v4", "runs/final_evidence_exports_v1"):
        add_tree(directory, lambda p: "completion_workflow" not in p.parts and p.suffix != ".log")
    add_tree("paper", lambda p: "build" not in p.relative_to(workspace/"paper").parts)
    files.update({"research/FINAL_PROTOCOL_LOCK.json", "research/ANNUAL_DEVELOPMENT_PROTOCOL.md",
        "research/WIND_QUANTILE_CROSSWALK.md", "research/POST_FREEZE_ANALYSIS_LOG.md", "research/hardware.json",
        "research/FINAL_FINDINGS.md", "research/PRD_TRACEABILITY.md", "research/FINAL_PERFORMANCE_EXPOSURE.json",
        "MODEL_CARD.md", "DATA_AVAILABILITY.md", "pyproject.toml", "requirements-pilot.txt",
        "paper/build/manuscript.pdf", "paper/build/final_audit.json", "paper/build/visual_review.json"})
    ledger = json.loads((workspace/"paper/claim_evidence.json").read_text())
    files.update(claim["source_path"] for claim in ledger["claims"])
    files = {checked_path(workspace, name).relative_to(workspace.resolve()).as_posix() for name in files}
    if PRIVATE_PRD in files or any(name.startswith("research/sources/") for name in files):
        raise ValueError("Private planning or copied external papers entered the public candidate")
    return sorted(files)


def package(root, review_manifest, output):
    workspace, root, review_manifest, output = Path.cwd().resolve(), Path(root), Path(review_manifest), Path(output)
    if output.exists():
        raise FileExistsError("Choose a fresh public-candidate output directory")
    review = json.loads(review_manifest.read_text())
    if review["status"] != "local review bundles built and reopened":
        raise ValueError("Complete the independently checked manuscript/private bundles first")
    for entry in review["archives"]:
        if digest(review_manifest.parent/entry["file"]) != entry["sha256"]:
            raise ValueError("Changed review archive")
    if digest("paper/build/manuscript.pdf") != review["final_pdf_sha256"] or digest("paper/claim_evidence.json") != review["claim_ledger_sha256"]:
        raise ValueError("Manuscript or claims changed since package review")
    latency_path = Path("runs/inference_benchmark_v1/manifest.json")
    latency = json.loads(latency_path.read_text())
    if latency["status"] != "complete loaded-model latency benchmark":
        raise ValueError("Complete the required latency measurement first")
    for name, expected in latency["files_sha256"].items():
        if digest(latency_path.parent/name) != expected:
            raise ValueError("Changed measured latency artifact")
    files = candidate_files(workspace, root)
    staging = output/"public_candidate"
    staging.mkdir(parents=True)
    for name in files:
        target = staging/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace/name, target)
    shutil.copyfile(workspace/"release/README.md", staging/"README.md")
    checks = staging/"release/checks"
    checks.mkdir()
    env = {**os.environ, "MPLCONFIGDIR": str(checks.resolve()/"matplotlib_cache"),
           "XDG_CACHE_HOME": str(checks.resolve()/"cache")}
    commands = [
        [sys.executable, "-c", "from research.release_protocol import verification_protocol; f,p=verification_protocol('configs/final_evaluation_v4.json','research/FINAL_PROTOCOL_LOCK.json','release/DEPENDENCY_LOCK.json'); assert p['scientific_dependencies_verified']==82 and not p['private_prd_bytes_verified']; print('All 82 scientific dependencies verified without the private PRD')"],
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "examples.synthetic_replay", "--output", "runs/public_candidate_example"],
    ]
    stages = []
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=staging, env=env, capture_output=True, text=True)
        log = checks/f"stage_{index+1}.log"
        log.write_text(result.stdout+result.stderr)
        stages.append({"command": command, "returncode": result.returncode, "log": str(log.relative_to(staging)), "log_sha256": digest(log)})
        if result.returncode:
            raise RuntimeError(f"Public-candidate check failed; retain and inspect {log}")
    # The source example is deterministic; compare values, not just successful exit.
    import pandas as pd
    comparisons = {}
    for name in ("synthetic_measurements.parquet", "visible_features.parquet", "forecasts.parquet", "diagnostics.parquet"):
        reference = staging/"runs/clean_environment_v4/reference_example"/name
        reproduced = staging/"runs/public_candidate_example"/name
        pd.testing.assert_frame_equal(pd.read_parquet(reference), pd.read_parquet(reproduced), check_exact=True)
        comparisons[name] = {"exact_dataframe_equality": True, "reference_sha256": digest(reference), "reproduced_sha256": digest(reproduced)}
    check_record = {"status": "passed candidate dependency closure, tests and exact synthetic reproduction",
        "stages": stages, "comparisons": comparisons,
        "scope": "Automated on the same machine and installed environment; not a fresh dependency install, final-data rerun, second-human reproduction or publication approval"}
    (checks/"verification.json").write_text(json.dumps(check_record, indent=2)+"\n")
    archive_files = [p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts and p.suffix != ".pyc"
                     and not any(part in {"matplotlib_cache", "cache"} for part in p.relative_to(staging).parts)]
    archive = write_archive(output/"ccwc_public_release_candidate.zip", staging, archive_files,
        "Local public-release candidate; original-code license, author review and publication consent pending")
    record = {"status": "local public-release candidate built and reopened", "archive": archive,
        "source_review_manifest_sha256": digest(review_manifest), "packer_sha256": digest(Path(__file__)),
        "scientific_dependency_view_sha256": digest("release/DEPENDENCY_LOCK.json"),
        "candidate_checks_sha256": digest(checks/"verification.json"),
        "external_actions": "None; no publication, upload, contact, registration or payment"}
    (output/"manifest.json").write_text(json.dumps(record, indent=2)+"\n")
    print(f"Built and reopened the checked public-release candidate in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--review-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    package(args.run, args.review_manifest, args.output)
