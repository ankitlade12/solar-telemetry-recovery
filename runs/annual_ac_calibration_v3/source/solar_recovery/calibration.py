"""Empirical rolling/context/recovery calibration with receipt-gated labels."""
from dataclasses import dataclass
from collections import defaultdict

import numpy as np

from .metrics import PAIRS, ALPHAS, expand
from .replay import HOUR, utc


def state_key(features):
    result = []
    for stream in ("pv", "irradiance"):
        age = features[f"{stream}_age"]
        recovery = features[f"{stream}_recovery"]
        missing = features[f"{stream}_missing_fraction"]
        result.extend((0 if age == 0 else 1 if age <= 3 else 2,
                       -1 if recovery < 0 else 0 if recovery <= 3 else 1 if recovery <= 12 else 2,
                       0 if missing == 0 else 1 if missing <= .5 else 2))
    return tuple(result)


def context_vector(features):
    # All transformations are fixed in the pilot config, not fitted on test data.
    out = [features["hour_sin"], features["hour_cos"]]
    for stream in ("pv", "irradiance"):
        out.extend((min(features[f"{stream}_age"], 24)/12,
                    max(-1, min(features[f"{stream}_recovery"], 24))/12,
                    features[f"{stream}_missing_fraction"]))
    return np.asarray(out)


def weighted_quantile(values, weights, probability):
    values, weights = np.asarray(values), np.asarray(weights)
    if len(values) == 0 or not 0 <= probability <= 1 or np.any(weights < 0) or not weights.sum() > 0:
        raise ValueError("Invalid empirical quantile")
    order = np.argsort(values, kind="stable")
    cdf = np.cumsum(weights[order])/weights.sum()
    return values[order[min(np.searchsorted(cdf, probability), len(order)-1)]]


@dataclass
class ForecastRecord:
    id: str
    origin: object
    target_end: object
    horizon: int
    base: np.ndarray
    state: tuple
    context: np.ndarray


class OnlineCalibrator:
    def __init__(self, method="rolling", window_hours=720, tau_hours=336, shrinkage=50., bandwidth=1.):
        if method not in {"rolling", "context", "recovery"}:
            raise ValueError("Unknown calibration method")
        self.method, self.window = method, window_hours
        self.tau, self.shrinkage, self.bandwidth = tau_hours, shrinkage, bandwidth
        self.pending = defaultdict(list)
        self.scores = defaultdict(list)
        self.received = {}
        self.issued = set()
        self.update_count = 0

    def receive(self, observation, now):
        now = utc(now)
        if observation.receipt > now or observation.end > now:
            raise ValueError("Calibration cannot receive an unavailable label")
        if observation.stream != "pv":
            return
        if observation.id in self.received:
            if self.received[observation.id] != observation:
                raise ValueError("Conflicting label revision")
            return
        self.received[observation.id] = observation
        for forecast in self.pending.pop(observation.end, []):
            scores = np.asarray([max(forecast.base[lo]-observation.value,
                                     observation.value-forecast.base[hi]) for lo, hi in PAIRS])
            self.scores[forecast.horizon].append((forecast, scores))
            self.update_count += 1

    def correction(self, origin, horizon, features):
        origin = utc(origin)
        lower = (origin-self.window*HOUR).value
        self.scores[horizon] = [(f, s) for f, s in self.scores[horizon]
                                if lower <= f.origin.value <= origin.value]
        pool = self.scores[horizon]
        info = {"pool_size": len(pool), "matching_size": 0, "effective_n": 0.,
                "freshest_score_age_h": np.nan, "fallback": "no_eligible_scores"}
        if not pool:
            # Explicit pilot fallback: unchanged base intervals, marked unsupported.
            return np.zeros(3), info
        age = (origin.value-np.array([f.origin.value for f, _ in pool]))/HOUR.value
        weights = np.exp(-age/self.tau)
        weights /= weights.sum()
        key = state_key(features)
        match = np.array([f.state == key for f, _ in pool])
        if self.method == "context":
            distance = np.sum((np.array([f.context for f, _ in pool])-context_vector(features))**2, axis=1)
            log_weights = -age/self.tau-distance/(2*self.bandwidth**2)
            weights = np.exp(log_weights-log_weights.max())
            weights /= weights.sum()
        if self.method == "recovery" and match.any():
            local = weights*match
            local /= local.sum()
            effective_n = 1/np.sum(local**2)
            strength = effective_n/(effective_n+self.shrinkage)
            weights = strength*local+(1-strength)*weights
        scores = np.array([s for _, s in pool])
        correction = np.array([max(0., weighted_quantile(scores[:, k], weights, 1-alpha))
                               for k, alpha in enumerate(ALPHAS)])
        info.update({"matching_size": int(match.sum()), "effective_n": float(1/np.sum(weights**2)),
                     "freshest_score_age_h": float(age.min()),
                     "fallback": "global_pool" if self.method == "recovery" and not match.any() else "none"})
        return correction, info

    def issue(self, forecast_id, origin, horizon, base, features):
        origin = utc(origin)
        if forecast_id in self.issued:
            raise ValueError("Forecast IDs must be unique")
        self.issued.add(forecast_id)
        correction, info = self.correction(origin, horizon, features)
        base = np.asarray(base).copy()
        record = ForecastRecord(forecast_id, origin, origin+horizon*HOUR, horizon,
                                base, state_key(features), context_vector(features))
        self.pending[record.target_end].append(record)
        return expand(base, correction), info
