"""Generate a scientific schematic from explicit synthetic delivery events."""
from dataclasses import asdict
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from solar_recovery.pilot import digest
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import Fault, deliver_schedule


def make():
    root = Path("paper/figures")
    root.mkdir(exist_ok=True)
    zero = pd.Timestamp("2020-06-01T00:00Z")
    ends = pd.date_range(zero-pd.Timedelta(hours=2), periods=15, freq="h")
    frame = pd.DataFrame({"pv": 1., "irradiance": 100.}, index=ends)
    start = zero+pd.Timedelta(minutes=1)
    fault = Fault(start, start+pd.Timedelta(hours=6), start+pd.Timedelta(hours=9), "gradual", 15)
    records = deliver_schedule(observations_from_hourly(frame, 1), [fault])
    table = pd.DataFrame([{"stream": o.stream, "measurement_hour": (o.end-zero)/pd.Timedelta(hours=1),
        "receipt_hour": (o.receipt-zero)/pd.Timedelta(hours=1),
        "backlogged": o.receipt-o.end > pd.Timedelta(minutes=1)} for o in records])
    table.to_csv(root/"receipt_timeline.csv", index=False)
    plt.rcParams.update({"font.size": 7, "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(3.45, 2.25), constrained_layout=True)
    for stream, y, restore in (("pv", 3, 6+1/60), ("irradiance", 1, 9+1/60)):
        part = table.loc[table.stream.eq(stream)]
        ax.fill_between([1/60, restore], y-.85, y+.18, color="#eeeeee", zorder=0)
        for _, row in part.iterrows():
            color = "#2976a3" if row.backlogged else "#9a6845"
            ax.plot([row.measurement_hour, row.receipt_hour], [y, y-.7], color=color,
                    alpha=.6 if row.backlogged else .35, linewidth=.7)
        ax.scatter(part.measurement_hour, [y]*len(part), s=9, color="#555555", zorder=3)
        ax.scatter(part.receipt_hour, [y-.7]*len(part), s=10,
                   color=["#2976a3" if b else "#9a6845" for b in part.backlogged], zorder=3)
        ax.annotate("live resumes", (restore, y-.7), (restore-1.4, y-1.2), fontsize=6,
                    arrowprops={"arrowstyle": "->", "lw": .6})
    ax.set(yticks=[3, 2.3, 1, .3], yticklabels=["PV measured", "PV received", "POA measured", "POA received"],
           xticks=[0, 3, 6, 9, 12], xlabel="Hours relative to interruption", xlim=(-2.4, 12.7), ylim=(-.5, 3.5))
    ax.tick_params(axis="y", length=0)
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.text(0, 3.27, "interrupted", fontsize=6, color="#555555")
    ax.text(8.0, 3.27, "blue: delayed history", fontsize=6, color="#2976a3")
    for ext in ("pdf", "png"):
        fig.savefig(root/f"receipt_timeline.{ext}", dpi=250)
    plt.close(fig)
    (root/"receipt_timeline.json").write_text(json.dumps({"kind": "Explicit synthetic illustration, not observed outage evidence",
        "code_sha256": digest(Path(__file__)), "data_sha256": digest(root/"receipt_timeline.csv"),
        "normal_receipt_minutes": 1, "fault": {k: v.isoformat() if isinstance(v, pd.Timestamp) else v for k, v in asdict(fault).items()}}, indent=2)+"\n")


if __name__ == "__main__":
    make()
