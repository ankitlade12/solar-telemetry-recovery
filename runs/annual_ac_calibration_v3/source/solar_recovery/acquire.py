"""Bounded public PVDAQ acquisition with checksummed source manifests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import requests

BASE = "https://oedi-data-lake.s3.amazonaws.com/"
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_objects(prefix):
    items, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": 1000}
        if token:
            params["continuation-token"] = token
        response = requests.get(BASE, params=params, timeout=30)
        response.raise_for_status()
        tree = ET.fromstring(response.content)
        for item in tree.findall("s:Contents", NS):
            items.append({"key": item.findtext("s:Key", namespaces=NS),
                          "bytes": int(item.findtext("s:Size", namespaces=NS)),
                          "etag": item.findtext("s:ETag", namespaces=NS)})
        token = tree.findtext("s:NextContinuationToken", namespaces=NS)
        if not token:
            return items


def fetch(item, folder):
    path = folder / Path(item["key"]).name
    if path.exists() and "sha256" in item:
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() == item["sha256"]:
            return item
        raise ValueError(f"Cached source changed: {path}")
    for attempt in range(3):
        try:
            response = requests.get(BASE+item["key"], timeout=60)
            response.raise_for_status()
            if "bytes" in item and len(response.content) != item["bytes"]:
                raise ValueError(f"Size changed for {item['key']}")
            content = response.content
            path.write_bytes(content)
            return {**item, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(attempt+1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-id", type=int, default=4902)
    parser.add_argument("--year", type=int, default=2015)
    parser.add_argument("--max-mb", type=float, default=200)
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    folder = args.root / f"pvdaq_{args.system_id}_{args.year}"
    folder.mkdir(parents=True, exist_ok=True)
    manifest_file = folder / "manifest.json"
    if manifest_file.exists():
        old = json.loads(manifest_file.read_text())
        items = old["files"]
        for item in items:
            path = folder/Path(item["key"]).name
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"Manifest mismatch: {path}")
        print(f"Verified cached snapshot: {len(items)} files", flush=True)
        return
    prefix = f"pvdaq/parquet/pvdata/system_id={args.system_id}/year={args.year}/"
    items = [item for item in list_objects(prefix) if item["key"].endswith(".parquet")]
    if not items:
        raise ValueError("No source files found")
    size = sum(item["bytes"] for item in items)
    if size > args.max_mb*1e6:
        raise ValueError(f"Download would be {size/1e6:.1f} MB, exceeding the explicit limit")
    print(f"Downloading {len(items)} daily files, {size/1e6:.1f} MB", flush=True)
    items += [{"key": f"pvdaq/parquet/metrics/metrics__system_{args.system_id}__part000.parquet"},
              {"key": f"pvdaq/csv/system_metadata/{args.system_id}_system_metadata.json"}]
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, item in enumerate(pool.map(lambda item: fetch(item, folder), items), 1):
            results.append(item)
            if i % 40 == 0:
                print(f"Verified {i}/{len(items)} files", flush=True)
    manifest = {"dataset": "PVDAQ", "doi": "10.25984/1846021", "license": "CC-BY-4.0",
                "license_source": "https://catalog.data.gov/dataset/photovoltaic-data-acquisition-pvdaq-public-datasets",
                "downloaded_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "system_id": args.system_id, "year": args.year, "files": results}
    manifest_file.write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Snapshot saved: {manifest_file}", flush=True)


if __name__ == "__main__":
    main()
