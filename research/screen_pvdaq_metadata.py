"""Bounded metadata-only screen; does not inspect forecasting outcomes."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pandas as pd

from solar_recovery.acquire import fetch

SYSTEMS = [4, 10, 33, 50, 51, 1199, 1200, 1201, 1202, 1203, 1208, 1239, 1367, 4902, 4903, 4904]


def main():
    folder = Path("data/metadata/development_screen")
    folder.mkdir(parents=True, exist_ok=True)
    items = [{"key": key} for system in SYSTEMS for key in
             [f"pvdaq/parquet/metrics/metrics__system_{system}__part000.parquet",
              f"pvdaq/csv/system_metadata/{system}_system_metadata.json"]]
    def acquire(item):
        try:
            return fetch(item, folder)
        except Exception as error:
            return {**item, "error": str(error)}
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(acquire, items))
    (folder/"manifest.json").write_text(json.dumps(results, indent=2)+"\n")
    report = []
    for system in SYSTEMS:
        path = folder/f"metrics__system_{system}__part000.parquet"
        meta_path = folder/f"{system}_system_metadata.json"
        if not path.exists() or not meta_path.exists():
            report.append({"system_id": system, "status": "metadata unavailable"})
            continue
        metrics = pd.read_parquet(path)
        mask = metrics.common_name.str.contains("irradiance|^AC power$|^DC power$", case=False, na=False)
        columns = [c for c in ["metric_id", "sensor_name", "common_name", "units", "raw_units", "calc_scale",
                              "calc_offset", "aggregation_type", "source_type", "source_id"] if c in metrics]
        meta = json.loads(meta_path.read_text())
        report.append({"system_id": system, "system": meta.get("System"), "site": meta.get("Site"),
                       "instruments": {k: v for k, v in meta.items() if k in ["Inverters", "Meters", "Other Instruments"]},
                       "channels": json.loads(metrics.loc[mask, columns].to_json(orient="records"))})
    Path("research/pvdaq_metadata_screen.json").write_text(json.dumps(report, indent=2)+"\n")
    for item in report:
        print(item["system_id"], [(c["metric_id"], c["sensor_name"], c["units"], c["calc_scale"])
                                     for c in item.get("channels", [])], flush=True)


if __name__ == "__main__":
    main()
