"""A declared public dependency view; the original prospective lock is immutable."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from research.final_evaluation import assert_freeze
from solar_recovery.pilot import digest

ORIGINAL_LOCK_SHA256 = "b01f5fa92907e3967e61628d70a664ada8114398132aa32cea95e875e2151960"
PRIVATE_PRD = "Solar_Forecasting_Research_PRD.docx"
PRIVATE_PRD_SHA256 = "75b6e28dda396d72162ef5c8f5750426336eae7997b099573ef256ff729a2a6c"


def validate_release_view(view, parent):
    """Only the private specification may be omitted; every scientific hash stays."""
    expected_files = dict(parent["files_sha256"])
    if expected_files.pop(PRIVATE_PRD) != PRIVATE_PRD_SHA256:
        raise ValueError("Unexpected private specification hash")
    if view["files_sha256"] != expected_files:
        raise ValueError("Release view changed a scientific dependency")
    for key, value in parent.items():
        if key not in {"files_sha256", "nature", "performance_exposure"} and view.get(key) != value:
            raise ValueError(f"Release view changed frozen field: {key}")
    derivation = view.get("release_derivation", {})
    if derivation.get("parent_sha256") != ORIGINAL_LOCK_SHA256 or derivation.get("omitted_private_files") != {PRIVATE_PRD: PRIVATE_PRD_SHA256}:
        raise ValueError("Release view lacks exact parent/omission provenance")
    if view.get("nature") != "Derived public reproduction dependency view; not a new prospective freeze":
        raise ValueError("Release derivation must not claim a new prospective freeze")


def derive(parent_path, output):
    parent_path, output = Path(parent_path), Path(output)
    if output.exists():
        raise FileExistsError("Never overwrite a release dependency view")
    if digest(parent_path) != ORIGINAL_LOCK_SHA256:
        raise ValueError("Original prospective lock changed")
    parent = json.loads(parent_path.read_text())
    view = dict(parent)
    view["files_sha256"] = {k: v for k, v in parent["files_sha256"].items() if k != PRIVATE_PRD}
    view["nature"] = "Derived public reproduction dependency view; not a new prospective freeze"
    view["performance_exposure"] = "This file makes no prospective-exposure claim; the unchanged parent records the original experiment freeze."
    view["release_derivation"] = {"parent_path": str(parent_path), "parent_sha256": digest(parent_path),
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "omitted_private_files": {PRIVATE_PRD: PRIVATE_PRD_SHA256},
        "scope": "Only private planning documentation is omitted. All code, tests, inputs, archived models, configuration and environment constraints remain identical."}
    validate_release_view(view, parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(view, indent=2)+"\n")
    print(f"Derived {len(view['files_sha256'])}-file public dependency view; original lock unchanged")


def verification_protocol(config_path, run_lock, release_lock=None):
    if release_lock is None:
        frozen = assert_freeze(config_path, run_lock)
        if digest(PRIVATE_PRD) != PRIVATE_PRD_SHA256:
            raise ValueError("Original PRD changed")
        return frozen, {"mode": "original private-workspace verification", "private_prd_bytes_verified": True}
    release_lock = Path(release_lock)
    view = json.loads(release_lock.read_text())
    parent_path = Path(view["release_derivation"]["parent_path"])
    if digest(parent_path) != ORIGINAL_LOCK_SHA256:
        raise ValueError("Release parent is not the original prospective lock")
    parent = json.loads(parent_path.read_text())
    validate_release_view(view, parent)
    if digest(run_lock) not in {ORIGINAL_LOCK_SHA256, digest(release_lock)}:
        raise ValueError("Run lock is neither the preserved original nor this validated release view")
    assert_freeze(config_path, release_lock)
    if Path(PRIVATE_PRD).exists() and digest(PRIVATE_PRD) != PRIVATE_PRD_SHA256:
        raise ValueError("A present original PRD must still be unchanged")
    frozen = json.loads(Path(run_lock).read_text())
    return frozen, {"mode": "explicit public-release verification", "parent_sha256": ORIGINAL_LOCK_SHA256,
        "release_view_sha256": digest(release_lock), "scientific_dependencies_verified": len(view["files_sha256"]),
        "private_prd_bytes_verified": Path(PRIVATE_PRD).is_file(), "declared_omissions": view["release_derivation"]["omitted_private_files"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", default="research/FINAL_PROTOCOL_LOCK.json")
    parser.add_argument("--output", default="release/DEPENDENCY_LOCK.json")
    args = parser.parse_args()
    derive(args.parent, args.output)
