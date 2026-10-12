"""Event timeline scheduling for the News Bias Engine (Part 3/5).

Pure functions that compute the schedule points around an event so they are
unit-tested without a scheduler. The engine registers these as APScheduler
jobs; this module only decides *when* things happen and what state transitions
occur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(slots=True)
class EventSchedule:
    event_time: datetime
    regen_times: list[datetime] = field(default_factory=list)   # T-30, T-15, T-6
    lock_time: datetime | None = None                          # T-5 (bias locked)
    place_time: datetime | None = None                         # T-5 (orders placed post-confirm)
    cutoff_time: datetime | None = None                        # T-60s (no action -> nothing)
    expire_time: datetime | None = None                        # event + expiry window


def build_schedule(
    event_time: datetime,
    *,
    regen_offsets: tuple[int, ...] = (-30, -15, -6),
    lock_offset_minutes: int = 5,
    place_offset_minutes: int = 5,
    confirm_cutoff_seconds: int = 60,
    pending_expiry_minutes: int = 15,
) -> EventSchedule:
    regen = [event_time + timedelta(minutes=o) for o in regen_offsets]
    lock = event_time - timedelta(minutes=lock_offset_minutes)
    place = event_time - timedelta(minutes=place_offset_minutes)
    cutoff = event_time - timedelta(seconds=confirm_cutoff_seconds)
    expire = event_time + timedelta(minutes=pending_expiry_minutes)
    # Only keep regen points that are strictly before the lock time.
    regen = [t for t in regen if t < lock]
    return EventSchedule(
        event_time=event_time, regen_times=sorted(regen), lock_time=lock,
        place_time=place, cutoff_time=cutoff, expire_time=expire,
    )


def phase_at(schedule: EventSchedule, now: datetime) -> str:
    """Return the lifecycle phase for ``now`` relative to the schedule.

    Phases: 'idle' -> 'regen' (before lock) -> 'await_confirm' (lock..cutoff)
    -> 'place' (at/after place, before event) -> 'live' (event started) ->
    'expired' (after expiry).
    """
    if schedule.regen_times and now < schedule.regen_times[0]:
        return "idle"
    if schedule.lock_time and now < schedule.lock_time:
        return "regen"
    if schedule.cutoff_time and now < schedule.cutoff_time:
        return "await_confirm"
    if schedule.event_time and now < schedule.event_time:
        return "place"
    if schedule.expire_time and now < schedule.expire_time:
        return "live"
    return "expired"
