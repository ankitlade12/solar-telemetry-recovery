"""Archive matching code bytes so later development cannot erase reproducibility."""
import argparse
import json
from pathlib import Path

from solar_recovery.pilot import digest


def archive(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text())
    hashes = dict(manifest["code_sha256"])
    for name in ["runner_sha256", "probe_script_sha256"]:
        if name in manifest:
            matches = [p for p in Path("research").glob("*.py") if digest(p) == manifest[name]]
            if len(matches) != 1:
                raise ValueError(f"Could not uniquely resolve {name}")
            hashes[str(matches[0])] = manifest[name]
    for filename, expected in hashes.items():
        source, target = Path(filename), directory/"source"/filename
        if target.exists():
            if digest(target) != expected:
                raise ValueError(f"Existing source archive differs: {target}")
            continue
        if digest(source) != expected:
            raise ValueError(f"Working source no longer matches run: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (directory/"source_manifest.json").write_text(json.dumps(hashes, indent=2)+"\n")
    print(f"Archived and verified {len(hashes)} source files for {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    for path in args.runs:
        archive(path)
