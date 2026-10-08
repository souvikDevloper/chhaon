"""Use cases shared by the API, the scheduler targets and the agent tools."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import announce, metrics, planner, schedules, store, voice, weather

IST = timezone(timedelta(hours=5, minutes=30))

DEMO_SITE = {
    "name": "Howrah demo site",
    "lat": 22.5958,
    "lon": 88.2636,
    "workload": "heavy",
    "crew": 24,
    "new_workers": 3,
    "new_worker_day": 2,
    "shaded": False,
    "lang": "hi",
}

REPLAYS = {
    "rourkela-2024-05-30": {
        "place": "Rourkela, Odisha",
        "date": "2024-05-30",
        "lat": 22.2604,
        "lon": 84.8536,
        "what_happened": "Ten deaths from suspected heatstroke were reported at the government hospital in Rourkela that day. Odisha had barred its own employees from outdoor work between 11 AM and 3 PM.",
        "official_window": ["11:00", "15:00"],
        "source": "Reuters, 31 May 2024",
        "source_url": "https://www.business-standard.com/india-news/15-succumb-to-suspected-heatstroke-in-bihar-odisha-over-24-hours-124053100673_1.html",
    },
    "aurangabad-2024-05-30": {
        "place": "Aurangabad, Bihar",
        "date": "2024-05-30",
        "lat": 24.7522,
        "lon": 84.3740,
        "what_happened": "Five deaths due to 'sunstroke' were reported in Aurangabad city that day.",
        "official_window": None,
        "source": "Reuters, 31 May 2024",
        "source_url": "https://www.business-standard.com/india-news/15-succumb-to-suspected-heatstroke-in-bihar-odisha-over-24-hours-124053100673_1.html",
    },
}


def today() -> str:
    return datetime.now(IST).date().isoformat()


def resolve_day(day: str | None) -> str:
    if not day or day == "today":
        return today()
    if day == "tomorrow":
        return (datetime.now(IST).date() + timedelta(days=1)).isoformat()
    datetime.fromisoformat(day)  # validates
    return day


def site_config(site: dict) -> planner.SiteConfig:
    return planner.SiteConfig.from_dict(site)


def forecast_for(site: dict) -> dict:
    lat, lon = float(site["lat"]), float(site["lon"])
    return store.cached_weather(lat, lon, lambda: weather.forecast(lat, lon))


def compute(site: dict, date: str) -> tuple[list[planner.Slot], planner.DayPlan]:
    wx = forecast_for(site)
    cfg = site_config(site)
    slots, plan = planner.plan_from_weather(wx["hourly"], wx.get("utc_offset_seconds", 19800), cfg, date)
    if not slots:
        raise ValueError(f"no forecast for {date}")
    return slots, plan


def plan_payload(site_id: str, site: dict, date: str) -> dict:
    slots, plan = compute(site, date)
    _, published = store.get_plan(site_id, date)
    data = plan.to_dict()
    store.put_plan(site_id, date, data, published)
    return {
        "site_id": site_id,
        "site": site,
        "date": date,
        "plan": data,
        "published": bool(published),
        "now": datetime.now(IST).strftime("%H:%M"),
        "method": "Liljegren outdoor WBGT from the Open-Meteo forecast; ACGIH screening limits",
    }


def publish(site_id: str, site: dict, date: str) -> dict:
    _, plan = compute(site, date)
    _, old = store.get_plan(site_id, date)
    names = schedules.publish_day(site_id, date, plan.events, replace=old)
    store.put_plan(site_id, date, plan.to_dict(), names)
    metrics.emit(
        {"PlansPublished": 1, "UnsafeHoursAvoided": plan.unsafe_hours_avoided, "OverexposureMinutesAvoided": plan.overexposure_minutes_avoided}
    )
    return {"date": date, "schedules": len(names), "next": names[:1], "unsafe_hours_avoided": plan.unsafe_hours_avoided}


def announce_event(site_id: str, event: dict, date: str | None = None) -> dict:
    site = store.get_site(site_id) or {}
    lang = site.get("lang", "hi")
    texts = {l: announce.text_for(event, l) for l in ("hi", "en")}
    audio = {lang: voice.speak(texts[lang], lang)}
    entry = store.add_feed(
        site_id,
        {"type": "announcement", "kind": event["kind"], "at": event.get("at"), "date": date, "text": texts, "audio": audio, "lang": lang},
    )
    metrics.emit({"AnnouncementsDelivered": 1})
    return entry


def replay(key: str, workload: str = "heavy") -> dict:
    meta = REPLAYS.get(key)
    if not meta:
        raise KeyError(key)
    wx = store.cached_weather(meta["lat"] + 0.001, meta["lon"] + 0.001, lambda: weather.archive(meta["lat"], meta["lon"], meta["date"]))
    cfg = planner.SiteConfig(lat=meta["lat"], lon=meta["lon"], workload=workload)
    slots, plan = planner.plan_from_weather(wx["hourly"], wx.get("utc_offset_seconds", 19800), cfg, meta["date"])
    return {"replay": {k: v for k, v in meta.items()}, "key": key, "plan": plan.to_dict(), "data": "ERA5 reanalysis via Open-Meteo archive (about 25 km grid, not a site measurement)"}
