import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from tests import fakeaws

WORLD = fakeaws.install()
os.environ.update(
    TABLE_NAME="t", WEB_BUCKET="b", PROTOCOL_ARN="arn:sm", ANNOUNCE_FN_ARN="arn:fn", SCHEDULER_ROLE_ARN="arn:role", SCHEDULE_GROUP="g", ALERT_TOPIC_ARN="arn:topic"
)

from chhaon import agent, service, weather  # noqa: E402
from handlers import api, ask, jobs, protocol_task  # noqa: E402
from tests.test_core import synthetic_hourly  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


def fake_forecast(lat, lon, days=3):
    today = datetime.now(IST).date().isoformat()
    h = synthetic_hourly(today, 39, 27, 30, 70, lat, lon)
    tomorrow = (datetime.now(IST).date() + timedelta(days=1)).isoformat()
    h2 = synthetic_hourly(tomorrow, 39, 27, 30, 70, lat, lon)
    for k in h:
        h[k] = h[k][:24] + h2[k]
    return {"hourly": h, "utc_offset_seconds": 19800}


def fake_archive(lat, lon, date):
    return {"hourly": synthetic_hourly(date, 42, 30, 25, 65, lat, lon), "utc_offset_seconds": 19800}


weather.forecast = fake_forecast
weather.archive = fake_archive


def call(method, path, body=None, qs=None, ip="1.2.3.4", fn=api.handler):
    ev = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": ip}},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": qs,
    }
    res = fn(ev, None)
    return res["statusCode"], json.loads(res["body"])


