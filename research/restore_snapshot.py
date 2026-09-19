"""Restore exact public PVDAQ objects from an archived checksum manifest."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from urllib.parse import quote

import requests

from solar_recovery.pilot import digest

BASE = "https://oedi-data-lake.s3.amazonaws.com/"


def restore_object(item, folder):
    key = PurePosixPath(item["key"])
    if key.is_absolute() or ".." in key.parts or key.parts[0] != "pvdaq":
        raise ValueError("Manifest key is not a public PVDAQ object")
    path = folder/key.name
    expected_size, expected_hash = int(item["bytes"]), item["sha256"]
    if path.exists():
        if path.stat().st_size != expected_size or digest(path) != expected_hash:
            raise ValueError(f"Existing snapshot object changed: {path}")
        return {"key": item["key"], "status": "verified existing", "bytes": expected_size}
    content = bytearray()
    with requests.get(BASE+quote(item["key"], safe="/="), stream=True, timeout=60) as response:
        response.raise_for_status()
        for chunk in response.iter_content(1024*1024):
            content.extend(chunk)
            if len(content) > expected_size:
                raise ValueError(f"Public object grew beyond the archived size: {item['key']}")
    if len(content) != expected_size or hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError(f"Public object no longer matches the archived snapshot: {item['key']}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".verified_download_", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        # Publish complete verified bytes without overwriting a concurrently
        # created destination. Same-directory hard link keeps this atomic.
        try:
            os.link(temporary, path)
        except FileExistsError:
            if digest(path) != expected_hash:
                raise ValueError(f"Destination changed during restoration: {path}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"key": item["key"], "status": "restored verified bytes", "bytes": expected_size}


def restore(manifest_path, output=None, max_mb=200., workers=4):
    manifest_path = Path(manifest_path)
    content = manifest_path.read_bytes()
    manifest = json.loads(content)
    if manifest.get("dataset") != "PVDAQ" or not manifest.get("files"):
        raise ValueError("Require a nonempty PVDAQ snapshot manifest")
    items = manifest["files"]
    names = [PurePosixPath(item["key"]).name for item in items]
    if len(set(names)) != len(names):
        raise ValueError("Snapshot object basenames must be unique")
    if not 1 <= workers <= 8 or not 0 < max_mb <= 10000:
        raise ValueError("Use 1–8 workers and a positive download budget up to 10,000 MB")
    folder = manifest_path.parent if output is None else Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    target_manifest = folder/"manifest.json"
    if target_manifest.exists() and target_manifest.read_bytes() != content:
        raise ValueError("Destination contains a different snapshot manifest")
    missing_bytes = sum(int(item["bytes"]) for item in items if not (folder/PurePosixPath(item["key"]).name).exists())
    if missing_bytes > max_mb*1e6:
        raise ValueError(f"Missing objects require {missing_bytes/1e6:.1f} MB, above the explicit budget")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        restored = list(pool.map(lambda item: restore_object(item, folder), items))
    if not target_manifest.exists():
        with target_manifest.open("xb") as handle:
            handle.write(content)
    if digest(target_manifest) != hashlib.sha256(content).hexdigest():
        raise ValueError("Original manifest bytes were not preserved")
    receipt = {"status": "all listed public objects verified", "manifest_sha256": digest(target_manifest),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(), "files": restored,
        "downloaded_bytes": sum(item["bytes"] for item in restored if item["status"] == "restored verified bytes"),
        "code_sha256": digest(Path(__file__)),
        "scope": "The archived manifest is unchanged. A separate restoration receipt records this verification."}
    (folder/"restoration_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(f"Verified {len(restored)} objects; restored {receipt['downloaded_bytes']/1e6:.2f} MB; original manifest preserved")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output")
    parser.add_argument("--max-mb", type=float, default=200.)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    restore(args.manifest, args.output, args.max_mb, args.workers)
