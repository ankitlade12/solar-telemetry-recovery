"""Post-review diagnostics without changing the frozen calibration implementation."""
import numpy as np

from solar_recovery.calibration import state_key
from solar_recovery.calibration_v3 import ContextCalibrator, physical_context
from solar_recovery.replay import HOUR


class DiagnosticCalibrator(ContextCalibrator):
    """Expose pre-mixture support; preserve inherited predictions and receipt gating."""

    def __init__(self, conditioning, **kwargs):
        if conditioning not in {"physical_availability", "physical_recovery"}:
            raise ValueError("Revision diagnostics require a matched conditioned method")
        super().__init__(conditioning, **kwargs)

    def correction(self, origin, horizon, features):
        delta, info = super().correction(origin, horizon, features)
        info.update(local_effective_n=0., mixing_strength=0., global_effective_n=0.)
        pool = self.scores[horizon]
        if len(pool) < self.min_scores:
            return delta, info
        age = (origin.value-np.array([f.origin.value for f, _ in pool]))/HOUR.value
        distance = np.sum((np.array([f.context for f, _ in pool])-physical_context(features))**2, axis=1)
        logits = -age/self.tau-distance/(2*self.bandwidth**2)
        weights = np.exp(logits-logits.max())
        weights /= weights.sum()
        key = state_key(features)
        saved = [f.state for f, _ in pool]
        if self.conditioning == "physical_availability":
            key = tuple(key[i] for i in (0, 2, 3, 5))
            saved = [tuple(value[i] for i in (0, 2, 3, 5)) for value in saved]
        match = np.array([value == key for value in saved])
        info["global_effective_n"] = float(1/np.sum(weights**2))
        if match.any():
            local = weights*match
            local /= local.sum()
            ess = float(1/np.sum(local**2))
            info.update(local_effective_n=ess, mixing_strength=ess/(ess+self.shrinkage))
        return delta, info
