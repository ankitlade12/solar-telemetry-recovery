"""Matched physical-context/recovery and full-lag-mask empirical controls.

These are explicitly specified rolling weighted-score comparisons, not exact
reproductions of published CACP or mask-conditional conformal algorithms. They
make no conditional-coverage or exchangeability guarantee.
"""
import numpy as np

from .calibration import state_key, weighted_quantile
from .calibration_v2 import SignedCalibrator
from .metrics import ALPHAS, PAIRS
from .replay import HOUR, utc
from .replay_v3 import LAGS


def physical_context(features):
    """Physical/forecast/missingness context, deliberately excluding recovery age.

    Inputs are normalized by documented nameplate and irradiance units by the
    runner. No normalization is fitted on evaluation targets.
    """
    keys = ["target_solar_sine", "base_median_normalized", "base_width90_normalized",
            "hour_sin", "hour_cos", "year_sin", "year_cos"]
    values = [float(features[k]) for k in keys]
    ir = features["irradiance_lag1"]
    values.extend([float(ir)/1000. if np.isfinite(ir) else 0., float(not np.isfinite(ir))])
    for stream in ("pv", "irradiance"):
        values.extend([min(float(features[f"{stream}_age"]), 24.)/24., float(features[f"{stream}_missing_fraction"])])
    values = np.array(values)
    if not np.isfinite(values).all():
        raise ValueError("Context must be finite and based on visible inputs")
    return values


def full_mask(features):
    return tuple(bool(np.isfinite(features[f"{stream}_lag{lag}"]))
                 for stream in ("pv", "irradiance") for lag in LAGS)


class ContextCalibrator(SignedCalibrator):
    def __init__(self, conditioning="physical", **kwargs):
        if conditioning not in {"physical", "physical_recovery", "mask50"}:
            raise ValueError("Unknown conditioning")
        super().__init__(method="context" if conditioning != "mask50" else "mask", **kwargs)
        self.conditioning = conditioning

    def correction(self, origin, horizon, features):
        lower = (origin-self.window*HOUR).value
        self.scores[horizon] = [(f, s) for f, s in self.scores[horizon] if lower <= f.origin.value <= origin.value]
        pool = self.scores[horizon]
        info = {"pool_size": len(pool), "matching_size": 0, "effective_n": 0.,
                "freshest_score_age_h": np.nan, "fallback": "insufficient_scores"}
        if len(pool) < self.min_scores:
            return np.zeros(3), info
        age = (origin.value-np.array([f.origin.value for f, _ in pool]))/HOUR.value
        logits = -age/self.tau
        if self.conditioning != "mask50":
            distance = np.sum((np.array([f.context for f, _ in pool])-physical_context(features))**2, axis=1)
            logits -= distance/(2*self.bandwidth**2)
        weights = np.exp(logits-logits.max())
        weights /= weights.sum()
        key = full_mask(features) if self.conditioning == "mask50" else state_key(features)
        match = np.array([(f.mask if self.conditioning == "mask50" else f.state) == key for f, _ in pool])
        local_used = self.conditioning in {"mask50", "physical_recovery"}
        if local_used and match.any():
            local = weights*match
            local /= local.sum()
            ess = 1/np.sum(local**2)
            strength = ess/(ess+self.shrinkage)
            weights = strength*local+(1-strength)*weights
        scores = np.array([s for _, s in pool])
        levels = np.minimum(1., (1-ALPHAS)*(1+1/len(pool)))
        delta = np.array([weighted_quantile(scores[:, k], weights, p) for k, p in enumerate(levels)])
        info.update({"matching_size": int(match.sum()), "effective_n": float(1/np.sum(weights**2)),
                     "freshest_score_age_h": float(age.min()), "fallback": "global_pool" if local_used and not match.any() else "none"})
        return delta, info

    def issue(self, forecast_id, origin, horizon, base, features, target_daylight, target_end=None):
        # Validate the encoder before any forecast/pending state is committed.
        context, mask = physical_context(features), full_mask(features)
        output = super().issue(forecast_id, origin, horizon, base, features, target_daylight, target_end)
        if not self.daylight_only or target_daylight:
            target = utc(origin)+horizon*HOUR if target_end is None else utc(target_end)
            record = self.pending[target][-1]
            record.context, record.mask = context.copy(), mask
        return output
