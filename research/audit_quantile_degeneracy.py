"""Record, without altering archived fits, observed zero-gradient initialization."""
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd
from sklearn._loss.loss import PinballLoss
from threadpoolctl import threadpool_limits

from solar_recovery.baselines_v3 import model_features
from solar_recovery.pilot import digest


def audit(root):
    root = Path(root)
    records = []
    with threadpool_limits(limits=1):
        for site in ("nist", "colorado"):
            with (root/site/"models.pkl").open("rb") as handle:
                models = pickle.load(handle)
            features = pd.read_parquet(root/site/"features_clean.parquet")
            for name, model in models.items():
                if not name.startswith("quantile_"):
                    continue
                for h, fits in model.models.items():
                    X = model_features(features, model.contract, h)
                    predictions = np.column_stack([m.predict(X) for m in fits])
                    for j, q in enumerate((.05, .1, .25, .5, .75, .9, .95)):
                        records.append({"site": site, "method": name, "horizon": h, "quantile": q,
                            "initial_prediction": float(fits[j]._baseline_prediction[0, 0]),
                            "prediction_min": float(predictions[:, j].min()), "prediction_max": float(predictions[:, j].max()),
                            "prediction_std": float(predictions[:, j].std()),
                            "zero_fraction": float((predictions[:, j] == 0).mean()),
                            "all_quantile_crossing_fraction": float((np.diff(predictions, axis=1) < 0).any(axis=1).mean())})
    frame = pd.DataFrame(records)
    frame.to_csv(root/"quantile_fit_audit.csv", index=False)
    result = {"gradient_probe_y": [0., .1, 1.], "gradient_probe_prediction": [0., 0., 0.],
        "gradient_by_quantile": {str(q): PinballLoss(quantile=q).gradient(np.array([0., .1, 1.]), np.zeros(3)).tolist()
                                 for q in (.05, .1, .25, .5)},
        "nist_constant_zero_medians": frame.loc[frame.site.eq("nist") & frame['quantile'].eq(.5) & frame.zero_fraction.eq(1.)].to_dict("records"),
        "interpretation": "At zero initial prediction the pinned loss gives identical gradients for zero and positive targets. Constant zero median fits are observed on NIST; exact downstream splitting behavior can depend on numerical effects. Do not use this failed quantile baseline to establish a new method's superiority.",
        "source": "https://github.com/scikit-learn/scikit-learn/blob/1.8.0/sklearn/_loss/_loss.pyx.tp",
        "audit_sha256": digest(__file__)}
    (root/"quantile_fit_audit.json").write_text(json.dumps(result, indent=2)+"\n")
    print(f"{root}: {len(frame)} model fits audited; {len(result['nist_constant_zero_medians'])} constant-zero NIST median models", flush=True)


if __name__ == "__main__":
    audit("runs/annual_ac_baselines_v3")
