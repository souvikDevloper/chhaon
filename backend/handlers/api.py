"""HTTP API: sites, plans, schedules, feed, incidents, replays, geocoding."""
from __future__ import annotations

import json
import os
import re
import traceback

import boto3

from chhaon import announce, listen, metrics, places, planner, protocol, schedules, service, store, voice, weather
from chhaon.http import HttpError, body, query, respond, source_ip, valid_id

_sfn = None

SITE_FIELDS = (
    "name", "lat", "lon", "workload", "crew", "new_workers", "new_worker_day", "shaded",
    "lang", "window_start", "window_end", "clothing",
)


def sfn():
    global _sfn
    if _sfn is None:
        _sfn = boto3.client("stepfunctions")
    return _sfn


def _clean_site(data: dict, base: dict | None = None) -> dict:
    site = dict(base or {})
    for k in SITE_FIELDS:
        if k in data and data[k] is not None:
            site[k] = data[k]
    site["name"] = str(site.get("name") or "My site")[:80]
    site["lang"] = "en" if site.get("lang") == "en" else "hi"
    try:
        site["lat"], site["lon"] = float(site["lat"]), float(site["lon"])
        for k in ("crew", "new_workers", "new_worker_day", "window_start", "window_end"):
            if k in site:
                site[k] = int(site[k])
        site["shaded"] = bool(site.get("shaded", False))
        planner.SiteConfig.from_dict(site)
        if "new_worker_day" in data or "new_workers" in data:
            site["new_workers_since"] = service.new_workers_since(site.get("new_worker_day", 1))
    except (KeyError, TypeError, ValueError) as exc:
        raise HttpError(400, f"invalid site: {exc}")
    return site


def _limit(event: dict, bucket: str, per_minute: int) -> None:
    if not store.allow(f"{bucket}#{source_ip(event)}", per_minute):
        raise HttpError(429, "too many requests, try again in a minute")


def _site(site_id: str) -> dict:
    site = store.get_site(valid_id(site_id))
    if not site:
        raise HttpError(404, "site not found")
    return site


def route(event: dict) -> dict:
    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "/")
    q = query(event)

    if path == "/api/health":
        return respond(200, {"ok": True, "date": service.today()})

    if path == "/api/demo" and method == "POST":
        _limit(event, "create", 20)
        site_id = store.new_id()
        site = {**service.DEMO_SITE, "auto_publish": False, "demo": True, "new_workers_since": service.new_workers_since(service.DEMO_SITE["new_worker_day"])}
        store.put_site(site_id, site, ttl_days=7)
        return respond(201, {"site_id": site_id, "site": site})

    if path == "/api/sites" and method == "POST":
        _limit(event, "create", 20)
        site = _clean_site(body(event))
        site["auto_publish"] = True
        site_id = store.new_id()
        store.put_site(site_id, site)
        return respond(201, {"site_id": site_id, "site": site})

    m = re.fullmatch(r"/api/sites/([^/]+)(/[a-z-]+)?", path)
    if m:
        site_id, sub = m.group(1), m.group(2) or ""
        site = _site(site_id)
        if sub == "" and method == "GET":
            return respond(200, {"site_id": site_id, "site": site})
        if sub == "" and method == "PUT":
            site = _clean_site(body(event), site)
            store.put_site(site_id, site, ttl_days=7 if site.get("demo") else 30)
            return respond(200, {"site_id": site_id, "site": site})
        if sub == "/plan" and method == "GET":
            date = service.resolve_day(q.get("day"))
            return respond(200, service.plan_payload(site_id, site, date))
        if sub == "/publish" and method == "POST":
            _limit(event, "publish", 10)
            date = service.resolve_day(body(event).get("day"))
            return respond(200, service.publish(site_id, site, date))
        if sub == "/test-announcement" and method == "POST":
            _limit(event, "test", 6)
            return respond(200, schedules.test_in(site_id, 60))
        if sub == "/preview" and method == "POST":
            _limit(event, "preview", 30)
            data = body(event)
            kind = data.get("kind", "rest")
            if kind not in announce.TEMPLATES:
                raise HttpError(400, "unknown announcement")
            ev = {"kind": kind, "minutes": int(data.get("minutes") or 15), "until": str(data.get("until") or "16:00")[:5]}
            lang = "en" if data.get("lang") == "en" else "hi"
            text = announce.text_for(ev, lang)
            return respond(200, {"text": text, "audio": voice.speak(text, lang)})
        if sub == "/speak" and method == "POST":
            _limit(event, "speak", 12)
            data = body(event)
            text = str(data.get("text") or "").strip()[:600]
            if not text:
                raise HttpError(400, "nothing to speak")
            lang = "en" if data.get("lang") == "en" else "hi"
            return respond(200, {"audio": voice.speak(text, lang)})
        if sub == "/brief" and method == "POST":
            _limit(event, "brief", 10)
            data = body(event)
            lang = "en" if data.get("lang") == "en" else "hi"
            return respond(200, service.brief(site, service.resolve_day(data.get("day")), lang))
        if sub == "/played" and method == "POST":
            _limit(event, "played", 60)
            metrics.emit({"AnnouncementsPlayed": 1}, {"Kind": "demo" if site.get("demo") else "site"})
            return respond(200, {"ok": True})
        if sub == "/feed" and method == "GET":
            return respond(200, {"items": store.feed(site_id, q.get("since"))})
        if sub == "/incidents" and method == "POST":
            _limit(event, "incident", 10)
            return respond(201, _start_incident(site_id, site, body(event)))
        raise HttpError(404, "not found")

    m = re.fullmatch(r"/api/incidents/([^/]+)(/answer)?", path)
    if m:
        inc_id = valid_id(m.group(1))
        if m.group(2) and method == "POST":
            return respond(200, _answer(inc_id, body(event)))
        inc = store.get_incident(inc_id)
        if not inc:
            raise HttpError(404, "incident not found")
        inc.get("pending", {}) and inc["pending"].pop("token", None)
        return respond(200, inc)

    if path == "/api/listen" and method == "POST":
        _limit(event, "listen", 10)
        return respond(200, listen.presign("en" if body(event).get("lang") == "en" else "hi"))

    if path == "/api/geocode" and method == "GET":
        _limit(event, "geocode", 30)
        text = (q.get("q") or "").strip()
        if len(text) < 3:
            raise HttpError(400, "query too short")
        return respond(200, {"results": places.geocode(text)})

    m = re.fullmatch(r"/api/replay/([a-z0-9-]+)", path)
    if m and method == "GET":
        try:
            workload = q.get("workload", "heavy")
            if workload not in ("light", "moderate", "heavy", "very_heavy"):
                raise HttpError(400, "bad workload")
            return respond(200, service.replay(m.group(1), workload), cache="public, max-age=86400")
        except KeyError:
            raise HttpError(404, "unknown replay")

    if path == "/api/replays" and method == "GET":
        return respond(200, {"items": [{"key": k, **{x: v[x] for x in ("place", "date")}} for k, v in service.REPLAYS.items()]}, cache="public, max-age=3600")

    raise HttpError(404, "not found")


