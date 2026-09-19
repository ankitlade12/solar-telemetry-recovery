"""Compare completeness of alternative same-site power channels, without substitution."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from solar_recovery.data import solar_elevation


def audit():
    source = Path("data/raw/pvdaq_4902_2015")
    ids = [82610, 82607, 82633]
    raw = pd.concat([pd.read_parquet(p, columns=["utc_measured_on", "metric_id", "value"],
                                    filters=[("metric_id", "in", ids)])
                     for p in sorted(source.glob("system_4902__date_*.parquet"))], ignore_index=True)
    raw["utc_measured_on"] = pd.to_datetime(raw.utc_measured_on, utc=True)
    assert not raw.groupby(["utc_measured_on", "metric_id"]).value.nunique(dropna=False).gt(1).any()
    raw = raw.drop_duplicates(["utc_measured_on", "metric_id"]).copy()
    raw.loc[~np.isfinite(raw.value) | (raw.value < 0), "value"] = np.nan
    wide = raw.pivot(index="utc_measured_on", columns="metric_id", values="value").sort_index()
    # Same conservative completeness rule, not a validated replacement adapter.
    counts = wide.resample("h", closed="left", label="right").count()
    hourly = wide.resample("h", closed="left", label="right").mean().where(counts.eq(60))
    daylight = solar_elevation(hourly.index-pd.Timedelta(minutes=30), 39.1319, -77.2141) > 0
    names = {82610: "inverter_dc", 82607: "inverter_ac", 82633: "meter_ac"}
    result = {"status": "exploratory completeness only; target semantics and meter sign convention unresolved",
              "used_in_pilot": "82610 inverter DC only", "metrics": {}}
    for metric in ids:
        result["metrics"][metric] = {"label": names[metric], "valid_nonnegative_hours": int(hourly[metric].count()),
            "valid_daylight_hours": int(hourly.loc[daylight, metric].count()), "geometric_daylight_hours": int(daylight.sum()),
            "max_hourly_kw": float(hourly[metric].max()), "monthly_valid_hours": {
                key: int(part.count()) for key, part in hourly[metric].groupby(hourly.index.strftime("%Y-%m"))}}
    Path("research/pvdaq_alternative_power.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    audit()
