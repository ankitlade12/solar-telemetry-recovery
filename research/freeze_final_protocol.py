"""Run checks and create a single non-overwritable pre-evaluation hash lock."""
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys

from research.final_evaluation import forecast_sources
from solar_recovery.pilot import digest


def freeze():
    target = Path("research/FINAL_PROTOCOL_LOCK.json")
    if target.exists():
        raise FileExistsError("Protocol is already locked; use a documented new version for amendments")
    if digest("Solar_Forecasting_Research_PRD.docx") != "75b6e28dda396d72162ef5c8f5750426336eae7997b099573ef256ff729a2a6c":
        raise ValueError("Original PRD changed")
    check = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
    print(check.stdout, end="")
    if check.returncode:
        print(check.stderr, end="")
        raise RuntimeError("Tests failed; do not lock or evaluate")
    evidence = Path("research/final_protocol_test_record.json")
    evidence.write_text(json.dumps({"command": [sys.executable, "-m", "pytest", "-q"],
        "returncode": check.returncode, "stdout": check.stdout, "stderr": check.stderr,
        "utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Unit and end-to-end synthetic checks; no 2017 observed-data forecast evaluation"}, indent=2)+"\n")
    config_path = Path("configs/final_evaluation_v4.json")
    config = json.loads(config_path.read_text())
    files = [*forecast_sources(), *Path("tests").glob("test_*.py"),
        Path(__file__).relative_to(Path.cwd()), Path("research/prepare_final_data.py"),
        Path("research/FINAL_EVALUATION_PROTOCOL.md"), Path("research/RESERVED_DATA_QUALIFICATION.md"),
        Path("research/CLOSEST_METHOD_CROSSWALK.md"), Path("Solar_Forecasting_Research_PRD.docx"),
        Path("requirements-pilot.txt"), Path("pyproject.toml"), evidence]
    files += [p for p in Path(config["input_root"]).rglob("*") if p.is_file()]
    files += [Path(config["old_models"])/site/"models.pkl" for site in config["sites"]]
    files += [Path(config["old_models"])/"manifest.json", Path(config["old_models"])/"selected_profiles.csv"]
    packages = [line.split("==")[0] for line in Path("requirements-pilot.txt").read_text().splitlines() if "==" in line]
    lock = {"version": 4, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": digest(config_path), "files_sha256": {str(p): digest(p) for p in sorted(set(files))},
        "environment": {p: version(p) for p in packages}, "python": platform.python_version(),
        "performance_exposure": "2015/2016 development only; 2017 metadata and quality qualification only",
        "nature": "Internal pre-evaluation freeze, not public preregistration",
        "primary_contrast": config["inference"]["primary_contrast"],
        "case_count": len(config["cases"]),
        "site_case_count": sum(len(c.get("sites", config["sites"])) for c in config["cases"])}
    with target.open("x") as handle:
        handle.write(json.dumps(lock, indent=2)+"\n")
    print(f"Locked {len(lock['files_sha256'])} files; {lock['site_case_count']} site/case combinations")


if __name__ == "__main__":
    freeze()
