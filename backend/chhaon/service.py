"""Use cases shared by the API, the scheduler targets and the agent tools."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
        "what_happened_hi": "उस दिन राउरकेला के सरकारी अस्पताल में संदिग्ध लू से दस मौतें दर्ज हुईं। ओडिशा ने अपने कर्मचारियों के लिए सुबह 11 से दोपहर 3 बजे तक बाहर काम पर रोक लगाई थी।",
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
        "what_happened_hi": "उस दिन औरंगाबाद शहर में 'लू लगने' से पाँच मौतें दर्ज हुईं।",
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


def site_config(site: dict, date: str | None = None) -> planner.SiteConfig:
    """The planner's view of a site on `date`. New workers' day on site counts up from
    `new_workers_since`, so the NIOSH ramp advances by itself (day 1: 20%, +20% a day)."""
    d = dict(site)
    since = site.get("new_workers_since")
    if since and date:
        d["new_worker_day"] = max(1, (datetime.fromisoformat(date) - datetime.fromisoformat(since)).days + 1)
    return planner.SiteConfig.from_dict(d)


def new_workers_since(day_on_site: int) -> str:
    return (datetime.now(IST).date() - timedelta(days=max(1, int(day_on_site)) - 1)).isoformat()


def forecast_for(site: dict) -> dict:
    lat, lon = float(site["lat"]), float(site["lon"])
    return store.cached_weather(lat, lon, lambda: weather.forecast(lat, lon))


def compute(site: dict, date: str) -> tuple[list[planner.Slot], planner.DayPlan]:
    wx = forecast_for(site)
    cfg = site_config(site, date)
    slots, plan = planner.plan_from_weather(wx["hourly"], wx.get("utc_offset_seconds", 19800), cfg, date)
    if not slots:
        raise ValueError(f"no forecast for {date}")
    return slots, plan


def shade_option(site: dict, date: str, plan: planner.DayPlan) -> dict | None:
    """What a tarpaulin over the work area would give back: the same day planned in shade."""
    if site.get("shaded") or not plan.unsafe_hours_normal:
        return None
    wx = forecast_for(site)
    cfg = site_config(site, date)
    cfg.shaded = True
    _, shaded = planner.plan_from_weather(wx["hourly"], wx.get("utc_offset_seconds", 19800), cfg, date)
    gain = shaded.crew.planned_minutes - plan.crew.planned_minutes
    if gain <= 0:
        return None
    return {
        "planned_minutes": shaded.crew.planned_minutes,
        "gain_minutes": gain,
        "gain_worker_hours": round(gain * int(site.get("crew") or 0) / 60),
        "unsafe_hours_normal": shaded.unsafe_hours_normal,
        "stop_windows": shaded.crew.stop_windows,
        "first_start": shaded.crew.first_start,
    }


def plan_payload(site_id: str, site: dict, date: str) -> dict:
    slots, plan = compute(site, date)
    _, published = store.get_plan(site_id, date)
    data = plan.to_dict()
    store.put_plan(site_id, date, data, published)
    try:
        shade = shade_option(site, date, plan)
    except Exception:
        shade = None
    return {
        "site_id": site_id,
        "site": {**site, "new_worker_day": site_config(site, date).new_worker_day},
        "date": date,
        "plan": data,
        "shade": shade,
        "published": bool(published),
        "now": datetime.now(IST).strftime("%H:%M"),
        "method": "Liljegren outdoor WBGT from the Open-Meteo forecast; ACGIH screening limits",
    }


def _next_day(date: str) -> str:
    return (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()


def _with_tomorrow(site: dict, date: str, events: list[dict]) -> list[dict]:
    """Add tomorrow's start time to the end-of-day announcement, so the crew hears it."""
    events = [dict(e) for e in events]
    if events and events[-1]["kind"] == "day_end":
        try:
            _, nxt = compute(site, _next_day(date))
            if nxt.crew.first_start:
                events[-1]["tomorrow"] = nxt.crew.first_start
        except Exception:
            pass
    return events


def prepare_audio(events: list[dict], lang: str) -> list[dict]:
    """Synthesise every announcement of the day now (each sentence once, cached in S3),
    so the phone can cache the audio and still play breaks if the network drops."""
    texts = [announce.text_for(e, lang) for e in events]
    unique = list(dict.fromkeys(texts))
    with ThreadPoolExecutor(max_workers=6) as pool:
        urls = dict(zip(unique, pool.map(lambda t: voice.speak(t, lang), unique)))
    return [{"at": e["at"], "kind": e["kind"], "text": t, "audio": urls[t]} for e, t in zip(events, texts)]