class ApiFlow(unittest.TestCase):
    def test_full_demo_flow(self):
        code, demo = call("POST", "/api/demo")
        self.assertEqual(code, 201)
        sid = demo["site_id"]

        code, plan = call("GET", f"/api/sites/{sid}/plan", qs={"day": "today"})
        self.assertEqual(code, 200, plan)
        self.assertIn(plan["plan"]["verdict"], ("normal", "adjusted", "stop_heavy", "stop_all"))
        self.assertTrue(plan["plan"]["crew"]["hours"])

        code, pub = call("POST", f"/api/sites/{sid}/publish", {"day": "tomorrow"})
        self.assertEqual(code, 200, pub)
        self.assertGreater(pub["schedules"], 3)
        self.assertEqual(len(WORLD.schedules), pub["schedules"])
        one = next(iter(WORLD.schedules.values()))
        self.assertTrue(one["ScheduleExpression"].startswith("at("))
        self.assertEqual(one["ScheduleExpressionTimezone"], "Asia/Kolkata")
        self.assertEqual(one["ActionAfterCompletion"], "DELETE")

        # republish replaces, never duplicates
        call("POST", f"/api/sites/{sid}/publish", {"day": "tomorrow"})
        self.assertEqual(len(WORLD.schedules), pub["schedules"])

        code, t = call("POST", f"/api/sites/{sid}/test-announcement")
        self.assertEqual(code, 200, t)

        # the scheduler fires
        payload = json.loads(one["Target"]["Input"])
        out = jobs.announce(payload, None)
        self.assertTrue(out["ok"])
        code, feed = call("GET", f"/api/sites/{sid}/feed")
        self.assertEqual(feed["items"][-1]["type"], "announcement")
        self.assertTrue(feed["items"][-1]["audio"]["hi"].startswith("/audio/"))
        self.assertEqual(WORLD.polly[-1]["VoiceId"], "Kajal")

        code, prev = call("POST", f"/api/sites/{sid}/preview", {"kind": "pause", "until": "16:00", "lang": "hi"})
        self.assertEqual(code, 200)
        self.assertIn("16:00", prev["text"])

    def test_incident_amber_then_worse_escalates(self):
        _, demo = call("POST", "/api/demo", ip="5.5.5.5")
        sid = demo["site_id"]
        code, inc = call("POST", f"/api/sites/{sid}/incidents", {"worker": "Ramesh", "symptoms": ["dizzy", "vomiting"]}, ip="5.5.5.5")
        self.assertEqual(code, 201, inc)
        self.assertEqual(inc["level"], "amber")
        start = json.loads(WORLD.executions[-1]["input"])
        self.assertEqual(start["wait_seconds"], 20)  # demo site: compressed re-check

        state = protocol_task.handler({"action": "begin", "state": start}, None)
        state = protocol_task.handler({"action": "care", "state": state}, None)
        protocol_task.handler({"action": "ask", "question": "recheck", "token": "tok-1", "state": state}, None)
        code, seen = call("GET", f"/api/incidents/{inc['id']}")
        self.assertEqual(seen["pending"]["question"], "recheck")
        self.assertNotIn("token", seen["pending"])  # never leaked to the browser

        code, ans = call("POST", f"/api/incidents/{inc['id']}/answer", {"answer": "worse"})
        self.assertEqual(code, 200, ans)
        self.assertEqual(WORLD.task_success[-1]["token"], "tok-1")
        state = protocol_task.handler({"action": "decide", "state": {**state, "recheck": {"answer": "worse"}}}, None)
        self.assertEqual(state["level"], "red")
        state = protocol_task.handler({"action": "emergency", "state": state}, None)
        code, seen = call("GET", f"/api/incidents/{inc['id']}")
        self.assertEqual(seen["status"], "emergency")
        self.assertEqual(seen["hospitals"][0]["name"], "District Hospital")
        self.assertTrue(seen["guidance"]["call_108"])
        self.assertIn("EMERGENCY", WORLD.sns[-1]["Subject"])

        code, again = call("POST", f"/api/incidents/{inc['id']}/answer", {"answer": "better"})
        self.assertEqual(code, 409)

    def test_red_flag_is_immediate(self):
        _, demo = call("POST", "/api/demo", ip="6.6.6.6")
        code, inc = call("POST", f"/api/sites/{demo['site_id']}/incidents", {"symptoms": ["confused"], "lang": "en"}, ip="6.6.6.6")
        self.assertEqual(inc["level"], "red")
        self.assertIn("108", inc["guidance"]["steps"][0])

    def test_validation_and_limits(self):
        self.assertEqual(call("GET", "/api/sites/../../etc/plan")[0], 404)
        self.assertEqual(call("GET", "/api/sites/abc!/plan")[0], 400)
        self.assertEqual(call("POST", "/api/sites", {"lat": 999, "lon": 1})[0], 400)
        code, _ = call("POST", "/api/sites", {"name": "Tower B", "lat": 22.57, "lon": 88.36, "workload": "moderate", "crew": 12}, ip="9.9.9.9")
        self.assertEqual(code, 201)
        codes = [call("POST", "/api/demo", ip="7.7.7.7")[0] for _ in range(22)]
        self.assertIn(429, codes)

    def test_replay(self):
        code, r = call("GET", "/api/replay/rourkela-2024-05-30")
        self.assertEqual(code, 200, r)
        self.assertEqual(r["replay"]["official_window"], ["11:00", "15:00"])
        self.assertEqual(call("GET", "/api/replay/nowhere")[0], 404)

    def test_ask_falls_back_without_bedrock(self):
        _, demo = call("POST", "/api/demo", ip="8.8.8.8")
        code, res = call("POST", "/api/ask", {"site_id": demo["site_id"], "question": "कल दोपहर 2 बजे ढलाई कर सकते हैं?"}, ip="8.8.8.8", fn=ask.handler)
        self.assertEqual(code, 200, res)
        self.assertEqual(res["engine"], "rules")
        self.assertEqual(res["lang"], "hi")
        self.assertIn("WBGT", res["answer"])

    def test_agent_tools_direct(self):
        tools = agent.make_tools(service.DEMO_SITE, "en")
        p = tools["day_plan"]("today")
        self.assertIn("hours", p)
        c = tools["check_task"]("tomorrow", 14, 3, "heavy")
        self.assertIn("best", c)
        self.assertEqual(tools["first_aid"](["seizure"])["level"], "red")

    def test_morning_job_plans_real_sites_only(self):
        call("POST", "/api/demo", ip="4.4.4.4")
        code, real = call("POST", "/api/sites", {"name": "Tower C", "lat": 22.6, "lon": 88.4, "workload": "heavy"}, ip="4.4.4.4")
        self.assertEqual(code, 201)
        out = jobs.morning({}, None)
        sites = [service.store.get_site(i) for i in service.store.active_site_ids()]
        real_count = sum(1 for s in sites if s and s.get("auto_publish"))
        self.assertEqual(out["planned"], real_count)
        self.assertEqual(out["failed"], 0)


if __name__ == "__main__":
    unittest.main()
