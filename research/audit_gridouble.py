"""Inspect pinned public GRIDouble files; never infer confirmed units or receipt times."""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import tempfile
import urllib.request
from zoneinfo import ZoneInfo

REVISION = "535f684d43f30e181d882e4ac9c5cf023503b2bf"
HASHES = {
    "README.md": "7e3ab76766189895338c2ae3304f0e3b6dcc73fc3c83d7e64abb23a25e2bade9",
    "Data_Cacak.csv": "8fc4e8dcf54a97891390db321bcbdc5047023f86734a77c71b4add5e1630c760",
    "Data_Kraljevo.csv": "dad38a03f34a6829aa7377d143f0ddbfd2b139ceb25c0a548576bf669cf401ff",
}


def inspect(folder):
    output = {"source_revision": REVISION, "files": {}, "interpretation": {
        "timezone": "Europe/Belgrade with file-order autumn folds is a tested hypothesis, not source-confirmed timestamp semantics.",
        "weather": "README identifies Solcast as meteorological source; on-site irradiance measurement is not established.",
        "units": "No unit conversions applied; source unit claims require reconciliation.",
        "license": "README declares Creative Commons Attribution 4.0 International License.",
        "scope": "Structural data audit only; no forecast performance or instrument validity established."
    }}
    for name, expected in HASHES.items():
        path = folder / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f"Unexpected source bytes: {name}: {digest}")
        entry = {"sha256": digest, "bytes": path.stat().st_size,
                 "url": f"https://raw.githubusercontent.com/vodena/GRIDouble/{REVISION}/data/{name}"}
        output["files"][name] = entry
        if not name.endswith(".csv"):
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        formats = collections.Counter()
        dates = []
        for row in rows:
            for fmt in ("%m/%d/%Y %H:%M", "%m-%d-%y %H:%M"):
                try:
                    parsed = dt.datetime.strptime(row["Datetime"], fmt)
                    formats[fmt] += 1
                    dates.append(parsed)
                    break
                except ValueError:
                    pass
            else:
                raise ValueError(f"Unrecognized timestamp: {row['Datetime']}")
        counts = collections.Counter(dates)
        seen = collections.Counter()
        utc = []
        for value in dates:
            fold = seen[value]
            if fold > 1:
                raise ValueError("More than two copies of one local timestamp")
            seen[value] += 1
            utc.append(value.replace(tzinfo=ZoneInfo("Europe/Belgrade"), fold=fold).astimezone(dt.timezone.utc))
        columns = {}
        for column in rows[0]:
            if column == "Datetime":
                continue
            values = [float(row[column]) for row in rows if row[column].strip()]
            finite = [v for v in values if math.isfinite(v)]
            columns[column] = {
                "empty": sum(not row[column].strip() for row in rows),
                "nonfinite": len(values) - len(finite),
                "min_raw": min(finite), "max_raw": max(finite),
                "zero_count": sum(v == 0 for v in finite),
                "negative_count": sum(v < 0 for v in finite),
            }
        entry.update({
            "rows": len(rows), "columns": columns, "timestamp_formats": dict(formats),
            "first_local": min(dates).isoformat(), "last_local": max(dates).isoformat(),
            "span_days_between_endpoints": (max(dates)-min(dates)).total_seconds()/86400,
            "duplicate_local_times": {k.isoformat(): v for k,v in counts.items() if v > 1},
            "non_hour_local_steps": [{"before": a.isoformat(), "after": b.isoformat(),
                                      "hours": (b-a).total_seconds()/3600}
                                     for a,b in zip(dates,dates[1:]) if b-a != dt.timedelta(hours=1)],
            "hourly_utc_if_belgrade_file_order_folds": all(b-a == dt.timedelta(hours=1) for a,b in zip(utc,utc[1:])),
            "max_abs_ghi_minus_dhi_minus_ebh_raw": max(abs(float(r["GHI"])-float(r["DHI"])-float(r["EBH"])) for r in rows),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-dir", type=Path)
    source.add_argument("--download", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.download:
        with tempfile.TemporaryDirectory(prefix="gridouble-audit-") as directory:
            folder = Path(directory)
            for name in HASHES:
                url = f"https://raw.githubusercontent.com/vodena/GRIDouble/{REVISION}/data/{name}"
                with urllib.request.urlopen(url, timeout=60) as response:
                    (folder/name).write_bytes(response.read())
            result = inspect(folder)
    else:
        result = inspect(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n")
    print(f"Wrote structural audit: {args.output}")


if __name__ == "__main__":
    main()