def record_impact(site_id: str, site: dict, date: str, plan: planner.DayPlan) -> bool:
    """Count a site-day's impact once, however often the plan is re-published."""
    if not store.first_time(f"impact#{site_id}#{date}"):
        return False
    metrics.emit(
        {"UnsafeHoursAvoided": plan.unsafe_hours_avoided, "WorkerHoursProtected": plan.worker_hours_protected, "SiteDaysPlanned": 1},
        {"Kind": "demo" if site.get("demo") else "site"},
    )
    return True


def publish(site_id: str, site: dict, date: str) -> dict:
    _, plan = compute(site, date)
    events = _with_tomorrow(site, date, plan.events)
    _, old = store.get_plan(site_id, date)
    names = schedules.publish_day(site_id, date, events, replace=old)
    store.put_plan(site_id, date, plan.to_dict(), names)
    try:
        audio = prepare_audio(events, site.get("lang", "hi"))
    except Exception:
        audio = []
    metrics.emit({"PlansPublished": 1})
    record_impact(site_id, site, date, plan)
    return {
        "date": date,
        "schedules": len(names),
        "next": names[:1],
        "unsafe_hours_avoided": plan.unsafe_hours_avoided,
        "worker_hours_protected": plan.worker_hours_protected,
        "events": audio,
    }


def brief(site: dict, date: str, lang: str) -> dict:
    """The day's plan as a short voice note for the crew's WhatsApp group. Fixed template."""
    _, plan = compute(site, date)
    c = plan.crew
    say = lambda hhmm: announce.spoken_time(hhmm, lang)  # noqa: E731
    is_today = date == today()
    if lang == "en":
        parts = [f"Chhaon plan for {site.get('name', 'the site')}, {'today' if is_today else 'tomorrow'}."]
        if not c.first_start:
            parts.append("It is too hot for this work at any time. No work in the sun.")
        else:
            parts.append(f"Work starts at {say(c.first_start)}.")
            parts += [f"No work from {say(a)} to {say(b)}." for a, b in c.stop_windows]
            parts.append(f"Work ends at {say(c.last_end)}.")
        if plan.new_workers and plan.new_workers.exposure_factor < 1:
            parts.append("Workers in their first week will work less; the supervisor will tell you when.")
        parts.append("Drink a glass of water every fifteen to twenty minutes, and rest in the shade. If you feel dizzy, sick, a bad headache or very weak, tell the supervisor at once. In an emergency call 108.")
    else:
        parts = [f"छाँव की ओर से {site.get('name', 'साइट')} के साथियों के लिए {'आज' if is_today else 'कल'} का प्लान।"]
        if not c.first_start:
            parts.append("इस काम के लिए आज कोई भी समय सुरक्षित नहीं। धूप में काम नहीं होगा।")
        else:
            parts.append(f"काम {say(c.first_start)} शुरू होगा।")
            parts += [f"{say(a)} से {say(b)} तक काम बंद रहेगा।" for a, b in c.stop_windows]
            parts.append(f"काम {say(c.last_end)} ख़त्म होगा।")
        if plan.new_workers and plan.new_workers.exposure_factor < 1:
            parts.append("पहले हफ़्ते वाले नए साथी आज कम काम करेंगे, सुपरवाइज़र समय बताएँगे।")
        parts.append("हर पंद्रह-बीस मिनट पर एक गिलास पानी पीजिए और छाँव में आराम कीजिए। चक्कर, उल्टी, तेज़ सिरदर्द या बहुत कमज़ोरी लगे तो तुरंत सुपरवाइज़र को बताइए। इमरजेंसी में 108 पर कॉल कीजिए।")
    text = " ".join(parts)
    return {"date": date, "lang": lang, "text": text, "audio": voice.speak(text, lang)}


def announce_event(site_id: str, event: dict, date: str | None = None) -> dict:
    site = store.get_site(site_id) or {}
    lang = site.get("lang", "hi")
    texts = {l: announce.text_for(event, l) for l in ("hi", "en")}
    audio = {lang: voice.speak(texts[lang], lang)}
    entry = store.add_feed(
        site_id,
        {"type": "announcement", "kind": event["kind"], "at": event.get("at"), "date": date, "text": texts, "audio": audio, "lang": lang},
    )
    metrics.emit({"AnnouncementsSent": 1})
    return entry


def replay(key: str, workload: str = "heavy") -> dict:
    meta = REPLAYS.get(key)
    if not meta:
        raise KeyError(key)
    wx = store.cached_weather(meta["lat"] + 0.001, meta["lon"] + 0.001, lambda: weather.archive(meta["lat"], meta["lon"], meta["date"]))
    cfg = planner.SiteConfig(lat=meta["lat"], lon=meta["lon"], workload=workload)
    slots, plan = planner.plan_from_weather(wx["hourly"], wx.get("utc_offset_seconds", 19800), cfg, meta["date"])
    return {"replay": {k: v for k, v in meta.items()}, "key": key, "plan": plan.to_dict(), "data": "ERA5 reanalysis via Open-Meteo archive (about 25 km grid, not a site measurement)"}
