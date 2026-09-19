"""Describe recorded AC zeros without assuming they are errors or imputing truth."""
import json
from pathlib import Path

import pandas as pd

from solar_recovery.baselines_v3 import geometry
from solar_recovery.pilot import digest

rows = []
inputs = {}
for site in ("nist", "colorado"):
    for year in (2015, 2016):
        root = Path(f"data/processed/{site}_ac_{year}")
        contract = json.loads((root/"contract.json").read_text())
        inputs[str(root)] = digest(root/"hourly.parquet")
        frame = pd.read_parquet(root/"hourly.parquet")
        frame = frame.loc[frame.index.year == year].copy()
        frame["month"] = frame.index.month
        frame["daylight"] = geometry(frame.index, contract) > 0
        for month, part in frame.groupby("month"):
            day = part.loc[part.daylight]
            rows.append({"site": site, "year": year, "month_utc": month,
                "daylight_bins": len(day), "valid_daylight_pv": int(day.pv.count()),
                "valid_daylight_joint": int(day[["pv", "irradiance"]].notna().all(axis=1).sum()),
                "zero_daylight_pv": int(day.pv.eq(0).sum()),
                "zero_pv_irradiance_gt200": int((day.pv.eq(0) & day.irradiance.gt(200)).sum()),
                "missing_irradiance_at_zero": int((day.pv.eq(0) & day.irradiance.isna()).sum()),
                "signed_mean_negative_at_zero": int((day.pv.eq(0) & day.pv_signed_mean_kw.lt(0)).sum())})
pd.DataFrame(rows).to_csv("research/ac_zero_episode_audit.csv", index=False)
Path("research/ac_zero_episode_audit.json").write_text(json.dumps({"input_sha256": inputs,
    "source_sha256": digest(__file__), "monthly_records": rows,
    "interpretation": "Recorded zeros are retained. High-irradiance zeros may represent plant unavailability, snow/shading, meter issues or other causes; these data alone do not establish the cause. Missing irradiance cannot certify normal generation conditions. This audit does not relabel or remove zero targets.",
    "next_sensitivity": "Quantify how source-year/long-zero episodes affect fitted baselines; retain an observed-target primary analysis and report any exclusion sensitivity explicitly."}, indent=2)+"\n")
print(pd.DataFrame(rows).groupby(["site", "year"])[["valid_daylight_pv", "zero_daylight_pv", "zero_pv_irradiance_gt200"]].sum().to_string())
