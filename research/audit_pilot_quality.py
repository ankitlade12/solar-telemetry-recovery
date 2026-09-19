"""Reproduce the pilot's hourly completeness and range audit."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from solar_recovery.data import solar_elevation


def audit(directory):
    directory = Path(directory)
    frame = pd.read_parquet(directory/"hourly.parquet")
    contract = json.loads((directory/"contract.json").read_text())
    daylight = solar_elevation(frame.index-pd.Timedelta(minutes=30), contract["latitude"], contract["longitude"]) > 0
    result = {"hourly_sha256": hashlib.sha256((directory/"hourly.parquet").read_bytes()).hexdigest(),
              "normalization_audit": json.loads((directory/"audit.json").read_text()), "strata": {}}
    for name, part in (("all", frame), ("daylight", frame[daylight]), ("night", frame[~daylight])):
        result["strata"][name] = {"hours": len(part), "valid_pv_hours": int(part.pv.notna().sum()),
            "valid_irradiance_hours": int(part.irradiance.notna().sum()),
            "valid_joint_hours": int(part[["pv", "irradiance"]].notna().all(axis=1).sum()),
            "pv_max_kw": float(part.pv.max()), "irradiance_max_w_m2": float(part.irradiance.max())}
    grouped = frame.groupby(frame.index.strftime("%Y-%m"))
    result["utc_months"] = {name: {"hours": len(part), "valid_pv_hours": int(part.pv.notna().sum()),
        "valid_irradiance_hours": int(part.irradiance.notna().sum())} for name, part in grouped}
    excluded = pd.read_parquet(directory/"excluded_measurements.parquet")
    result["negative_or_nonfinite_by_metric"] = {str(k): int(v) for k, v in excluded.groupby("metric_id").size().items()}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/processed/nist_2015")
    parser.add_argument("--output", default="research/pvdaq_pilot_quality.json")
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(audit(args.data), indent=2)+"\n")
