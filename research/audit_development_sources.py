"""Source-channel and timestamp qualification, without forecast performance."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.pilot import digest

CHANNELS = {4: [313, 314, 315], 1200: [2751, 2752, 2753, 4197], 4902: [82595, 82607, 82610, 82633]}


def audit(system):
    source = Path(f"data/raw/pvdaq_{system}_2016")
    manifest = json.loads((source/"manifest.json").read_text())
    for item in manifest["files"]:
        assert digest(source/Path(item["key"]).name) == item["sha256"]
    raw = pd.concat([pd.read_parquet(path, columns=["measured_on", "utc_measured_on", "metric_id", "value"],
                                    filters=[("metric_id", "in", CHANNELS[system])])
                     for path in sorted(source.glob(f"system_{system}__date*.parquet"))], ignore_index=True)
    for column in ["measured_on", "utc_measured_on"]:
        raw[column] = pd.to_datetime(raw[column])
    metrics = pd.read_parquet(source/f"metrics__system_{system}__part000.parquet").set_index("metric_id")
    out = {"system_id": system, "year": 2016, "source_manifest_sha256": digest(source/"manifest.json"), "channels": {}}
    for metric in CHANNELS[system]:
        part = raw[raw.metric_id.eq(metric)]
        values = part.value
        timestamps = part.utc_measured_on if part.utc_measured_on.notna().all() else part.measured_on
        steps = timestamps.drop_duplicates().sort_values().diff().dt.total_seconds().value_counts().head(4)
        out["channels"][metric] = {"sensor_name": str(metrics.loc[metric, "sensor_name"]),
            "units": str(metrics.loc[metric, "units"]), "rows": len(part),
            "utc_timestamp_missing": int(part.utc_measured_on.isna().sum()),
            "unique_native_timestamps": int(part.measured_on.nunique()),
            "conflicting_native_timestamp_pairs": int(part.groupby("measured_on").value.nunique(dropna=False).gt(1).sum()),
            "negative_values": int(values.lt(0).sum()), "nonfinite_values": int((~np.isfinite(values)).sum()),
            "value_quantiles": {str(q): float(values.quantile(q)) for q in [0, .01, .5, .99, 1]} if len(part) else {},
            "dominant_unique_timestamp_steps_seconds": {str(k): int(v) for k, v in steps.items()},
            "rows_by_native_month": {f"{int(k)//100:04d}-{int(k)%100:02d}": int(v) for k, v in
                part.groupby(part.measured_on.dt.year*100+part.measured_on.dt.month).size().items()}}
    print(f"Completed source qualification for {system}", flush=True)
    return out


if __name__ == "__main__":
    results = [audit(system) for system in CHANNELS]
    Path("research/development_source_audit.json").write_text(json.dumps(results, indent=2)+"\n")
    for result in results:
        for metric, channel in result["channels"].items():
            print(result["system_id"], metric, channel["rows"], "missing UTC", channel["utc_timestamp_missing"],
                  "negative", channel["negative_values"], flush=True)
