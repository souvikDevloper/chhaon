"""Work/rest limits from the ACGIH heat-stress screening criteria.

Values are WBGT (deg C) for an 8-hour day with conventional breaks, as published
by CCOHS (Canadian Centre for Occupational Health and Safety) from ACGIH TLVs.
A value is the highest WBGT at which that share of each hour may be spent
working. `None` means the table gives no limit (do not plan that share).

Acclimatised workers use the TLV; workers new to the heat use the Action Limit.
NIOSH: a new worker should get no more than 20% of the usual exposure on day 1,
+20% per day after; an experienced worker returning after a week or more away
50% / 60% / 80% / 100% on days 1-4.
"""
from __future__ import annotations

from dataclasses import dataclass

WORKLOADS = ("light", "moderate", "heavy", "very_heavy")

# (work share upper bound in %, minutes of work allowed per hour in the plan)
# 75-100% is planned as 50 min work + 10 min rest: the table assumes conventional breaks.
SHARES = ((100, 50), (75, 45), (50, 30), (25, 15))

TLV = {  # acclimatised
    "light": (31.0, 31.0, 32.0, 32.5),
    "moderate": (28.0, 29.0, 30.0, 31.5),
    "heavy": (None, 27.5, 29.0, 30.5),
    "very_heavy": (None, None, 28.0, 30.0),
}
ACTION_LIMIT = {  # unacclimatised
    "light": (28.0, 28.5, 29.5, 30.0),
    "moderate": (25.0, 26.0, 27.0, 29.0),
    "heavy": (None, 24.0, 25.5, 28.0),
    "very_heavy": (None, None, 24.5, 27.0),
}

# Clothing adjustment added to WBGT before using the table (ACGIH clothing adjustment
# factors as published by CCOHS; work clothes and woven coveralls are the reference, 0)
CLOTHING_ADJUST = {"normal": 0.0, "coveralls": 0.0, "double_layer": 3.0}

NEW_WORKER_RAMP = (0.2, 0.4, 0.6, 0.8, 1.0)
RETURNING_RAMP = (0.5, 0.6, 0.8, 1.0)

FULL_HOUR_MINUTES = SHARES[0][1]  # 50


def cool_max_minutes(workload: str, acclimatised: bool = True) -> int:
    """Work minutes per hour the table allows this workload on a cool day.

    Heavy work has no 75-100% row (it is never screened for continuous work), so
    its normal hour is 45 minutes of work, very heavy 30. An hour is only "unsafe
    because of heat" when the heat cuts it below this."""
    row = (TLV if acclimatised else ACTION_LIMIT)[workload]
    for (share, minutes), limit in zip(SHARES, row):
        if limit is not None:
            return minutes
    return 0


@dataclass(frozen=True)
class HourLimit:
    work_minutes: int  # minutes per hour that may be worked
    rest_minutes: int
    band: str  # "safe" | "caution" | "danger" | "extreme" | "stop"
    limit_used: float | None  # WBGT limit of the band reached


def hour_limit(wbgt: float, workload: str, acclimatised: bool, clothing: str = "normal") -> HourLimit:
    if workload not in WORKLOADS:
        raise ValueError(f"unknown workload {workload!r}")
    eff = wbgt + CLOTHING_ADJUST.get(clothing, 0.0)
    row = (TLV if acclimatised else ACTION_LIMIT)[workload]
    bands = ("safe", "caution", "danger", "extreme")
    for (share, minutes), limit, band in zip(SHARES, row, bands):
        if limit is not None and eff <= limit:
            return HourLimit(minutes, 60 - minutes, band, limit)
    return HourLimit(0, 60, "stop", row[-1])


def exposure_factor(days_on_site: int | None, returning: bool = False) -> float:
    """Share of a normal day's heat exposure allowed while acclimatising."""
    if days_on_site is None:
        return 1.0
    ramp = RETURNING_RAMP if returning else NEW_WORKER_RAMP
    if days_on_site < 1:
        days_on_site = 1
    return ramp[min(days_on_site, len(ramp)) - 1]
