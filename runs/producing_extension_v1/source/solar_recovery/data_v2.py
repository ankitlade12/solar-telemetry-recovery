"""Explicit AC-target development contracts for NIST and Colorado PVDAQ arrays."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import solar_elevation
from .pilot import digest

SITES = {
    4902: {"pv": 82633, "irradiance": 82595, "pv_unit": "kW", "pv_to_kw": 1.,
           "utc_add_hours": 5, "alignment": "left aligned according to meter and reference-cell metadata"},
    4: {"pv": 315, "irradiance": 313, "pv_unit": "W", "pv_to_kw": .001,
        "utc_add_hours": 7, "alignment": "instrument alignment unspecified; timestamp-bin target definition, one-minute sensitivity required"}}


def normalize(raw, specification, capacity, bounds=None, timestamp_shift_minutes=0):
    if timestamp_shift_minutes not in (-1, 0, 1):
        raise ValueError("Only explicit one-minute alignment sensitivities are supported")
    bounds = {"ac_min_kw": -.05*capacity, "ac_max_kw": 1.5*capacity,
              "poa_min_w_m2": -20., "poa_max_w_m2": 2000.} if bounds is None else bounds
    if not all(np.isfinite(bounds[k]) for k in ("ac_min_kw", "ac_max_kw", "poa_min_w_m2", "poa_max_w_m2")):
        raise ValueError("Quality bounds must be finite")
    if bounds["ac_min_kw"] >= bounds["ac_max_kw"] or bounds["poa_min_w_m2"] >= bounds["poa_max_w_m2"]:
        raise ValueError("Quality bounds must be ordered")
    raw = raw.copy()
    raw["measured_on"] = pd.to_datetime(raw.measured_on)
    raw["utc_measured_on"] = pd.to_datetime(raw.utc_measured_on)
    expected_utc = raw.measured_on+pd.Timedelta(hours=specification["utc_add_hours"])
    if raw.utc_measured_on.notna().all():
        if not raw.utc_measured_on.eq(expected_utc).all():
            raise ValueError("UTC field conflicts with fixed-offset source contract")
        times = raw.utc_measured_on
        timestamp_source = "source UTC, cross-checked against native fixed-offset timestamps"
    elif raw.utc_measured_on.isna().all() and specification["utc_add_hours"] == 7:
        times = expected_utc
        timestamp_source = "derived UTC: native timestamps plus seven hours; fixed-offset interpretation qualified from catalog and development-grid audit"
    else:
        raise ValueError("Mixed/missing UTC timestamps outside the explicit Colorado contract")
    raw["timestamp"] = pd.to_datetime(times, utc=True)+pd.Timedelta(minutes=timestamp_shift_minutes)
    if not raw.timestamp.eq(raw.timestamp.dt.floor("min")).all():
        raise ValueError("Off-grid timestamps require separate treatment")
    key = ["timestamp", "metric_id"]
    if raw.groupby(key).value.nunique(dropna=False).gt(1).any():
        raise ValueError("Conflicting timestamp/metric values")
    duplicate_count = int(raw.duplicated(key).sum())
    raw = raw.drop_duplicates(key).copy()
    pv_mask = raw.metric_id.eq(specification["pv"])
    raw.loc[pv_mask, "value"] *= specification["pv_to_kw"]
    invalid = ~np.isfinite(raw.value)
    # Deliberately broad instrument-domain screening, not zero imputation.
    invalid |= pv_mask & ((raw.value < bounds["ac_min_kw"]) | (raw.value > bounds["ac_max_kw"]))
    invalid |= ~pv_mask & ((raw.value < bounds["poa_min_w_m2"]) | (raw.value > bounds["poa_max_w_m2"]))
    exclusions = raw.loc[invalid, ["timestamp", "metric_id", "value"]].copy()
    raw.loc[invalid, "value"] = np.nan
    wide = raw.pivot(index="timestamp", columns="metric_id", values="value").rename(
        columns={specification["pv"]: "pv", specification["irradiance"]: "irradiance"}).sort_index()
    counts = wide.resample("h", closed="left", label="right").count()
    hourly = wide.resample("h", closed="left", label="right").mean().where(counts.eq(60))
    hourly["pv_signed_mean_kw"] = hourly.pv
    hourly["pv"] = hourly.pv.clip(lower=0)
    hourly["pv_sample_count"], hourly["irradiance_sample_count"] = counts.pv, counts.irradiance
    hourly.index.name = "interval_end"
    return hourly, exclusions, {"duplicate_rows_removed": duplicate_count, "timestamp_source": timestamp_source,
        "excluded_minute_rows": len(exclusions), "negative_hourly_ac_means_clipped": int(hourly.pv_signed_mean_kw.lt(0).sum())}


def prepare(snapshot, output):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise FileExistsError("Use a fresh normalized-data directory")
    manifest = json.loads((snapshot/"manifest.json").read_text())
    system = manifest["system_id"]
    specification = SITES[system]
    for item in manifest["files"]:
        assert digest(snapshot/Path(item["key"]).name) == item["sha256"]
    metrics = pd.read_parquet(snapshot/f"metrics__system_{system}__part000.parquet").set_index("metric_id")
    selected = metrics.loc[[specification["pv"], specification["irradiance"]]]
    if not selected.calc_scale.eq(1).all() or not selected.calc_offset.eq(0).all() or not selected.aggregation_type.eq("avg").all():
        raise ValueError("Unresolved scaling or aggregation")
    if selected.loc[specification["pv"], "units"] != specification["pv_unit"] or selected.loc[specification["irradiance"], "units"] != "W/m^2":
        raise ValueError("Unexpected units")
    metadata = json.loads((snapshot/f"{system}_system_metadata.json").read_text())
    if system == 4902 and metadata["Meters"]["Meter 0"]["time_interval"] != "L":
        raise ValueError("Unexpected NIST meter interval alignment")
    capacity = float(metadata["System"]["power"])
    raw = pd.concat([pd.read_parquet(path, columns=["measured_on", "utc_measured_on", "metric_id", "value"],
                                    filters=[("metric_id", "in", list(selected.index))])
                     for path in sorted(snapshot.glob(f"system_{system}__date*.parquet"))], ignore_index=True)
    hourly, exclusions, audit = normalize(raw, specification, capacity)
    lat, lon = float(metadata["Site"]["latitude"]), float(metadata["Site"]["longitude"])
    daylight = solar_elevation(hourly.index-pd.Timedelta(minutes=30), lat, lon) > 0
    audit.update({"system_id": system, "year": manifest["year"], "hours": len(hourly),
        "valid_pv_hours": int(hourly.pv.notna().sum()), "valid_irradiance_hours": int(hourly.irradiance.notna().sum()),
        "daylight_hours": int(daylight.sum()), "valid_daylight_pv_hours": int(hourly.loc[daylight, "pv"].count()),
        "valid_daylight_joint_hours": int(hourly.loc[daylight, ["pv", "irradiance"]].notna().all(axis=1).sum())})
    output.mkdir(parents=True)
    hourly.to_parquet(output/"hourly.parquet")
    exclusions.to_parquet(output/"excluded_measurements.parquet", index=False)
    contract = {"system_id": system, "year": manifest["year"], "name": metadata["System"]["public_name"],
        "latitude": lat, "longitude": lon, "capacity_kw_dc": capacity, "specification": specification,
        "target": "nonnegative component of the hourly mean of recorded AC real-power samples, kW",
        "target_transform": "max(mean(valid minute AC measurements), 0); missing means remain missing",
        "irradiance": "mean recorded POA irradiance; small negative sensor readings retained, not treated as delivery failure",
        "hour_definition": "60 valid distinct source minute records in left-closed timestamp bins, labelled at the next hour",
        "quality_bounds": {"ac_min_kw": -.05*capacity, "ac_max_kw": 1.5*capacity, "poa_min_w_m2": -20., "poa_max_w_m2": 2000.},
        "timestamp_source": audit["timestamp_source"], "alignment": specification["alignment"],
        "receipt_assumption": "Operational receipts unavailable. For alignment sensitivity, impose at least one-minute release margin; current artifact is data only.",
        "status": "development data; Colorado UTC/interval convention is a qualified assumption requiring sensitivity analysis",
        "source_manifest_sha256": digest(snapshot/"manifest.json"), "hourly_sha256": digest(output/"hourly.parquet"),
        "adapter_sha256": digest(__file__), "license": manifest["license"], "doi": manifest["doi"],
        "limitations": ["quality bounds are explicit engineering choices requiring sensitivity analysis",
                        "AC sensor and nonnegative-component target differ from the original inverter-DC pilot",
                        "catalog QA flags remain applicable; high completeness alone is not metrological validation",
                        "no forecast performance or untouched evaluation result is reported by this adapter"]}
    (output/"contract.json").write_text(json.dumps(contract, indent=2)+"\n")
    (output/"audit.json").write_text(json.dumps(audit, indent=2)+"\n")
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    prepare(args.snapshot, args.output)
