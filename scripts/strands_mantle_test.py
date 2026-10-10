"""Run the production Strands-on-Bedrock-Mantle engine from backend/chhaon/agent.py on this PC,
with fixed tool results, to check the SigV4-signed OpenAI client and the Strands tool loop."""
import os
import sys
import time

sys.path.insert(0, "build/winpy")
sys.path.insert(0, "backend")
os.environ.setdefault("MANTLE_REGION", "ap-south-1")
os.environ.setdefault("AWS_REGION", "ap-south-1")

from chhaon import agent, protocol  # noqa: E402

CHECK = {"workload": "heavy", "asked": {"start": "14:00", "end": "16:00", "max_wbgt": 31.2, "min_safe_minutes": 0, "ok": False},
         "best": [{"start": "17:00", "end": "19:00", "max_wbgt": 26.1, "min_safe_minutes": 45, "ok": True}]}
PLAN = {"date": "2026-10-10", "verdict": "stop_heavy", "work_starts": "06:00", "work_ends": "18:45", "stop_windows": [["10:00", "11:00"]], "peak_wbgt": 30.6, "peak_time": "10:00"}
tools = {
    "day_plan": lambda day="today": PLAN,
    "check_task": lambda day="today", start_hour=9, hours=2, workload=None, new_workers=False: {**CHECK, "args": [day, start_hour, hours, workload, new_workers]},
    "first_aid": lambda symptoms: protocol.guidance(protocol.classify(symptoms), "hi"),
}
for q in ("कल दोपहर 2 बजे ढलाई कर सकते हैं?", "When does heavy work stop tomorrow?", "एक साथी को चक्कर और उल्टी हो रही है, क्या करें?"):
    t0 = time.time()
    try:
        text, used = agent._strands_mantle(q, tools, agent._detect_lang(q))
        print(f"OK {time.time() - t0:.1f}s tools={used}\n   Q: {q}\n   A: {text}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAIL {type(e).__name__}: {e}")
