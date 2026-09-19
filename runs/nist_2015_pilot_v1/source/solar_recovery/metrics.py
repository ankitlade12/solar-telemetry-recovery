"""Scores for the final issued median and central intervals."""
import numpy as np

QUANTILES = np.array([.05, .10, .25, .50, .75, .90, .95])
ALPHAS = np.array([.50, .20, .10])
PAIRS = ((2, 4), (1, 5), (0, 6))


def interval_score(y, lower, upper, alpha):
    if not 0 < alpha < 1 or np.any(np.asarray(lower) > np.asarray(upper)):
        raise ValueError("Invalid interval or level")
    return upper-lower + 2/alpha*(np.maximum(lower-y, 0)+np.maximum(y-upper, 0))


def wis(y, q):
    q = np.asarray(q)
    if q.shape[-1] != 7 or not np.isfinite(q).all() or np.any(np.diff(q, axis=-1)<0):
        raise ValueError("Expected seven finite ordered quantiles")
    y = np.asarray(y)
    value = .5*np.abs(y-q[..., 3])
    for alpha, (lo, hi) in zip(ALPHAS, PAIRS):
        value += alpha/2*interval_score(y, q[..., lo], q[..., hi], alpha)
    return value/3.5


def expand(q, corrections):
    result = np.asarray(q, dtype=float).copy()
    for correction, (lo, hi) in zip(corrections, PAIRS):
        result[lo] -= max(0, correction)
        result[hi] += max(0, correction)
    # Enforce nesting outward; do not silently exchange interval identities.
    result[1] = min(result[1], result[2])
    result[0] = min(result[0], result[1])
    result[5] = max(result[5], result[4])
    result[6] = max(result[6], result[5])
    return np.maximum(result, 0)
