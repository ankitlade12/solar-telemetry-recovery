"""Verify tests and an identical synthetic run in a separately installed venv."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from solar_recovery.pilot import digest


def reproduce(interpreter, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Use a new reproduction directory")
    output.mkdir(parents=True)
    records = []
    env = {**os.environ, "MPLCONFIGDIR": "/private/tmp/solar-recovery-clean-mpl"}
    commands = [
        [interpreter, "-m", "pip", "freeze"],
        [interpreter, "-m", "pytest", "-q"],
        [interpreter, "-m", "examples.synthetic_replay", "--output", str(output/"clean_example")],
        [sys.executable, "-m", "examples.synthetic_replay", "--output", str(output/"reference_example")],
    ]
    for i, command in enumerate(commands):
        print(f"Reproduction stage {i+1}/{len(commands)}", flush=True)
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        (output/f"stage_{i+1}.log").write_text(result.stdout+result.stderr)
        records.append({"command": command, "returncode": result.returncode,
            "log_sha256": digest(output/f"stage_{i+1}.log")})
        if result.returncode:
            (output/"failure.json").write_text(json.dumps(records, indent=2)+"\n")
            raise RuntimeError(f"Stage {i+1} failed; see retained log")
        if i == 0:
            (output/"requirements-clean.txt").write_text(result.stdout)
    comparisons = {}
    for filename in ("synthetic_measurements.parquet", "visible_features.parquet", "forecasts.parquet", "diagnostics.parquet"):
        a = pd.read_parquet(output/"clean_example"/filename)
        b = pd.read_parquet(output/"reference_example"/filename)
        pd.testing.assert_frame_equal(a, b, check_exact=True)
        comparisons[filename] = {"rows": len(a), "exact_dataframe_equality": True,
            "clean_sha256": digest(output/"clean_example"/filename), "reference_sha256": digest(output/"reference_example"/filename)}
    record = {"status": "passed clean-environment tests and exact synthetic reproduction",
        "commands": records, "comparisons": comparisons, "verifier_sha256": digest(Path(__file__)),
        "limitations": "Automated fresh dependency installation on the same machine and Python version; not a second human or full-data reproduction"}
    (output/"verification.json").write_text(json.dumps(record, indent=2)+"\n")
    print(record["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    reproduce(args.python, args.output)
