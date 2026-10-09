"""Ask the live assistant a handful of real supervisor questions and print the plan next to the answers,
so each number in an answer can be checked against the planner. Usage: python scripts/ask_eval.py [BASE_URL]"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://d2cvj3mcid9pim.cloudfront.net").rstrip("/")
QUESTIONS = [
    "कल दोपहर 2 बजे ढलाई कर सकते हैं?",
    "kal subah 7 baje se 3 ghante chhat ka kaam ho sakta hai?",
    "When does heavy work stop today?",
    "एक मज़दूर को चक्कर आ रहा है और उल्टी हो रही है, क्या करें?",
    "Can the new workers carry bricks at 11 AM tomorrow?",
]


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/api" + path, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


code, demo = call("POST", "/demo")
print("demo", code, demo.get("site_id") if isinstance(demo, dict) else demo)
sid = demo["site_id"]
for day in ("today", "tomorrow"):
    code, p = call("GET", f"/sites/{sid}/plan?day={day}")
    plan = p["plan"]
    crew = plan["crew"]
    print(f"\n--- plan {day} {plan.get('date')}: verdict={plan['verdict']} stops={crew['stop_windows']} peak={plan['peak_wbgt']}@{plan['peak_time']}")
    print("    hour  wbgt  air   safe(acclim)  planned")
    for h in crew["hours"]:
        if h.get("status") != "off":
            print(f"    {h['start']}  {h['wbgt']:>4}  {h.get('air_temp', '')!s:>4}  {h['safe_minutes']:>4}          {h['work_minutes']:>4}")
    nw = plan.get("new_workers")
    if nw:
        print(f"    new workers: planned {nw.get('planned_minutes')} min, stops {nw.get('stop_windows')}")

for q in QUESTIONS:
    t0 = time.time()
    code, a = call("POST", "/ask", {"site_id": sid, "question": q})
    dt = time.time() - t0
    print(f"\nQ: {q}")
    if code != 200:
        print(f"   HTTP {code}: {a}")
        continue
    print(f"   [{a.get('engine')} {a.get('model', '')} tools={a.get('tools_used')} {dt:.1f}s{' FALLBACK ' + a.get('error', '') if a.get('model_unavailable') else ''}]")
    print(f"   A: {a.get('answer')}")
    time.sleep(1)
