"""Transport-heartbeat sensitivity preserving stale measurement timestamps."""
from dataclasses import replace

from .replay import STREAMS
from .replay_v3 import deliver_schedule


def stale_schedule(observations, faults):
    """Drop interrupted measurements and repeat the last pre-fault packet.

    A new transport ID and receipt do not manufacture a new measurement end or
    value. Repeated PV labels therefore cannot create new calibration scores.
    Missing pre-fault packets produce no heartbeat for that stream.
    """
    events = list(observations)
    scheduled = deliver_schedule(events, [replace(f, mode="none") for f in faults])
    for j, fault in enumerate(faults):
        for stream in STREAMS:
            previous = [o for o in scheduled if o.stream == stream and o.receipt < fault.start]
            if not previous:
                continue
            latest = max(previous, key=lambda o: (o.end, o.receipt))
            restore = getattr(fault, f"{stream}_return")
            for observation in events:
                if observation.stream == stream and fault.start <= observation.receipt < restore:
                    scheduled.append(replace(latest, id=f"stale:{j}:{observation.id}", receipt=observation.receipt))
    return sorted(scheduled, key=lambda o: (o.receipt, o.end, o.stream, o.id))
