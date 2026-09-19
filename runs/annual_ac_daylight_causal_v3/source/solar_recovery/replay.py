"""Observation delivery and state construction, independent of evaluator truth."""
from dataclasses import dataclass, replace
import math
from collections import defaultdict

import numpy as np
import pandas as pd

HOUR = pd.Timedelta(hours=1)
STREAMS = ("pv", "irradiance")
LAGS = (1, 2, 3, 4, 5, 6, 12, 24, 48)


def utc(value):
    value = pd.Timestamp(value)
    if value.tzinfo is None:
        raise ValueError("An explicit timezone is required")
    return value.tz_convert("UTC")


@dataclass(frozen=True)
class Observation:
    id: str
    stream: str
    end: pd.Timestamp
    receipt: pd.Timestamp
    value: float

    def __post_init__(self):
        object.__setattr__(self, "end", utc(self.end))
        object.__setattr__(self, "receipt", utc(self.receipt))
        if self.stream not in STREAMS or not math.isfinite(self.value):
            raise ValueError("Unknown stream or nonfinite observation")
        if self.receipt < self.end:
            raise ValueError("An interval cannot arrive before it ends")


@dataclass(frozen=True)
class Outage:
    start: pd.Timestamp
    pv_return: pd.Timestamp
    irradiance_return: pd.Timestamp
    backfill: bool = True

    def __post_init__(self):
        for key in ("start", "pv_return", "irradiance_return"):
            object.__setattr__(self, key, utc(getattr(self, key)))
        if min(self.pv_return, self.irradiance_return) < self.start:
            raise ValueError("Restoration precedes interruption")


def deliver_schedule(observations, outages):
    """Faults affect arrivals only. The scheduler is not passed to a forecaster."""
    result = []
    for obs in observations:
        receipt = obs.receipt
        dropped = False
        for fault in sorted(outages, key=lambda f: f.start):
            restore = fault.pv_return if obs.stream == "pv" else fault.irradiance_return
            if fault.start <= receipt < restore:
                if not fault.backfill:
                    dropped = True
                    break
                receipt = restore
        if not dropped:
            result.append(replace(obs, receipt=receipt))
    return sorted(result, key=lambda x: (x.receipt, x.end, x.stream, x.id))


class VisibleHistory:
    """Only delivered observations; late old data never overwrites newer state."""

    def __init__(self, baseline_lag_minutes=0):
        self.lag = pd.Timedelta(minutes=baseline_lag_minutes)
        self.values = {stream: {} for stream in STREAMS}
        self.receipts = {stream: None for stream in STREAMS}
        self.ids = {}
        self.gap = dict.fromkeys(STREAMS, False)
        self.restored = dict.fromkeys(STREAMS, None)
        self.last_origin = None

    def receive(self, obs, origin):
        origin = utc(origin)
        if obs.receipt > origin or obs.end > origin:
            raise ValueError("Undelivered or future observation")
        if obs.id in self.ids:
            if self.ids[obs.id] != obs:
                raise ValueError("Conflicting duplicate observation ID")
            return
        existing = self.values[obs.stream].get(obs.end)
        if existing is not None and existing != obs.value:
            raise ValueError("Conflicting same-time values need an explicit revision policy")
        self.ids[obs.id] = obs
        self.values[obs.stream][obs.end] = obs.value
        last = self.receipts[obs.stream]
        self.receipts[obs.stream] = max(last, obs.receipt) if last is not None else obs.receipt

    def features(self, origin):
        origin = utc(origin)
        if self.last_origin is not None and origin <= self.last_origin:
            raise ValueError("Feature origins must strictly increase")
        self.last_origin = origin
        expected_end = (origin - self.lag).floor("h")
        result = {}
        for stream in STREAMS:
            history = self.values[stream]
            latest = max(history) if history else None
            age = max(0., (expected_end-latest)/HOUR) if latest is not None else 1e6
            current = age == 0
            if self.gap[stream] and current:
                self.restored[stream] = origin
            if not current and latest is not None:
                self.restored[stream] = None
            self.gap[stream] = not current and latest is not None
            recovery = (origin-self.restored[stream])/HOUR if self.restored[stream] is not None else -1.
            result[f"{stream}_age"] = age
            result[f"{stream}_current"] = float(current)
            result[f"{stream}_recovery"] = recovery
            result[f"{stream}_last"] = history[latest] if latest is not None else np.nan
            result[f"{stream}_transport_age"] = (origin-self.receipts[stream])/HOUR if self.receipts[stream] is not None else 1e6
            for lag in LAGS:
                # lag=1 denotes the completed interval [origin-1h, origin).
                result[f"{stream}_lag{lag}"] = history.get(origin-(lag-1)*HOUR, np.nan)
            result[f"{stream}_missing_fraction"] = np.mean([not np.isfinite(result[f"{stream}_lag{lag}"]) for lag in LAGS])
        angle = 2*np.pi*(origin.hour+origin.minute/60)/24
        result["hour_sin"], result["hour_cos"] = np.sin(angle), np.cos(angle)
        result["year_sin"] = np.sin(2*np.pi*origin.dayofyear/365.25)
        result["year_cos"] = np.cos(2*np.pi*origin.dayofyear/365.25)
        return result


def replay_features(observations, origins, baseline_lag_minutes=0):
    events = sorted(observations, key=lambda x: (x.receipt, x.end, x.stream, x.id))
    view = VisibleHistory(baseline_lag_minutes)
    position = 0
    rows = []
    for origin in origins:
        origin = utc(origin)
        while position < len(events) and events[position].receipt <= origin:
            view.receive(events[position], origin)
            position += 1
        rows.append(view.features(origin))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(origins, name="origin"))


def observations_from_hourly(frame, lag_minutes=0):
    """Frame index is completed interval end; missing values produce no event."""
    if frame.index.tz is None or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Hourly data needs unique sorted timezone-aware interval ends")
    if not frame.index.equals(frame.index.floor("h")):
        raise ValueError("Interval ends must be hourly boundaries")
    result = []
    for end, row in frame.iterrows():
        for stream in STREAMS:
            if np.isfinite(row[stream]):
                result.append(Observation(f"{stream}:{end.isoformat()}", stream, end,
                                          end+pd.Timedelta(minutes=lag_minutes), float(row[stream])))
    return result


def labels_by_receipt(events):
    """Only the causal delivery ledger is exposed to online calibration."""
    result = defaultdict(list)
    for obs in events:
        if obs.stream == "pv":
            result[obs.receipt].append(obs)
    return result

