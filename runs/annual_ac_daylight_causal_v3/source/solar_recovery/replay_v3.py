"""Versioned hourly replay with a release margin and independent backfill queue.

The scheduler knows injected faults. VisibleHistory never receives that plan.
All history slots refer to completed bins, even when forecasts issue at HH:01.
"""
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .replay import HOUR, STREAMS, VisibleHistory as OriginalHistory, utc

LAGS = (*range(1, 25), 48)


@dataclass(frozen=True)
class Fault:
    start: pd.Timestamp
    pv_return: pd.Timestamp
    irradiance_return: pd.Timestamp
    mode: str = "immediate"
    backfill_spacing_minutes: float = 15.

    def __post_init__(self):
        for key in ("start", "pv_return", "irradiance_return"):
            object.__setattr__(self, key, utc(getattr(self, key)))
        if min(self.pv_return, self.irradiance_return) < self.start:
            raise ValueError("Restoration precedes interruption")
        if self.mode not in {"immediate", "gradual", "none"}:
            raise ValueError("Unknown backfill mode")
        if not np.isfinite(self.backfill_spacing_minutes) or self.backfill_spacing_minutes <= 0:
            raise ValueError("Backfill spacing must be finite and positive")


def deliver_schedule(observations, faults):
    """Oldest-first gradual queue: first old item arrives one spacing after return.

    Live observations arriving at/after restoration bypass the queue. Later
    faults can interrupt already queued packets, using their actual receipts.
    No values or measurement ends change, and missing source values stay absent.
    """
    events = list(observations)
    faults = sorted(faults, key=lambda f: f.start)
    if any(a.start == b.start or max(a.pv_return, a.irradiance_return) > b.start
           for a, b in zip(faults, faults[1:])):
        raise ValueError("Fault interruption periods must not overlap")
    for fault in faults:
        for stream in STREAMS:
            restore = getattr(fault, f"{stream}_return")
            backlog = sorted((o for o in events if o.stream == stream and fault.start <= o.receipt < restore),
                             key=lambda o: (o.end, o.id))
            changes = {}
            for position, observation in enumerate(backlog, 1):
                receipt = restore
                if fault.mode == "gradual":
                    receipt += pd.Timedelta(minutes=position*fault.backfill_spacing_minutes)
                changes[observation.id] = None if fault.mode == "none" else replace(observation, receipt=receipt)
            events = [changes.get(o.id, o) for o in events if changes.get(o.id, o) is not None]
    return sorted(events, key=lambda o: (o.receipt, o.end, o.stream, o.id))


class VisibleHistory(OriginalHistory):
    def __init__(self, baseline_lag_minutes=1):
        if not np.isfinite(baseline_lag_minutes) or baseline_lag_minutes < 0:
            raise ValueError("Release margin must be finite and nonnegative")
        super().__init__(baseline_lag_minutes)
        self.latest = dict.fromkeys(STREAMS, None)

    def receive(self, observation, origin):
        origin = utc(origin)
        if self.last_origin is not None and origin < self.last_origin:
            raise ValueError("History clock cannot go backward")
        super().receive(observation, origin)
        latest = self.latest[observation.stream]
        if latest is None or observation.end > latest:
            self.latest[observation.stream] = observation.end

    def features(self, origin):
        origin = utc(origin)
        if self.last_origin is not None and origin <= self.last_origin:
            raise ValueError("Feature origins must strictly increase")
        self.last_origin = origin
        expected_end = (origin-self.lag).floor("h")
        result = {}
        for stream in STREAMS:
            history, latest = self.values[stream], self.latest[stream]
            age = max(0., (expected_end-latest)/HOUR) if latest is not None else 1e6
            current = latest is not None and latest >= expected_end
            if self.gap[stream] and current:
                self.restored[stream] = origin
            if not current and latest is not None:
                self.restored[stream] = None
            self.gap[stream] = not current and latest is not None
            result[f"{stream}_age"] = age
            result[f"{stream}_current"] = float(current)
            result[f"{stream}_recovery"] = (origin-self.restored[stream])/HOUR if self.restored[stream] is not None else -1.
            result[f"{stream}_last"] = history[latest] if latest is not None else np.nan
            receipt = self.receipts[stream]
            result[f"{stream}_transport_age"] = (origin-receipt)/HOUR if receipt is not None else 1e6
            for lag in LAGS:
                result[f"{stream}_lag{lag}"] = history.get(expected_end-(lag-1)*HOUR, np.nan)
            result[f"{stream}_missing_fraction"] = np.mean([not np.isfinite(result[f"{stream}_lag{lag}"]) for lag in LAGS])
        angle = 2*np.pi*(origin.hour+origin.minute/60)/24
        result["hour_sin"], result["hour_cos"] = np.sin(angle), np.cos(angle)
        result["year_sin"] = np.sin(2*np.pi*origin.dayofyear/365.25)
        result["year_cos"] = np.cos(2*np.pi*origin.dayofyear/365.25)
        return result


def replay_features(observations, origins, baseline_lag_minutes=1):
    events = sorted(observations, key=lambda o: (o.receipt, o.end, o.stream, o.id))
    history = VisibleHistory(baseline_lag_minutes)
    rows, position = [], 0
    for origin in origins:
        while position < len(events) and events[position].receipt <= origin:
            history.receive(events[position], origin)
            position += 1
        rows.append(history.features(origin))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(origins, name="origin"))


def calendar_faults(start, end, seed, duration_hours=12, gap_hours=3,
                    scenario="irradiance_first", mode="immediate", spacing_days=7):
    """Calendar-only starts sample all UTC hours; no solar/weather/target filter."""
    if duration_hours <= 0 or gap_hours < 0 or spacing_days*24 <= duration_hours+gap_hours+24:
        raise ValueError("Events require positive duration and separate recovery windows")
    rng = np.random.default_rng(seed)
    days = pd.date_range(utc(start).normalize()+pd.Timedelta(days=3), utc(end)-pd.Timedelta(days=2), freq=f"{spacing_days}D")
    faults = []
    for day in days:
        instant = day+pd.Timedelta(hours=int(rng.integers(0, 24)), minutes=1)
        pv_return = irradiance_return = instant+duration_hours*HOUR
        if scenario == "pv_only":
            irradiance_return = instant
        elif scenario == "irradiance_only":
            pv_return = instant
        elif scenario == "irradiance_first":
            pv_return += gap_hours*HOUR
        elif scenario == "pv_first":
            irradiance_return += gap_hours*HOUR
        elif scenario != "joint":
            raise ValueError("Unknown outage scenario")
        faults.append(Fault(instant, pv_return, irradiance_return, mode))
    return faults
