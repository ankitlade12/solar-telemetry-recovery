"""Observable recovery features and explicitly synthetic transport stress tests."""
from collections import deque
from dataclasses import replace

import numpy as np
import pandas as pd

from solar_recovery.baselines_v3 import geometry
from solar_recovery.calibration import state_key, weighted_quantile
from solar_recovery.calibration_v3 import ContextCalibrator, physical_context
from solar_recovery.metrics import ALPHAS
from solar_recovery.replay import HOUR
from solar_recovery.replay_v3 import Fault, VisibleHistory, LAGS, deliver_schedule

FAMILIES = {
    'age': ['rs_age_pv', 'rs_age_irradiance', 'rs_active_pv', 'rs_active_irradiance'],
    'history': ['rs_late_fraction', 'rs_restored_slots', 'rs_restore_order'],
    'transport': ['rs_delay_mean', 'rs_delay_std', 'rs_duplicate_fraction', 'rs_out_of_order_fraction', 'rs_reconnects'],
    'labels': ['rs_pending_labels', 'rs_newest_label_age'],
}


def recovery_features(events, origins, contract, horizons=(1, 2, 3, 4), margin=1):
    """No fault plan or undelivered packet is visible to this observer.

    Missing-history restoration and packet-loss rates are proxies: the true
    queue size and eventual delivery denominator are unknowable at issue time.
    """
    events = sorted(events, key=lambda e: (e.receipt, e.end, e.stream, e.id))
    history, pointer, recent, reconnects = VisibleHistory(margin), 0, deque(), deque()
    seen, latest, pending, labeled = set(), {}, {}, set()
    newest_label, rows = None, []
    solar = {h: geometry(pd.DatetimeIndex(origins).floor('h')+h*HOUR, contract) for h in horizons}
    for index, origin in enumerate(origins):
        while recent and recent[0][0] < origin-24*HOUR:
            recent.popleft()
        while reconnects and reconnects[0] < origin-24*HOUR:
            reconnects.popleft()
        restored_slots = 0
        while pointer < len(events) and events[pointer].receipt <= origin:
            event = events[pointer]
            key = (event.stream, event.end)
            duplicate = key in seen
            out_of_order = event.stream in latest and event.end < latest[event.stream]
            delay = max(0., (event.receipt-event.end).total_seconds()/3600-margin/60)
            late = delay > 1/60
            if not duplicate and late and event.end >= origin-48*HOUR:
                restored_slots += 1
            recent.append((event.receipt, delay, duplicate, out_of_order, late))
            seen.add(key)
            latest[event.stream] = max(event.end, latest.get(event.stream, event.end))
            history.receive(event, origin)
            if event.stream == 'pv' and event.end in pending and event.end not in labeled:
                newest_label = max(event.end, newest_label or event.end)
                labeled.add(event.end)
                del pending[event.end]
            pointer += 1
        was_gap = history.gap.copy()
        state = history.features(origin)
        for stream in ('pv', 'irradiance'):
            if was_gap[stream] and state[stream+'_current']:
                reconnects.append(origin)
            age = state[stream+'_recovery']
            state['rs_age_'+stream] = np.log1p(min(max(age, 0), 168))/np.log(169)
            state['rs_active_'+stream] = float(age >= 0)
        window = [r for r in recent if r[0] >= origin-24*HOUR]
        delays = np.array([r[1] for r in window])
        state.update(rs_late_fraction=np.mean([r[4] for r in window]) if window else 0.,
            rs_restored_slots=min(restored_slots, 50)/50,
            rs_restore_order=float(state['pv_current'])-float(state['irradiance_current']),
            rs_delay_mean=min(delays.mean(), 168)/168 if len(delays) else 0.,
            rs_delay_std=min(delays.std(), 168)/168 if len(delays) else 0.,
            rs_duplicate_fraction=np.mean([r[2] for r in window]) if window else 0.,
            rs_out_of_order_fraction=np.mean([r[3] for r in window]) if window else 0.,
            rs_reconnects=min(len(reconnects), 24)/24,
            rs_pending_labels=min(sum(pending.values()), 96)/96,
            rs_newest_label_age=min((origin-newest_label)/HOUR, 168)/168 if newest_label is not None else 1.)
        rows.append(state)
        # The feature vector is fixed before this origin's new forecasts exist.
        for horizon in horizons:
            target = origin.floor('h')+horizon*HOUR
            if solar[horizon][index] > 0:
                pending[target] = pending.get(target, 0)+1
        # Calibration window is 30 days; expired pending records are not useful support.
        pending = {t: n for t, n in pending.items() if t >= origin-720*HOUR}
    return pd.DataFrame(rows, index=pd.DatetimeIndex(origins, name='origin'))