def _start_incident(site_id: str, site: dict, data: dict) -> dict:
    symptoms = [s for s in (data.get("symptoms") or []) if s in protocol.ALL_SYMPTOMS][:10]
    if not symptoms:
        raise HttpError(400, "pick at least one symptom")
    lang = "en" if (data.get("lang") or site.get("lang")) == "en" else "hi"
    level = protocol.classify(symptoms)
    worker = str(data.get("worker") or ("साथी" if lang == "hi" else "Worker"))[:40]
    demo = bool(site.get("demo") or data.get("demo"))
    inc_id = store.new_id("i")
    inc = {
        "id": inc_id,
        "site_id": site_id,
        "worker": worker,
        "symptoms": symptoms,
        "level": level,
        "status": "open",
        "lang": lang,
        "demo": demo,
        "guidance": protocol.guidance(level, lang),
        "hospitals": [],
        "pending": None,
        "timeline": [{"t": store.now_iso(), "kind": "reported", "text": ", ".join(symptoms)}],
        "created": store.now_iso(),
    }
    store.put_incident(inc_id, inc)
    execution = sfn().start_execution(
        stateMachineArn=os.environ["PROTOCOL_ARN"],
        name=inc_id,
        input=json.dumps(
            {"incident_id": inc_id, "site_id": site_id, "level": level, "lang": lang, "wait_seconds": 20 if demo else 1800, "handover_timeout": 300 if demo else 3600}
        ),
    )
    store.update_incident(inc_id, lambda i: {**i, "execution_arn": execution["executionArn"]})
    store.add_feed(site_id, {"type": "incident", "incident_id": inc_id, "level": level, "worker": worker})
    metrics.emit({"Incidents": 1}, {"Level": level})
    inc["execution_arn"] = execution["executionArn"]
    return inc


ANSWERS = {"recheck": ("better", "same", "worse"), "handover": ("handed_over",)}


def _answer(inc_id: str, data: dict) -> dict:
    inc = store.get_incident(inc_id)
    if not inc:
        raise HttpError(404, "incident not found")
    pending = inc.get("pending") or {}
    answer = data.get("answer")
    if not pending.get("token"):
        raise HttpError(409, "nothing to answer right now")
    if answer not in ANSWERS.get(pending.get("question"), ()):
        raise HttpError(400, "invalid answer")
    sfn().send_task_success(taskToken=pending["token"], output=json.dumps({"answer": answer}))

    def apply(i):
        i["pending"] = None
        i["timeline"].append({"t": store.now_iso(), "kind": "answer", "text": answer})
        return i

    inc = store.update_incident(inc_id, apply)
    return {"ok": True, "status": inc.get("status")}


def handler(event, context):
    try:
        return route(event)
    except HttpError as e:
        return respond(e.status, {"error": e.message})
    except weather.WeatherError as e:
        return respond(503, {"error": f"weather forecast unavailable: {e}"})
    except ValueError as e:
        return respond(400, {"error": str(e)})
    except Exception:
        traceback.print_exc()
        return respond(500, {"error": "internal error"})
