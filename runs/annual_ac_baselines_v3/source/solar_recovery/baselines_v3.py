"""Full-season, causal development baselines; no future measured weather inputs.

MI is an explicitly adapted input-imputation comparator, not a reproduction:
Pashmchi et al., https://arxiv.org/abs/2603.15564 (2026). We retain observed
training targets and extend donor sampling to missing irradiance/joint gaps.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neighbors import NearestNeighbors

from .data import solar_elevation
from .replay import HOUR, utc
from .replay_v3 import LAGS

QUANTILES = np.array([.05, .1, .25, .5, .75, .9, .95])
PROFILES = {
    "compact": {"max_iter": 150, "max_leaf_nodes": 15, "min_samples_leaf": 40, "learning_rate": .05},
    "flexible": {"max_iter": 250, "max_leaf_nodes": 31, "min_samples_leaf": 40, "learning_rate": .05},
}


def geometry(ends, contract):
    elevation = solar_elevation(pd.DatetimeIndex(ends)-HOUR/2, contract["latitude"], contract["longitude"])
    return np.maximum(0., np.sin(np.deg2rad(elevation)))


def target_ends(features, horizon):
    return features.index.floor("h")+horizon*HOUR


def model_features(features, contract, horizon):
    result = features[[c for c in features if not c.endswith("_recovery")]].copy()
    for c in result:
        if c.startswith("pv_") and ("_lag" in c or c.endswith("_last")):
            result[c] /= contract["capacity_kw_dc"]
        elif c.startswith("irradiance_") and ("_lag" in c or c.endswith("_last")):
            result[c] /= 1000.
        elif c.endswith("_age"):
            result[c] = np.minimum(result[c], 168.)/24.
    ends = target_ends(features, horizon)
    result["target_solar_sine"] = geometry(ends, contract)
    result["recent_solar_sine"] = geometry(features.index.floor("h"), contract)
    result["target_hour_sin"] = np.sin(2*np.pi*ends.hour/24)
    result["target_hour_cos"] = np.cos(2*np.pi*ends.hour/24)
    return result


def training_table(features, truth, contract, horizon, train_end):
    ends = target_ends(features, horizon)
    y = truth.pv.reindex(ends).to_numpy()/contract["capacity_kw_dc"]
    selected = (ends <= utc(train_end)) & (features.index < utc(train_end)) & np.isfinite(y)
    return features.iloc[np.flatnonzero(selected)], y[selected]


class QuantileForecaster:
    def __init__(self, profile="compact", seed=20260911):
        self.profile, self.seed = profile, seed
        self.models, self.counts = {}, {}

    def fit(self, features, truth, contract, train_end, horizons=(1, 2, 3, 4)):
        self.contract = contract
        for horizon in horizons:
            eligible, y = training_table(features, truth, contract, horizon, train_end)
            X = model_features(eligible, contract, horizon)
            self.models[horizon] = []
            self.counts[horizon] = {"rows": len(y), "unique_targets": len(target_ends(eligible, horizon).unique())}
            for quantile in QUANTILES:
                model = HistGradientBoostingRegressor(loss="quantile", quantile=float(quantile),
                    early_stopping=False, random_state=self.seed, **PROFILES[self.profile])
                model.fit(X, y)
                self.models[horizon].append(model)
        return self

    def predict(self, features):
        capacity = self.contract["capacity_kw_dc"]
        return {h: np.maximum(0., np.sort(np.column_stack([m.predict(model_features(features, self.contract, h))
                    for m in models]), axis=1))*capacity for h, models in self.models.items()}


def donor_calendar(ends, contract):
    ends = pd.DatetimeIndex(ends)
    return np.column_stack([geometry(ends, contract), np.sin(2*np.pi*ends.hour/24),
        np.cos(2*np.pi*ends.hour/24), np.sin(2*np.pi*ends.dayofyear/365.25),
        np.cos(2*np.pi*ends.dayofyear/365.25)])


class LagDonorImputer:
    """Training-only donor pairs; retain all observed input entries exactly.

    PV-only gap: nearest measured irradiance. Irradiance-only gap: nearest PV.
    Both absent: nearest calendar/solar-geometry vectors, sample a joint pair.
    Mean mode averages the same donor set. Sample mode draws uniformly, with
    replacement. The joint extension is an engineering comparator, not new MI.
    """
    def __init__(self, truth, contract, train_end, k=50):
        if not isinstance(k, int) or k < 1:
            raise ValueError("k must be a positive integer")
        self.contract, self.k = contract, k
        valid = truth.loc[truth.index <= utc(train_end), ["pv", "irradiance"]].dropna()
        if len(valid) < k:
            raise ValueError("Insufficient training donor pairs")
        self.donor_ends = valid.index.copy()
        self.pairs = valid.to_numpy()
        self.indices = {
            "pv": NearestNeighbors(n_neighbors=k).fit(self.pairs[:, 1:2]/1000.),
            "irradiance": NearestNeighbors(n_neighbors=k).fit(self.pairs[:, 0:1]/contract["capacity_kw_dc"]),
            "joint": NearestNeighbors(n_neighbors=k).fit(donor_calendar(valid.index, contract)),
        }

    def transform(self, features, sample=False, seed=20260911):
        rng = np.random.default_rng(seed)
        result = features.copy()
        for lag in LAGS:
            cols = [f"pv_lag{lag}", f"irradiance_lag{lag}"]
            values = result[cols].to_numpy(copy=True)
            pv_missing, ir_missing = ~np.isfinite(values[:, 0]), ~np.isfinite(values[:, 1])
            for kind, mask, column in (("pv", pv_missing & ~ir_missing, 0),
                                      ("irradiance", ir_missing & ~pv_missing, 1),
                                      ("joint", pv_missing & ir_missing, None)):
                rows = np.flatnonzero(mask)
                if not len(rows):
                    continue
                if kind == "pv":
                    query = values[rows, 1:2]/1000.
                elif kind == "irradiance":
                    query = values[rows, 0:1]/self.contract["capacity_kw_dc"]
                else:
                    query = donor_calendar(features.index[rows].floor("h")-(lag-1)*HOUR, self.contract)
                neighbors = self.indices[kind].kneighbors(query, return_distance=False)
                if sample:
                    completed = self.pairs[neighbors[np.arange(len(rows)), rng.integers(self.k, size=len(rows))]]
                else:
                    completed = self.pairs[neighbors].mean(axis=1)
                if column is None:
                    values[rows] = completed
                else:
                    values[rows, column] = completed[:, column]
            result[cols] = values
        return result


class ImputedForecaster:
    """One mean-imputed training fit; SI versus MI test-input ablation (Setup 2).

    Within variance is training residual MSE. MI normal variance adds
    (1+1/B)*sample variance of predicted means. Nonnegative quantile projection
    is declared and common across baselines; no normal coverage guarantee.
    """
    def __init__(self, profile="compact", seed=20260911, k=50, rounds=10):
        self.profile, self.seed, self.k, self.rounds = profile, seed, k, rounds
        if rounds < 2:
            raise ValueError("Multiple imputation needs at least two rounds")
        self.models, self.variance = {}, {}

    def fit(self, features, truth, contract, train_end, horizons=(1, 2, 3, 4)):
        self.contract = contract
        self.imputer = LagDonorImputer(truth, contract, train_end, self.k)
        completed = self.imputer.transform(features)
        for horizon in horizons:
            eligible, y = training_table(completed, truth, contract, horizon, train_end)
            X = model_features(eligible, contract, horizon)
            model = HistGradientBoostingRegressor(loss="squared_error", early_stopping=False,
                    random_state=self.seed, **PROFILES[self.profile]).fit(X, y)
            self.models[horizon] = model
            self.variance[horizon] = float(np.mean((model.predict(X)-y)**2))
        return self

    def predict(self, features):
        mean_completed = self.imputer.transform(features)
        single = {h: model.predict(model_features(mean_completed, self.contract, h)) for h, model in self.models.items()}
        multiple = {h: [] for h in self.models}
        for b in range(self.rounds):
            sample = self.imputer.transform(features, sample=True, seed=self.seed+b)
            for h, model in self.models.items():
                multiple[h].append(model.predict(model_features(sample, self.contract, h)))
        capacity = self.contract["capacity_kw_dc"]
        result = {"single_imputation": {}, "multiple_imputation": {}}
        for h in self.models:
            means = np.array(multiple[h])
            variance = self.variance[h]+(1+1/self.rounds)*means.var(axis=0, ddof=1)
            result["single_imputation"][h] = np.maximum(0., single[h][:, None]+np.sqrt(self.variance[h])*norm.ppf(QUANTILES))*capacity
            result["multiple_imputation"][h] = np.maximum(0., means.mean(axis=0)[:, None]+np.sqrt(variance)[:, None]*norm.ppf(QUANTILES))*capacity
        return result


class DressedPersistence:
    """Last received PV, optionally scaled by a capped geometric solar ratio.

    Three target-solar strata of training residual quantiles provide uncertainty.
    The ratio uses known geometry at the last received PV bin and target bin;
    denominator floor .1 and ratio cap 3 are fixed engineering choices.
    """
    def __init__(self, geometric=False):
        self.geometric, self.residuals = geometric, {}

    def point(self, features, horizon):
        last = features.pv_last.fillna(0.).to_numpy()
        if self.geometric:
            age = np.minimum(features.pv_age.to_numpy(), 24.*365.)
            last_ends = features.index.floor("h")-pd.to_timedelta(age, unit="h")
            ratio = geometry(target_ends(features, horizon), self.contract)/np.maximum(.1, geometry(last_ends, self.contract))
            last = last*np.minimum(3., ratio)
        return last

    def strata(self, features, horizon):
        return np.digitize(geometry(target_ends(features, horizon), self.contract), [.2, .6])

    def fit(self, features, truth, contract, train_end, horizons=(1, 2, 3, 4)):
        self.contract = contract
        for h in horizons:
            eligible, y = training_table(features, truth, contract, h, train_end)
            residual = y*contract["capacity_kw_dc"]-self.point(eligible, h)
            strata = self.strata(eligible, h)
            self.residuals[h] = np.array([np.quantile(residual[strata == k] if (strata == k).any() else residual, QUANTILES)
                                         for k in range(3)])
        return self

    def predict(self, features):
        return {h: np.maximum(0., self.point(features, h)[:, None]+values[self.strata(features, h)])
                for h, values in self.residuals.items()}