class RecoveryKernelCalibrator(ContextCalibrator):
    """Fixed continuous feature-family kernel, with availability matching only."""
    def __init__(self, family, **kwargs):
        if family not in {*FAMILIES, 'all'}:
            raise ValueError('Unknown recovery feature family')
        self.keys = sum(FAMILIES.values(), []) if family == 'all' else FAMILIES[family]
        super().__init__('physical_availability', **kwargs)

    def encode(self, features):
        return np.r_[physical_context(features), [features[k] for k in self.keys]]

    def correction(self, origin, horizon, features):
        self.scores[horizon] = [(f, s) for f, s in self.scores[horizon] if origin-self.window*HOUR <= f.origin <= origin]
        pool = self.scores[horizon]
        info = {'pool_size': len(pool), 'matching_size': 0, 'effective_n': 0., 'fallback': 'insufficient_scores'}
        if len(pool) < self.min_scores:
            return np.zeros(3), info
        ages = np.array([(origin-f.origin)/HOUR for f, _ in pool])
        distance = np.sum((np.array([f.context for f, _ in pool])-self.encode(features))**2, axis=1)
        logits = -ages/self.tau-distance/(2*self.bandwidth**2)
        weights = np.exp(logits-logits.max()); weights /= weights.sum()
        coords = (0, 2, 3, 5)
        key = tuple(state_key(features)[i] for i in coords)
        match = np.array([tuple(f.state[i] for i in coords) == key for f, _ in pool])
        strength = 0.
        if match.any():
            local = weights*match; local /= local.sum()
            ess = 1/np.sum(local**2); strength = ess/(ess+self.shrinkage)
            weights = strength*local+(1-strength)*weights
        scores = np.array([s for _, s in pool])
        levels = np.minimum(1., (1-ALPHAS)*(1+1/len(pool)))
        delta = np.array([weighted_quantile(scores[:, k], weights, p) for k, p in enumerate(levels)])
        info.update(matching_size=int(match.sum()), effective_n=float(1/np.sum(weights**2)), mixing_strength=strength,
                    fallback='none' if match.any() else 'global_pool')
        return delta, info

    def issue(self, forecast_id, origin, horizon, base, features, target_daylight, target_end=None):
        result = super().issue(forecast_id, origin, horizon, base, features, target_daylight, target_end)
        if not self.daylight_only or target_daylight:
            target = origin+horizon*HOUR if target_end is None else target_end
            self.pending[target][-1].context = self.encode(features).copy()
        return result


def realistic_faults(truth, contract, start, end, correlated, seed=20261015):
    """Synthetic low-clearness-biased starts; clipped heavy-tail duration distribution."""
    rng = np.random.default_rng(seed)
    origins = pd.date_range(start, end, freq='h', inclusive='left')
    faults = []
    for week in pd.date_range(pd.Timestamp(start).floor('D'), end, freq='7D', inclusive='left'):
        slots = origins[(origins >= week) & (origins < week+pd.Timedelta(days=2))]
        if not len(slots):
            continue
        solar = geometry(slots, contract)
        poa = truth.irradiance.reindex(slots).to_numpy()
        weights = np.ones(len(slots))
        if correlated:
            valid = (solar > .1) & np.isfinite(poa)
            clearness = np.clip(poa/np.maximum(100, 1000*solar), 0, 1)
            weights = np.where(valid, 1+9*(1-clearness), .1)
        origin = slots[rng.choice(len(slots), p=weights/weights.sum())]+pd.Timedelta(minutes=1)
        duration = float(np.clip(rng.lognormal(np.log(12), .9), 2, 96))
        gap = float(rng.uniform(0, 6))
        first, last = origin+duration*HOUR, origin+(duration+gap)*HOUR
        if rng.random() < .5:
            pv, ir = first, last
        else:
            pv, ir = last, first
        faults.append(Fault(origin, pv, ir, 'gradual', float(rng.uniform(5, 60))))
        if rng.random() < .25:
            reconnect = last+2*HOUR
            faults.append(Fault(reconnect, reconnect+HOUR, reconnect+HOUR, 'gradual', 15))
    return faults


def transport_stress(events, faults, seed=20261015):
    rng = np.random.default_rng(seed)
    result = []
    for event in deliver_schedule(events, faults):
        if rng.random() < .03:
            continue
        jitter = min(rng.exponential(5), 60) if rng.random() < .3 else 0.
        delayed = replace(event, receipt=event.receipt+pd.Timedelta(minutes=jitter))
        result.append(delayed)
        if rng.random() < .02:
            result.append(replace(delayed, id=delayed.id+':duplicate', receipt=delayed.receipt+pd.Timedelta(minutes=1)))
    return sorted(result, key=lambda e: (e.receipt, e.end, e.stream, e.id))
