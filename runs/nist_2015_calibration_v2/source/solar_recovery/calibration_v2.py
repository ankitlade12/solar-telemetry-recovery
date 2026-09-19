"""Signed, receipt-gated empirical calibration for development experiments.

CQR: Romano, Patterson & Candes (2019), https://arxiv.org/abs/1905.03222
ACI update: Gibbs & Candes (2021), https://arxiv.org/abs/2106.00170
Weighted/windowed variants and bounded delayed ACI here have no asserted
exchangeability, conditional-coverage or original ACI guarantee.
"""
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .calibration import context_vector, state_key, weighted_quantile
from .metrics import ALPHAS, PAIRS
from .replay import HOUR, LAGS, utc


def signed_adjustment(base, correction):
    """Signed CQR adjustment, enlarged as needed to contain median and nest.

    Repairs never remove points from any adjusted interval. Nonnegative clipping
    assumes a nonnegative target; do not use this adapter for signed net power.
    """
    base, correction = np.asarray(base, dtype=float), np.asarray(correction, dtype=float)
    if base.shape != (7,) or correction.shape != (3,) or not np.isfinite(base).all() or not np.isfinite(correction).all():
        raise ValueError("Expected seven finite base quantiles and three finite corrections")
    if base[0] < 0 or np.any(np.diff(base) < 0):
        raise ValueError("Base quantiles must be nonnegative and ordered")
    adjusted = base.copy()
    for delta, (lo, hi) in zip(correction, PAIRS):
        adjusted[lo] -= delta
        adjusted[hi] += delta
    raw = adjusted.copy()
    # Work outward from the unchanged median, not by swapping quantile identities.
    for j in (2, 1, 0):
        adjusted[j] = min(adjusted[j], adjusted[j+1])
    for j in (4, 5, 6):
        adjusted[j] = max(adjusted[j], adjusted[j-1])
    adjusted = np.maximum(adjusted, 0)
    return adjusted, bool(np.any(adjusted != raw))


def mask_key(features):
    return tuple(bool(np.isfinite(features[f"{stream}_lag{lag}"]))
                 for stream in ("pv", "irradiance") for lag in LAGS)


@dataclass
class IssuedForecast:
    id: str
    origin: object
    target_end: object
    horizon: int
    base: np.ndarray
    final: np.ndarray
    state: tuple
    mask: tuple
    context: np.ndarray


