"""Run Chhaon locally with no AWS account: the real Lambda handlers, in-memory
fakes for AWS, a tiny Step Functions simulator, and synthetic weather (or a saved
Open-Meteo response from data/fixtures).

    python dev/server.py            # http://localhost:8787
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tests import fakeaws  # noqa: E402

WORLD = fakeaws.install()
os.environ.update(TABLE_NAME="local", WEB_BUCKET="local", PROTOCOL_ARN="arn:local", ANNOUNCE_FN_ARN="arn:local", SCHEDULER_ROLE_ARN="arn:local", SCHEDULE_GROUP="local", ALERT_TOPIC_ARN="")

from chhaon import weather  # noqa: E402
from handlers import api, ask, jobs, protocol_task  # noqa: E402
from tests.test_core import synthetic_hourly  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
FIX = ROOT / "data" / "fixtures"


def _fixture(name):
    p = FIX / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def local_forecast(lat, lon, days=3):
    fx = _fixture("forecast-howrah")
    if fx:
        return fx
    today = datetime.now(IST).date()
    h = synthetic_hourly(today.isoformat(), 34, 26, 55, 88, lat, lon)
    h2 = synthetic_hourly((today + timedelta(days=1)).isoformat(), 35, 26, 52, 88, lat, lon)
    for k in h:
        h[k] = h[k][:24] + h2[k]
    return {"hourly": h, "utc_offset_seconds": 19800}


def local_archive(lat, lon, date):
    for name in ("archive-rourkela-2024-05-30", "archive-aurangabad-2024-05-30"):
        fx = _fixture(name)
        if fx and abs(fx["latitude"] - lat) < 0.2 and date == "2024-05-30":
            return fx
    return {"hourly": synthetic_hourly(date, 44, 31, 22, 60, lat, lon), "utc_offset_seconds": 19800}


weather.forecast = local_forecast
weather.archive = local_archive


# ---- the scheduler: fire due one-time schedules ----
def scheduler_loop():
    while True:
        now = datetime.now(IST).replace(tzinfo=None)
        for name, s in list(WORLD.schedules.items()):
            when = datetime.fromisoformat(s["ScheduleExpression"][3:-1])
            if when <= now:
                WORLD.schedules.pop(name, None)
                try:
                    jobs.announce(json.loads(s["Target"]["Input"]), None)
                except Exception as exc:
                    print("announce failed", exc)
        time.sleep(2)


# ---- a tiny Step Functions interpreter for the protocol ----
def run_protocol(inp: dict):
    state = dict(inp)

    def task(action, **extra):
        return protocol_task.handler({"action": action, "state": state, **extra}, None)

    def wait_token(question, timeout):
        token = f"tok-{inp['incident_id']}-{question}-{time.time()}"
        task("ask", question=question, token=token)
        end = time.time() + timeout
        while time.time() < end:
            for i, ts in enumerate(WORLD.task_success):
                if ts["token"] == token:
                    WORLD.task_success.pop(i)
                    return json.loads(ts["output"])
            time.sleep(0.5)
        return None

    state = task("begin")
    level = state["level"]
    while True:
        if level == "red":
            state = task("emergency")
            ans = wait_token("handover", state.get("handover_timeout", 300))
            task("close" if ans else "escalate")
            return
        if level == "green":
            task("care")
            return
        state = task("care")
        time.sleep(state.get("wait_seconds", 20))
        ans = wait_token("recheck", 900)
        if ans is None:
            task("escalate")
            return
        state = protocol_task.handler({"action": "decide", "state": {**state, "recheck": ans}}, None)
        level = state["level"]
        if level == "resolved":
            return


_orig_start = fakeaws.FakeClient.start_execution


def start_execution(self, stateMachineArn, name, input):
    out = _orig_start(self, stateMachineArn, name, input)
    threading.Thread(target=run_protocol, args=(json.loads(input),), daemon=True).start()
    return out


fakeaws.FakeClient.start_execution = start_execution


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def _api(self, method):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode() if length else None
        path, _, qs = self.path.partition("?")
        query = dict(p.split("=", 1) for p in qs.split("&") if "=" in p) if qs else None
        if query:
            from urllib.parse import unquote_plus
            query = {k: unquote_plus(v) for k, v in query.items()}
        ev = {"rawPath": path, "requestContext": {"http": {"method": method, "sourceIp": self.client_address[0]}}, "body": body, "queryStringParameters": query}
        res = (ask.handler if path == "/api/ask" else api.handler)(ev, None)
        data = res["body"].encode()
        self.send_response(res["statusCode"])
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        if self.path.startswith("/audio/"):
            self.send_response(200)
            self.send_header("content-type", "audio/mpeg")
            self.end_headers()
            self.wfile.write(WORLD.s3.get(self.path[1:], b""))
            return
        return super().do_GET()

    def do_POST(self):
        return self._api("POST")

    def do_PUT(self):
        return self._api("PUT")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    threading.Thread(target=scheduler_loop, daemon=True).start()
    print(f"Chhaon local: http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
