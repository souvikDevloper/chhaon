"""Heat-safe shift planner.

Turns an hourly weather forecast into a day plan for a site:
1. WBGT for every hour slot, in sun (or shade for covered work).
2. The safe share of each hour for the crew's workload (ACGIH screening table).
3. A shift that keeps the normal 9-to-6 hours where they are safe and moves the
   minutes that are not safe into the coolest hours of the allowed window, so the
   crew keeps as much paid work as the heat allows.
4. The announcements a site speaker should play, minute by minute.

Everything here is deterministic and unit-tested: the language model never makes
a safety decision, it only explains this output.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from .limits import cool_max_minutes, exposure_factor, hour_limit

WATER_L_PER_HOUR = 0.75  # NIOSH: one cup (about 240 ml) every 15-20 minutes when working in the heat
from .solar import solar_position
from .wbgt import outdoor_wbgt


@dataclass
class SiteConfig:
    lat: float
    lon: float
    workload: str = "heavy"
    crew: int = 20
    new_workers: int = 0
    new_worker_day: int = 1
    shaded: bool = False
    clothing: str = "normal"
    window_start: int = 6  # earliest hour work may start
    window_end: int = 19  # work must end by this hour
    baseline_start: int = 9
    baseline_end: int = 18
    lunch_hour: int | None = 13
    urban: bool = True

    def baseline_hours(self) -> list[int]:
        return [h for h in range(self.baseline_start, self.baseline_end) if h != self.lunch_hour]

    @classmethod
    def from_dict(cls, d: dict) -> "SiteConfig":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d and d[k] is not None}
        cfg = cls(**known)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
            raise ValueError("lat/lon out of range")
        if self.workload not in ("light", "moderate", "heavy", "very_heavy"):
            raise ValueError("workload must be light, moderate, heavy or very_heavy")
        if not (0 <= self.window_start < self.window_end <= 24):
            raise ValueError("bad work window")
        self.crew = max(0, min(int(self.crew), 2000))
        self.new_workers = max(0, min(int(self.new_workers), self.crew or 2000))
        self.new_worker_day = max(1, min(int(self.new_worker_day), 30))


@dataclass
class Slot:
    hour: int
    start: str
    air_temp: float
    humidity: float
    wind: float
    solar: float
    wbgt: float
    globe: float
    wet_bulb: float


def compute_slots(hourly: dict, utc_offset_seconds: int, lat: float, lon: float, date: str, shaded: bool = False, urban: bool = True) -> list[Slot]:
    """Hour slots [h, h+1) for `date` from Open-Meteo hourly arrays (local time).

    Temperature, humidity, wind and pressure are instantaneous at the hour mark, so
    a slot uses the mean of its two ends. Radiation is the mean of the preceding
    hour, so slot [h, h+1) uses the value labelled h+1, and the sun is placed at
    the slot's midpoint.
    """
    times = hourly["time"]
    index = {t: i for i, t in enumerate(times)}
    tz = timezone(timedelta(seconds=utc_offset_seconds))
    day0 = datetime.fromisoformat(f"{date}T00:00").replace(tzinfo=tz)

    def val(name: str, i: int):
        arr = hourly.get(name)
        return None if arr is None else arr[i]

    slots: list[Slot] = []
    for h in range(24):
        t0 = day0 + timedelta(hours=h)
        t1 = t0 + timedelta(hours=1)
        i0 = index.get(t0.strftime("%Y-%m-%dT%H:%M"))
        i1 = index.get(t1.strftime("%Y-%m-%dT%H:%M"))
        if i0 is None or i1 is None:
            continue
        raw = {}
        ok = True
        for name in ("temperature_2m", "relative_humidity_2m", "wind_speed_10m", "surface_pressure"):
            a, b = val(name, i0), val(name, i1)
            if a is None or b is None:
                ok = False
                break
            raw[name] = (a + b) / 2
        ghi = val("shortwave_radiation", i1)
        if not ok or ghi is None:
            continue
        direct = val("direct_radiation", i1)
        cza, dist = solar_position(t0 + timedelta(minutes=30), lat, lon)
        res = outdoor_wbgt(
            raw["temperature_2m"],
            raw["relative_humidity_2m"],
            raw["wind_speed_10m"],
            ghi,
            raw["surface_pressure"],
            cza,
            distance_au=dist,
            direct_wm2=direct,
            urban=urban,
            shaded=shaded,
        )
        slots.append(
            Slot(
                hour=h,
                start=f"{h:02d}:00",
                air_temp=round(raw["temperature_2m"], 1),
                humidity=round(raw["relative_humidity_2m"]),
                wind=round(raw["wind_speed_10m"], 1),
                solar=round(ghi),
                wbgt=round(res.wbgt, 1),
                globe=round(res.globe, 1),
                wet_bulb=round(res.psychrometric_wet_bulb, 1),
            )
        )
    return slots


@dataclass
class HourPlan:
    hour: int
    start: str
    wbgt: float
    air_temp: float
    humidity: float
    band: str
    safe_minutes: int  # safe work minutes this hour
    work_minutes: int  # planned
    rest_minutes: int
    status: str  # work | free | stop | off
    in_normal_shift: bool
    normal_overexposure: int  # minutes a normal shift would work above the safe share because of heat


@dataclass
class GroupPlan:
    label: str
    acclimatised: bool
    exposure_factor: float
    target_minutes: int
    planned_minutes: int
    shortfall_minutes: int
    hours: list[HourPlan]
    first_start: str | None
    last_end: str | None
    stop_windows: list[tuple[str, str]]


@dataclass
class DayPlan:
    date: str
    workload: str
    shaded: bool
    crew: GroupPlan
    new_workers: GroupPlan | None
    unsafe_hours_normal: int
    unsafe_hours_planned: int
    unsafe_hours_avoided: int
    overexposure_minutes_avoided: int
    worker_hours_protected: float  # crew x minutes a normal shift would have worked above the limit
    normal_minutes_per_hour: int
    water_litres_per_worker: float | None
    water_litres_total: int | None
    peak_wbgt: float | None
    peak_time: str | None
    verdict: str  # normal | adjusted | stop_heavy | stop_all
    events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt(h: int, m: int = 0) -> str:
    h += m // 60
    m %= 60
    return f"{h:02d}:{m:02d}"


def _plan_group(slots: list[Slot], cfg: SiteConfig, acclimatised: bool, factor: float, label: str) -> GroupPlan:
    window = [s for s in slots if cfg.window_start <= s.hour < cfg.window_end]
    baseline = set(cfg.baseline_hours())
    limits = {s.hour: hour_limit(s.wbgt, cfg.workload, acclimatised, cfg.clothing) for s in window}
    normal = cool_max_minutes(cfg.workload)  # a normal hour of this work on a cool day
    full_target = len(baseline) * normal
    target = int(round(full_target * factor / 5.0) * 5)

    plan: dict[int, int] = {s.hour: 0 for s in window}
    if factor >= 1.0:
        # keep the normal shift where it is safe
        for h in sorted(baseline):
            if h in limits:
                plan[h] = min(normal, limits[h].work_minutes)
    remaining = target - sum(plan.values())
    # move the rest into the coolest hours with spare capacity
    for s in sorted(window, key=lambda s: (s.wbgt, s.hour)):
        if remaining <= 0:
            break
        spare = limits[s.hour].work_minutes - plan[s.hour]
        if spare <= 0:
            continue
        add = min(spare, remaining)
        plan[s.hour] += add
        remaining -= add
    # trim if the normal shift alone overshoots a reduced target
    over = sum(plan.values()) - target
    if over > 0:
        for s in sorted(window, key=lambda s: (-s.wbgt, -s.hour)):
            if over <= 0:
                break
            cut = min(plan[s.hour], over)
            plan[s.hour] -= cut
            over -= cut

    hours: list[HourPlan] = []
    for s in slots:
        lim = limits.get(s.hour) or hour_limit(s.wbgt, cfg.workload, acclimatised, cfg.clothing)
        in_window = s.hour in limits
        work = plan.get(s.hour, 0)
        if not in_window:
            status = "off"
        elif work > 0:
            status = "work"
        elif lim.work_minutes == 0:
            status = "stop"
        else:
            status = "free"
        in_normal = s.hour in baseline
        hours.append(
            HourPlan(
                hour=s.hour,
                start=s.start,
                wbgt=s.wbgt,
                air_temp=s.air_temp,
                humidity=s.humidity,
                band=lim.band,
                safe_minutes=lim.work_minutes,
                work_minutes=work,
                rest_minutes=60 - work if work else 0,
                status=status,
                in_normal_shift=in_normal,
                normal_overexposure=max(0, normal - lim.work_minutes) if in_normal else 0,
            )
        )

    work_hours = [h for h in hours if h.work_minutes > 0]
    stops: list[tuple[str, str]] = []
    run: list[int] = []
    for h in hours:
        if h.status == "stop":
            run.append(h.hour)
        elif run:
            stops.append((_fmt(run[0]), _fmt(run[-1] + 1)))
            run = []
    if run:
        stops.append((_fmt(run[0]), _fmt(run[-1] + 1)))
    planned = sum(plan.values())
    return GroupPlan(
        label=label,
        acclimatised=acclimatised,
        exposure_factor=factor,
        target_minutes=target,
        planned_minutes=planned,
        shortfall_minutes=max(0, target - planned),
        hours=hours,
        first_start=work_hours[0].start if work_hours else None,
        last_end=_fmt(work_hours[-1].hour, work_hours[-1].work_minutes) if work_hours else None,
        stop_windows=stops,
    )


def build_events(group: GroupPlan) -> list[dict]:
    """Announcements for the site speaker, in time order."""
    work = [h for h in group.hours if h.work_minutes > 0]
    events: list[dict] = []
    if not work:
        return events
    first, last = work[0], work[-1]
    for i, h in enumerate(work):
        nxt = work[i + 1] if i + 1 < len(work) else None
        prev = work[i - 1] if i > 0 else None
        if h is first:
            events.append({"at": _fmt(h.hour), "kind": "day_start", "minutes": h.work_minutes})
        elif prev is not None and prev.hour != h.hour - 1:
            events.append({"at": _fmt(h.hour), "kind": "resume", "minutes": h.work_minutes})
        elif prev is not None and prev.rest_minutes > 0:
            events.append({"at": _fmt(h.hour), "kind": "work_start", "minutes": h.work_minutes})
        end_of_work = _fmt(h.hour, h.work_minutes)
        if h is last:
            events.append({"at": end_of_work, "kind": "day_end", "minutes": 0})
        elif nxt is not None and nxt.hour != h.hour + 1:
            events.append({"at": end_of_work, "kind": "pause", "minutes": (nxt.hour - h.hour) * 60 - h.work_minutes, "until": _fmt(nxt.hour)})
        elif h.rest_minutes > 0:
            events.append({"at": end_of_work, "kind": "rest", "minutes": h.rest_minutes})
    return events


def plan_day(slots: list[Slot], cfg: SiteConfig, date: str) -> DayPlan:
    crew = _plan_group(slots, cfg, acclimatised=True, factor=1.0, label="crew")
    normal = cool_max_minutes(cfg.workload)
    window = [s for s in slots if cfg.window_start <= s.hour < cfg.window_end]
    newbies = None
    if cfg.new_workers > 0:
        # NIOSH's ramp limits exposure to heat: it applies only when the heat cuts into
        # new workers' hours at all (stricter Action Limit), not on a cool day.
        hot_for_new = any(hour_limit(s.wbgt, cfg.workload, False, cfg.clothing).work_minutes < normal for s in window)
        factor = exposure_factor(cfg.new_worker_day) if hot_for_new else 1.0
        newbies = _plan_group(slots, cfg, acclimatised=False, factor=factor, label="new_workers")
    normal_unsafe = [h for h in crew.hours if h.in_normal_shift and h.normal_overexposure > 0]
    planned_unsafe = [h for h in crew.hours if h.work_minutes > h.safe_minutes]
    window_hours = [h for h in crew.hours if h.status != "off"]
    peak = max(slots, key=lambda s: s.wbgt) if slots else None
    over_minutes = sum(h.normal_overexposure for h in normal_unsafe)
    water_pw = water_total = None
    if normal_unsafe and crew.planned_minutes:
        # a cup every 15-20 minutes of work in the heat; rest breaks in shade not counted
        water_pw = max(0.5, round(crew.planned_minutes / 60 * WATER_L_PER_HOUR * 2) / 2)  # nearest half litre
        water_total = int(round(water_pw * cfg.crew))
    if not normal_unsafe:
        verdict = "normal"
    elif window_hours and all(h.safe_minutes == 0 for h in window_hours):
        verdict = "stop_all"
    elif crew.stop_windows:
        verdict = "stop_heavy"
    else:
        verdict = "adjusted"
    plan = DayPlan(
        date=date,
        workload=cfg.workload,
        shaded=cfg.shaded,
        crew=crew,
        new_workers=newbies,
        unsafe_hours_normal=len(normal_unsafe),
        unsafe_hours_planned=len(planned_unsafe),
        unsafe_hours_avoided=len(normal_unsafe) - len(planned_unsafe),
        overexposure_minutes_avoided=over_minutes,
        worker_hours_protected=round(over_minutes * cfg.crew / 60, 1),
        normal_minutes_per_hour=normal,
        water_litres_per_worker=water_pw,
        water_litres_total=water_total,
        peak_wbgt=peak.wbgt if peak else None,
        peak_time=peak.start if peak else None,
        verdict=verdict,
    )
    plan.events = build_events(crew)
    return plan


def check_window(slots: list[Slot], cfg: SiteConfig, start_hour: int, hours: int, workload: str | None = None, acclimatised: bool = True) -> dict:
    """Can a task of `hours` run from `start_hour`? Returns per-hour safety and the best alternative.
    acclimatised=False uses the stricter Action Limit for workers in their first week."""
    wl = workload or cfg.workload
    by_hour = {s.hour: s for s in slots}
    ok_minutes = min(45, cool_max_minutes(wl, acclimatised))

    def score(start: int) -> dict | None:
        rows = []
        for h in range(start, start + hours):
            s = by_hour.get(h)
            if s is None:
                return None
            lim = hour_limit(s.wbgt, wl, acclimatised, cfg.clothing)
            rows.append({"hour": _fmt(h), "wbgt": s.wbgt, "safe_minutes": lim.work_minutes, "band": lim.band})
        return {
            "start": _fmt(start),
            "end": _fmt(start + hours),
            "hours": rows,
            "min_safe_minutes": min(r["safe_minutes"] for r in rows),
            "max_wbgt": max(r["wbgt"] for r in rows),
            "ok": all(r["safe_minutes"] >= ok_minutes for r in rows),
        }

    asked = score(start_hour)
    options = [score(s) for s in range(cfg.window_start, cfg.window_end - hours + 1)]
    options = [o for o in options if o is not None]
    best = sorted(options, key=lambda o: (-o["min_safe_minutes"], o["max_wbgt"]))[:3]
    return {"workload": wl, "new_workers": not acclimatised, "asked": asked, "best": best}


def plan_from_weather(hourly: dict, utc_offset_seconds: int, cfg: SiteConfig, date: str) -> tuple[list[Slot], DayPlan]:
    """The one entry point services use: weather -> slots (with the site's shade/urban settings) -> plan."""
    slots = compute_slots(hourly, utc_offset_seconds, cfg.lat, cfg.lon, date, shaded=cfg.shaded, urban=cfg.urban)
    return slots, plan_day(slots, cfg, date)
