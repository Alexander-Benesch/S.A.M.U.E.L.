"""#302: Time-window helper for shared use across slices and adapters.

Pure-stdlib datetime logic — no adapter or slice imports. Lives in core/
so both ``samuel/adapters/llm/scheduled_routing.py`` and dashboard/slice code
can call into it without violating slice-architecture rules.
"""
from __future__ import annotations

import logging
from datetime import datetime, time

log = logging.getLogger(__name__)


def schedule_active(sched: dict | None, now: time | None = None) -> bool:
    """Returns True if the time-window in ``sched`` covers ``now``.

    Schema::

        {
            "active": true,        # default true; explicit false disables
            "from":   "22:00",      # HH:MM
            "to":     "06:00",      # HH:MM
            ...                     # provider/model fields ignored here
        }

    Mitternacht-Uebergang (z.B. 22:00-06:00) wird korrekt behandelt.
    Bei kaputten Werten (invalid time format, missing keys) -> False, kein Crash.
    """
    if not isinstance(sched, dict):
        return False
    if not sched.get("active", True):
        return False
    now = now or datetime.now().time()
    try:
        f = sched["from"]
        t = sched["to"]
        t_from = time(*map(int, f.split(":")))
        t_to = time(*map(int, t.split(":")))
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("Invalid schedule format (%s): %s", exc, sched)
        return False
    if t_from <= t_to:
        return t_from <= now <= t_to
    # Mitternacht-Uebergang: 22:00 -> 06:00
    return now >= t_from or now <= t_to
