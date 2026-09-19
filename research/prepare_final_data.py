"""Qualify predefined quality/alignment variants without forecast evaluation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.baselines_v3 import geometry
from solar_recovery.data_v2 import SITES, normalize
from solar_recovery.pilot import digest


def prepare(output="data/processed/final_v4"):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use a fresh immutable qualification directory")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for site, system in (("nist", 4902), ("colorado", 4)):
        for year in (2016, 2017):
            snapshot = Path(f"data/raw/pvdaq_{system}_{year}")
            source = json.loads((snapshot/"manifest.json").read_text())
            for item in source["files"]:
                if digest(snapshot/Path(item["key"]).name) != item["sha256"]:
                    raise ValueError("Raw object checksum mismatch")
            previous = Path(f"data/processed/{site}_ac_{year}")
            contract = json.loads((previous/"contract.json").read_text())
            raw = pd.concat([pd.read_parquet(p, columns=["measured_on", "utc_measured_on", "metric_id", "value"],
                    filters=[("metric_id", "in", [SITES[system]["pv"], SITES[system]["irradiance"]])])
                    for p in sorted(snapshot.glob(f"system_{system}__date*.parquet"))], ignore_index=True)
            capacity = contract["capacity_kw_dc"]
            variants = [("primary", contract["quality_bounds"], 0),
                        ("narrow_quality", {"ac_min_kw": -.01*capacity, "ac_max_kw": 1.2*capacity,
                                            "poa_min_w_m2": -10., "poa_max_w_m2": 1500.}, 0)]
            if site == "colorado":
                variants.append(("right_aligned", contract["quality_bounds"], -1))
            reference = None
            for variant, bounds, shift in variants:
                hourly, excluded, audit = normalize(raw, SITES[system], capacity, bounds, shift)
                if variant == "primary":
                    reference = hourly
                    pd.testing.assert_frame_equal(hourly, pd.read_parquet(previous/"hourly.parquet"), check_freq=False)
                aligned = hourly.reindex(reference.index)
                equal = aligned[["pv", "irradiance"]].eq(reference[["pv", "irradiance"]]) | (
                    aligned[["pv", "irradiance"]].isna() & reference[["pv", "irradiance"]].isna())
                audit.update({"site": site, "year": year, "variant": variant,
                    "changed_pv_hours": int((~equal.pv).sum()), "changed_irradiance_hours": int((~equal.irradiance).sum()),
                    "max_absolute_pv_difference_kw": float((aligned.pv-reference.pv).abs().max()),
                    "valid_daylight_targets": int(hourly.loc[geometry(hourly.index, contract) > 0, "pv"].count()),
                    "valid_daylight_joint": int(hourly.loc[geometry(hourly.index, contract) > 0, ["pv", "irradiance"]].notna().all(axis=1).sum())})
                root = output/site/str(year)/variant
                root.mkdir(parents=True)
                hourly.to_parquet(root/"hourly.parquet")
                excluded.to_parquet(root/"excluded_measurements.parquet", index=False)
                updated = dict(contract)
                updated.update({"quality_bounds": bounds, "timestamp_shift_minutes": shift,
                    "timestamp_source": audit["timestamp_source"], "adapter_sha256": digest("solar_recovery/data_v2.py"),
                    "hourly_sha256": digest(root/"hourly.parquet"), "parent_contract_sha256": digest(previous/"contract.json"),
                    "status": "2016 final-training candidate" if year == 2016 else "2017 reserved-performance input; quality inspection only",
                    "variant": variant, "alignment_sensitivity": "Native/UTC stamps shifted -1 minute before hourly grouping" if shift else "Original timestamp-bin definition"})
                (root/"contract.json").write_text(json.dumps(updated, indent=2)+"\n")
                (root/"audit.json").write_text(json.dumps(audit, indent=2)+"\n")
                records.append(audit)
                print(f"Qualified {site}/{year}/{variant}: changed PV {audit['changed_pv_hours']}, irradiance {audit['changed_irradiance_hours']}", flush=True)
    pd.DataFrame(records).to_csv(output/"qualification.csv", index=False)
    (output/"manifest.json").write_text(json.dumps({"status": "input qualification only; no forecast performance accessed",
        "preparer_sha256": digest(__file__), "adapter_sha256": digest("solar_recovery/data_v2.py"), "records": records}, indent=2)+"\n")


if __name__ == "__main__":
    prepare()
