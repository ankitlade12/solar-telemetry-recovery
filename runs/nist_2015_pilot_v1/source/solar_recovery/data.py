"""Conservative adapter for the pilot's explicitly identified NIST sensors."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

METRICS = {82610: "pv", 82595: "irradiance"}


def solar_elevation(times, latitude, longitude):
    """NOAA fractional-year approximation, UTC; used only as a geometric mask.

    Reference: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
    No measured future irradiance or generation enters the daylight definition.
    """
    times = pd.DatetimeIndex(times).tz_convert("UTC")
    hours = np.asarray(times.hour+times.minute/60)
    year_days = np.where(times.is_leap_year, 366, 365)
    gamma = 2*np.pi/year_days*(np.asarray(times.dayofyear)-1+(hours-12)/24)
    eq = 229.18*(.000075+.001868*np.cos(gamma)-.032077*np.sin(gamma)
                 -.014615*np.cos(2*gamma)-.040849*np.sin(2*gamma))
    dec = (.006918-.399912*np.cos(gamma)+.070257*np.sin(gamma)
           -.006758*np.cos(2*gamma)+.000907*np.sin(2*gamma)
           -.002697*np.cos(3*gamma)+.00148*np.sin(3*gamma))
    ha = np.deg2rad((hours*60+eq+4*longitude)/4-180)
    lat = np.deg2rad(latitude)
    return np.rad2deg(np.arcsin(np.clip(np.sin(lat)*np.sin(dec)+np.cos(lat)*np.cos(dec)*np.cos(ha), -1, 1)))


def hourly_from_minutes(raw):
    """Require every one-minute observation in each left-aligned hourly bin."""
    raw = raw.copy()
    required = {"utc_measured_on", "metric_id", "value"}
    if not required <= set(raw):
        raise ValueError(f"Missing columns: {required-set(raw)}")
    raw = raw[raw.metric_id.isin(METRICS)]
    raw["utc_measured_on"] = pd.to_datetime(raw.utc_measured_on, utc=True)
    if not raw.utc_measured_on.eq(raw.utc_measured_on.dt.floor("min")).all():
        raise ValueError("Off-grid subminute timestamps require separate integration")
    audit = {"raw_selected_rows": len(raw)}
    groups = raw.groupby(["utc_measured_on", "metric_id"]).value
    conflict = groups.nunique(dropna=False).gt(1)
    audit["conflicting_timestamp_metric_pairs"] = int(conflict.sum())
    if conflict.any():
        raise ValueError("Conflicting duplicate measurements; no automatic reconciliation")
    audit["identical_duplicate_rows_removed"] = int(raw.duplicated(["utc_measured_on", "metric_id"]).sum())
    raw = raw.drop_duplicates(["utc_measured_on", "metric_id"]).copy()
    raw["value"] = pd.to_numeric(raw.value, errors="raise")
    invalid = ~np.isfinite(raw.value) | (raw.value < 0)
    exclusions = raw.loc[invalid, ["utc_measured_on", "metric_id", "value"]].copy()
    exclusions["reason"] = np.where(np.isfinite(exclusions.value), "negative_measurement", "nonfinite_measurement")
    raw.loc[invalid, "value"] = np.nan
    wide = raw.pivot(index="utc_measured_on", columns="metric_id", values="value").rename(columns=METRICS).sort_index()
    means = wide.resample("h", closed="left", label="right").mean()
    counts = wide.resample("h", closed="left", label="right").count()
    means = means.where(counts.eq(60))
    means.index.name = "interval_end"
    for stream in METRICS.values():
        means[f"{stream}_sample_count"] = counts[stream]
    audit.update({"hourly_rows": len(means), "valid_pv_hours": int(means.pv.notna().sum()),
                  "valid_irradiance_hours": int(means.irradiance.notna().sum()),
                  "valid_joint_hours": int(means[["pv", "irradiance"]].notna().all(axis=1).sum()),
                  "first_interval_end": means.index.min().isoformat(),
                  "last_interval_end": means.index.max().isoformat(),
                  "negative_or_nonfinite_measurements": len(exclusions)})
    return means, audit, exclusions


def prepare(snapshot, output):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise FileExistsError(f"Use a fresh output directory: {output}")
    manifest = json.loads((snapshot/"manifest.json").read_text())
    if manifest["system_id"] != 4902:
        raise ValueError("This initial adapter is explicitly restricted to NIST system 4902")
    for item in manifest["files"]:
        path = snapshot/Path(item["key"]).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Source hash mismatch: {path}")
    metrics = pd.read_parquet(snapshot/"metrics__system_4902__part000.parquet")
    selected = metrics.set_index("metric_id").loc[list(METRICS)]
    if selected.loc[82610, "units"] != "kW" or selected.loc[82595, "units"] != "W/m^2":
        raise ValueError("Unexpected sensor units")
    if not selected.calc_scale.eq(1).all() or not selected.calc_offset.eq(0).all() or not selected.aggregation_type.eq("avg").all():
        raise ValueError("Sensor scaling/aggregation requires manual review")
    site = json.loads((snapshot/"4902_system_metadata.json").read_text())
    if site["Inverters"]["Inverter 0"]["time_interval"] != "L" or site["Other Instruments"]["Other Instrument 2"]["time_interval"] != "L":
        raise ValueError("Expected left-aligned sensor intervals")
    pieces = []
    for path in sorted(snapshot.glob("system_4902__date_*.parquet")):
        pieces.append(pd.read_parquet(path, columns=["utc_measured_on", "metric_id", "value"],
                                     filters=[("metric_id", "in", list(METRICS))]))
    if not pieces:
        raise ValueError("No measurement partitions")
    hourly, audit, exclusions = hourly_from_minutes(pd.concat(pieces, ignore_index=True))
    output.mkdir(parents=True)
    hourly.to_parquet(output/"hourly.parquet")
    exclusions.to_parquet(output/"excluded_measurements.parquet", index=False)
    contract = {"system_id": 4902, "name": site["System"]["public_name"],
                "latitude": float(site["Site"]["latitude"]), "longitude": float(site["Site"]["longitude"]),
                "capacity_kw_dc": float(site["System"]["power"]),
                "target": "hourly mean measured inverter DC power, kW", "pv_metric_id": 82610,
                "irradiance": "measured plane-of-array reference-cell irradiance, W/m^2", "irradiance_metric_id": 82595,
                "timestamps": "source utc_measured_on interpreted as UTC; documented left-aligned minute averages",
                "receipt_assumption": "No actual receipts available; normal receipt at completed hour boundary is a pilot assumption",
                "quality_policy": "Retain real zeros; exclude negative/nonfinite readings; require 60 distinct valid minutes per stream per hour; no imputation",
                "daylight": "NOAA approximate solar elevation > 0 at target interval midpoint",
                "license": manifest["license"], "doi": manifest["doi"],
                "source_manifest_sha256": hashlib.sha256((snapshot/"manifest.json").read_bytes()).hexdigest(),
                "hourly_sha256": hashlib.sha256((output/"hourly.parquet").read_bytes()).hexdigest(),
                "limitations": ["One site and one historical year; not a cross-site benchmark",
                                "Source catalog QA flags require domain review before publication",
                                "Instrument calibration certificates and upstream cleaning history not independently verified",
                                "Missing targets stay unscorable; synthetic delivery outages do not change physical truth"]}
    (output/"contract.json").write_text(json.dumps(contract, indent=2)+"\n")
    (output/"audit.json").write_text(json.dumps(audit, indent=2)+"\n")
    (output/"source_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    prepare(args.snapshot, args.output)