class SignedCalibrator:
    METHODS = {"rolling", "recency", "context", "mask", "recovery", "aci_bounded"}

    def __init__(self, method="rolling", daylight_only=True, window_hours=720,
                 tau_hours=336, shrinkage=50., bandwidth=1., min_scores=30,
                 gamma=.005, alpha_bounds=(.01, .99), expansion_only=False):
        if method not in self.METHODS:
            raise ValueError("Unknown calibration method")
        if window_hours <= 0 or tau_hours <= 0 or bandwidth <= 0 or shrinkage <= 0 or min_scores < 1:
            raise ValueError("Invalid calibration support/weight configuration")
        if not 0 <= gamma < 1 or not 0 < alpha_bounds[0] < alpha_bounds[1] < 1:
            raise ValueError("Invalid bounded ACI configuration")
        self.method, self.daylight_only = method, daylight_only
        self.expansion_only = expansion_only
        self.window, self.tau, self.shrinkage, self.bandwidth = window_hours, tau_hours, shrinkage, bandwidth
        self.min_scores, self.gamma, self.alpha_bounds = min_scores, gamma, alpha_bounds
        self.pending = defaultdict(list)
        self.scores = defaultdict(list)
        self.alpha = defaultdict(lambda: ALPHAS.copy())
        self.ids, self.labels, self.issued = {}, {}, set()
        self.last_now = None
        self.update_count = 0
        self.alpha_clip_count = 0

    def _clock(self, now):
        now = utc(now)
        if self.last_now is not None and now < self.last_now:
            raise ValueError("Calibration clock cannot go backward")
        self.last_now = now
        return now

    def receive(self, observation, now):
        now = self._clock(now)
        if observation.receipt > now or observation.end > now:
            raise ValueError("Unavailable label")
        if observation.stream != "pv":
            return
        if observation.id in self.ids:
            if self.ids[observation.id] != observation:
                raise ValueError("Conflicting label revision")
            return
        if observation.end in self.labels and self.labels[observation.end] != observation.value:
            raise ValueError("Conflicting same-target label")
        self.ids[observation.id] = observation
        self.labels[observation.end] = observation.value
        for record in self.pending.pop(observation.end, []):
            scores = np.array([max(record.base[lo]-observation.value,
                                   observation.value-record.base[hi]) for lo, hi in PAIRS])
            self.scores[record.horizon].append((record, scores))
            if self.method == "aci_bounded":
                error = np.array([not record.final[lo] <= observation.value <= record.final[hi] for lo, hi in PAIRS])
                updated = self.alpha[record.horizon]+self.gamma*(ALPHAS-error)
                clipped = np.clip(updated, *self.alpha_bounds)
                self.alpha_clip_count += int(np.any(updated != clipped))
                self.alpha[record.horizon] = clipped
            self.update_count += 1

    def correction(self, origin, horizon, features):
        lower = (origin-self.window*HOUR).value
        self.scores[horizon] = [(f, s) for f, s in self.scores[horizon] if lower <= f.origin.value <= origin.value]
        pool = self.scores[horizon]
        info = {"pool_size": len(pool), "matching_size": 0, "effective_n": 0.,
                "freshest_score_age_h": np.nan, "fallback": "insufficient_scores"}
        if len(pool) < self.min_scores:
            return np.zeros(3), info
        age = (origin.value-np.array([f.origin.value for f, _ in pool]))/HOUR.value
        # Uniform rolling baseline; recency weighting is used by conditioned variants.
        weights = np.ones(len(pool))/len(pool)
        state, mask = state_key(features), mask_key(features)
        match = np.array([f.mask == mask if self.method == "mask" else f.state == state for f, _ in pool])
        if self.method in {"recency", "context", "mask", "recovery"}:
            logits = -age/self.tau
            if self.method == "context":
                distance = np.sum((np.array([f.context for f, _ in pool])-context_vector(features))**2, axis=1)
                logits -= distance/(2*self.bandwidth**2)
            weights = np.exp(logits-logits.max())
            weights /= weights.sum()
        if self.method in {"mask", "recovery"} and match.any():
            local = weights*match
            local /= local.sum()
            ess = 1/np.sum(local**2)
            strength = ess/(ess+self.shrinkage)
            weights = strength*local+(1-strength)*weights
        alphas = self.alpha[horizon] if self.method == "aci_bounded" else ALPHAS
        # Sample-size adjustment matches the ordinary empirical CQR rank when
        # weights are uniform and the requested rank is finite. Upper ranks are
        # capped at the largest observed score; this is an explicit bounded rule.
        levels = np.minimum(1., (1-alphas)*(1+1/len(pool)))
        scores = np.array([s for _, s in pool])
        delta = np.array([weighted_quantile(scores[:, k], weights, level) for k, level in enumerate(levels)])
        if self.expansion_only:
            delta = np.maximum(delta, 0)
        info.update({"matching_size": int(match.sum()), "effective_n": float(1/np.sum(weights**2)),
                     "freshest_score_age_h": float(age.min()),
                     "fallback": "global_pool" if self.method in {"mask", "recovery"} and not match.any() else "none"})
        return delta, info

    def issue(self, forecast_id, origin, horizon, base, features, target_daylight):
        origin = self._clock(origin)
        if forecast_id in self.issued:
            raise ValueError("Forecast IDs must be unique")
        if not isinstance(horizon, int) or horizon < 1:
            raise ValueError("Horizon must be a positive integer number of hours")
        self.issued.add(forecast_id)
        eligible = not self.daylight_only or target_daylight
        if eligible:
            correction, info = self.correction(origin, horizon, features)
        else:
            correction = np.zeros(3)
            info = {"pool_size": 0, "matching_size": 0, "effective_n": 0.,
                    "freshest_score_age_h": np.nan, "fallback": "outside_daylight_scope"}
        final, repaired = signed_adjustment(base, correction)
        if eligible:
            record = IssuedForecast(forecast_id, origin, origin+horizon*HOUR, np.int64(horizon).item(),
                                    np.asarray(base).copy(), final.copy(), state_key(features),
                                    mask_key(features), context_vector(features))
            self.pending[record.target_end].append(record)
        info.update({"correction50": float(correction[0]), "correction80": float(correction[1]),
                     "correction90": float(correction[2]), "nesting_repaired": repaired,
                     "alpha50": float(self.alpha[horizon][0]), "alpha80": float(self.alpha[horizon][1]),
                     "alpha90": float(self.alpha[horizon][2]), "alpha_clip_count": self.alpha_clip_count})
        return final, info
