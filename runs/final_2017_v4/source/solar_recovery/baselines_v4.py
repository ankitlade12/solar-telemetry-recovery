"""Predeclared previous-day and carry-forward controls for the final evaluation."""
import numpy as np

from .baselines_v3 import DressedPersistence, QuantileForecaster
from .replay_v3 import LAGS


def carry_forward_inputs(features):
    """Fill each lag from an older visible slot, independently at each origin.

    The oldest unavailable slot defaults to zero. This is a simple baseline,
    not an estimate of an unobserved target. Availability indicators are removed
    by making them constant; no future row participates in a fill operation.
    """
    result = features.copy()
    for stream in ("pv", "irradiance"):
        columns = [f"{stream}_lag{lag}" for lag in sorted(LAGS, reverse=True)]
        result[columns] = result[columns].ffill(axis=1).fillna(0.)
        result[f"{stream}_last"] = result[f"{stream}_last"].fillna(0.)
        for suffix in ("age", "transport_age", "current", "recovery", "missing_fraction"):
            result[f"{stream}_{suffix}"] = 0.
    return result


class CarryForwardQuantile(QuantileForecaster):
    def fit(self, features, *args, **kwargs):
        return super().fit(carry_forward_inputs(features), *args, **kwargs)

    def predict(self, features):
        return super().predict(carry_forward_inputs(features))


class DressedPreviousDay(DressedPersistence):
    """Same target hour one day earlier; fall back to latest received PV."""
    def point(self, features, horizon):
        previous = features[f"pv_lag{25-horizon}"].to_numpy()
        fallback = features.pv_last.fillna(0.).to_numpy()
        return np.where(np.isfinite(previous), previous, fallback)
