"""Which bedrock-mantle model (ap-south-1) handles a Hindi question with tool calling best? SigV4, local creds."""
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "build/pydeps")
import botocore.session  # noqa: E402
from botocore.auth import SigV4Auth  # noqa: E402
from botocore.awsrequest import AWSRequest  # noqa: E402

REGION = "ap-south-1"
URL = f"https://bedrock-mantle.{REGION}.api.aws/v1/chat/completions"
creds = botocore.session.get_session().get_credentials()

TOOLS = [{
    "type": "function",
    "function": {
        "name": "check_task",
        "description": "Check if a task of N hours starting at an hour (0-23) is heat-safe, and get the safest alternative windows.",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string", "enum": ["today", "tomorrow"]},
            "start_hour": {"type": "integer"}, "hours": {"type": "integer"}}, "required": ["day", "start_hour", "hours"]},
    },
}]
SYSTEM = ("You are Chhaon, a heat-safety assistant for construction site supervisors in India. Reply in the language of the "
          "question (Hindi in Devanagari for Hindi). Use only numbers from tools. At most 3 short sentences.")
QUESTION = open("scripts/fixtures/ask-hi.txt", encoding="utf-8").read().strip()
TOOL_RESULT = {"asked": {"start": "14:00", "end": "16:00", "max_wbgt": 31.2, "min_safe_minutes": 0, "ok": False},
               "best": [{"start": "06:00", "end": "08:00", "max_wbgt": 27.9, "min_safe_minutes": 30, "ok": False},
                        {"start": "17:00", "end": "19:00", "max_wbgt": 26.1, "min_safe_minutes": 45, "ok": True}]}


def post(body):
    data = json.dumps(body).encode()
    req = AWSRequest(method="POST", url=URL, data=data, headers={"content-type": "application/json"})
    SigV4Auth(creds, "bedrock-mantle", REGION).add_auth(req)
    r = urllib.request.Request(URL, data=data, headers=dict(req.headers.items()), method="POST")
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


for model, extra in (("openai.gpt-oss-120b", {"reasoning_effort": "low"}), ("qwen.qwen3-235b-a22b-2507", {}),
                     ("mistral.mistral-large-3-675b-instruct", {}), ("openai.gpt-oss-20b", {"reasoning_effort": "low"})):
    t0 = time.time()
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": QUESTION}]
    code, res = post({"model": model, "messages": msgs, "tools": TOOLS, "tool_choice": "auto", "max_tokens": 800, "temperature": 0.2, **extra})
    if code != 200 and extra:
        code, res = post({"model": model, "messages": msgs, "tools": TOOLS, "tool_choice": "auto", "max_tokens": 800, "temperature": 0.2})
        extra = {}
    if code != 200:
        print(f"[{model}] step1 HTTP {code}: {res}")
        continue
    msg = res["choices"][0]["message"]
    calls = msg.get("tool_calls") or []
    t1 = time.time()
    if not calls:
        print(f"[{model}] no tool call ({t1 - t0:.1f}s): {str(msg.get('content'))[:200]}")
        continue
    call = calls[0]
    msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
    msgs.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(TOOL_RESULT)})
    code, res2 = post({"model": model, "messages": msgs, "tools": TOOLS, "max_tokens": 800, "temperature": 0.2, **extra})
    t2 = time.time()
    if code != 200:
        print(f"[{model}] step2 HTTP {code}: {res2}")
        continue
    answer = (res2["choices"][0]["message"].get("content") or "").strip().replace("\n", " ")
    usage = res2.get("usage", {})
    print(f"[{model}] tool={call['function']['name']} args={call['function']['arguments']} | {t1 - t0:.1f}s + {t2 - t1:.1f}s | tokens={usage.get('total_tokens')}")
    print(f"    answer: {answer[:400]}")
