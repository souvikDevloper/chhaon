"""Solar position (NOAA General Solar Position algorithm, ~0.01 deg accuracy).

Only what the WBGT model needs: the cosine of the solar zenith angle and the
Earth-Sun distance in AU, for a UTC instant and a location.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


def _julian_day(dt: datetime) -> float:
    dt = dt.astimezone(timezone.utc)
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + (dt.minute + dt.second / 60.0) / 60.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def solar_position(dt: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Return (cos_zenith, earth_sun_distance_au) for an aware datetime."""
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    utc = dt.astimezone(timezone.utc)
    jc = (_julian_day(utc) - 2451545.0) / 36525.0

    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(m)
    center = (
        math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * mr) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * mr) * 0.000289
    )
    true_long = l0 + center
    true_anom = m + center
    distance = (1.000001018 * (1 - ecc * ecc)) / (1 + ecc * math.cos(math.radians(true_anom)))
    omega = 125.04 - 1934.136 * jc
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    mean_obliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq = mean_obliq + 0.00256 * math.cos(math.radians(omega))
    decl = math.asin(math.sin(math.radians(obliq)) * math.sin(math.radians(app_long)))

    var_y = math.tan(math.radians(obliq / 2)) ** 2
    l0r = math.radians(l0)
    eq_time = 4 * math.degrees(
        var_y * math.sin(2 * l0r)
        - 2 * ecc * math.sin(mr)
        + 4 * ecc * var_y * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * var_y * var_y * math.sin(4 * l0r)
        - 1.25 * ecc * ecc * math.sin(2 * mr)
    )
    minutes = utc.hour * 60 + utc.minute + utc.second / 60.0
    tst = (minutes + eq_time + 4 * lon) % 1440
    hour_angle = tst / 4 - 180 if tst / 4 >= 0 else tst / 4 + 180

    latr = math.radians(lat)
    cos_zen = math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(
        math.radians(hour_angle)
    )
    return max(-1.0, min(1.0, cos_zen)), distance
