"""The supervisor's assistant: Amazon Bedrock with tools.

The model writes the words. Every number and every safety decision comes from a
tool that runs the same deterministic planner the rest of Chhaon uses.

Engines, in order: Bedrock's OpenAI-compatible endpoint (bedrock-mantle,
gpt-oss-120b by default) signed with the function's IAM role; then the Strands
Agents SDK or the Converse API on bedrock-runtime (Nova 2 Lite). If no model
answers in time, a rule-based answer is returned and labelled as such.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
import urllib.error
import urllib.request

import boto3

from . import announce, planner, protocol, service

MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-2-lite-v1:0")
# Bedrock's OpenAI-compatible endpoint (bedrock-mantle), signed with the function's own IAM role.
MANTLE_MODEL = os.environ.get("MANTLE_MODEL", "openai.gpt-oss-120b")
MANTLE_REGION = os.environ.get("MANTLE_REGION", os.environ.get("AWS_REGION", "ap-south-1"))
DEADLINE_S = float(os.environ.get("AGENT_DEADLINE_S", "18"))
COOLDOWN_S = 300  # after a throttle or timeout, answer from the rules for 5 minutes
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
_blocked_until: dict[str, float] = {}  # per backend: "mantle" (bedrock-mantle) or "runtime" (bedrock-runtime)

SYSTEM = """You are Chhaon, a heat-safety assistant for construction site supervisors in India.
Rules:
- Reply in the language and script of the question. Hindi or Hinglish question: answer in simple Hindi (Devanagari). English question: simple English only, no Hindi words.
- Say times the way people speak: in Hindi "दोपहर 2 बजे", "शाम 5 से 7 बजे तक" (not "14:00" or "17-19 बजे"); in English "2 PM", "5 to 7 PM".
- Use only numbers returned by tools. Never guess a temperature, WBGT or time. Call a tool first.
- Day: "कल" / "kal" / "tomorrow" means day="tomorrow"; "आज" / "aaj" / "today" or no day means day="today". Say the same day back in the answer.
- A question about a specific time or task ("कल दोपहर 2 बजे ढलाई?") needs check_task with a 24-hour start_hour (सुबह 7 बजे = 7, दोपहर 2 बजे = 14, शाम 5 बजे = 17). If no duration is given, use 2 hours. If the question is about new workers (नए मज़दूर, first week), set new_workers=true. General questions about the day need day_plan.
- Workload: leave it out to use the site's crew workload. Set it only when the task is clearly different: light = supervising, measuring, driving; moderate = plastering, painting, tying rebar; heavy = carrying bricks or cement, concreting (ढलाई), digging, shovelling.
- Reading check_task: asked.ok is the answer (true only if every hour allows at least 45 work minutes). min_safe_minutes is how many minutes of each hour may be worked; the rest is rest in shade. best lists safer windows; prefer ones with ok=true.
- Reading day_plan: safe_work_min_per_hour is the limit; planned_work_min is what the plan schedules. Do not mix them up.
- Be short: at most 3 short sentences (about 50 words), plain text, no markdown. Lead with the decision (yes / no / which time), then the reason with the WBGT number, then one practical tip.
- WBGT is the heat-stress measure (sun, humidity, wind, air temperature). Explain it in plain words if needed: in Hindi "धूप + उमस का असर", in English "sun + humidity".
- If anyone is confused, unconscious, having a seizure or has hot dry skin, tell them to call 108 immediately and start cooling. Use the first_aid tool.
- You do not change the plan; you explain it and suggest safer times."""

TOOL_SPECS = [
    {
        "name": "day_plan",
        "description": "The site's heat-safe plan for today or tomorrow: verdict, work start/end, stop windows, peak WBGT, unsafe hours avoided, and every hour's WBGT and safe work minutes.",
        "schema": {"type": "object", "properties": {"day": {"type": "string", "enum": ["today", "tomorrow"]}}, "required": ["day"]},
    },
    {
        "name": "check_task",
        "description": "Check if a task of N hours starting at an hour (0-23) is heat-safe for a workload, and get the 3 safest alternative windows.",
        "schema": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "enum": ["today", "tomorrow"], "description": "कल / kal = tomorrow"},
                "start_hour": {"type": "integer", "minimum": 0, "maximum": 23},
                "hours": {"type": "integer", "minimum": 1, "maximum": 10},
                "workload": {"type": "string", "enum": ["light", "moderate", "heavy", "very_heavy"]},
                "new_workers": {"type": "boolean", "description": "true if the question is about workers in their first week on site (stricter limits)"},
            },
            "required": ["day", "start_hour", "hours"],
        },
    },
    {
        "name": "first_aid",
        "description": "Heat-illness first aid steps from India's national guidelines for given symptoms.",
        "schema": {
            "type": "object",
            "properties": {"symptoms": {"type": "array", "items": {"type": "string", "enum": list(protocol.ALL_SYMPTOMS)}}},
            "required": ["symptoms"],
        },
    },
]


def make_tools(site: dict, lang: str) -> dict:
    """The agent's tools. `_state` records every call (name and arguments) and the last
    first-aid guidance, so the answer can show its evidence and the fixed protocol text."""
    cache: dict[str, tuple] = {}
    state: dict = {"trace": [], "first_aid": None}

    def _plan(day: str):
        date = service.resolve_day(day)
        if date not in cache:
            cache[date] = service.compute(site, date)
        return date, cache[date]

    def day_plan(day: str = "today") -> dict:
        state["trace"].append({"tool": "day_plan", "args": {"day": day}})
        date, (slots, p) = _plan(day)
        c = p.crew
        return {
            "date": date,
            "workload": p.workload,
            "verdict": p.verdict,
            "work_starts": c.first_start,
            "work_ends": c.last_end,
            "stop_windows": c.stop_windows,
            "stop_windows_said": [f"{announce.spoken_time(a, lang)} – {announce.spoken_time(b, lang)}" for a, b in c.stop_windows],
            "peak_wbgt": p.peak_wbgt,
            "peak_time": p.peak_time,
            "unsafe_hours_in_normal_9_to_6_shift": p.unsafe_hours_normal,
            "unsafe_hours_avoided": p.unsafe_hours_avoided,
            "work_minutes_planned": c.planned_minutes,
            "work_minutes_target": c.target_minutes,
            "hours": [
                {"time": h.start, "wbgt": h.wbgt, "air_temp": h.air_temp, "safe_work_min_per_hour": h.safe_minutes, "planned_work_min": h.work_minutes}
                for h in c.hours
                if h.status != "off"
            ],
            "new_workers": None
            if not p.new_workers
            else {"work_minutes_planned": p.new_workers.planned_minutes, "stop_windows": p.new_workers.stop_windows},
        }

    def check_task(day: str = "today", start_hour: int = 9, hours: int = 2, workload: str | None = None, new_workers: bool = False) -> dict:
        date, (slots, p) = _plan(day)
        new = new_workers.strip().lower() == "true" if isinstance(new_workers, str) else bool(new_workers)
        args = {"day": day, "start_hour": int(start_hour), "hours": int(hours)}
        if workload:
            args["workload"] = workload
        if new:
            args["new_workers"] = True
        state["trace"].append({"tool": "check_task", "args": args})
        res = planner.check_window(slots, service.site_config(site, date), int(start_hour), int(hours), workload or None, acclimatised=not new)
        res["date"] = date
        return res

    def first_aid(symptoms: list[str]) -> dict:
        state["trace"].append({"tool": "first_aid", "args": {"symptoms": list(symptoms)}})
        level = protocol.classify(symptoms)
        out = protocol.guidance(level, lang)
        state["first_aid"] = out
        return out

    return {"day_plan": day_plan, "check_task": check_task, "first_aid": first_aid, "_state": state}


def _detect_lang(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    hinglish = ("kya", "kal", "aaj", "baje", "kaam", "garmi", "dhoop", "sakte", "karna", "nahi", "hai")
    words = set(re.findall(r"[a-z]+", text.lower()))
    return "hi" if len(words & set(hinglish)) >= 2 else "en"


def _bedrock():
    from botocore.config import Config

    return boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 2, "mode": "standard"}, read_timeout=20, connect_timeout=5))


def _converse(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    client = _bedrock()
    tool_config = {"tools": [{"toolSpec": {"name": t["name"], "description": t["description"], "inputSchema": {"json": t["schema"]}}} for t in TOOL_SPECS]}
    messages = [{"role": "user", "content": [{"text": question}]}]
    used: list[str] = []
    for _ in range(5):
        res = client.converse(
            modelId=MODEL_ID,
            system=[{"text": _system(lang)}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 500, "temperature": 0.2},
        )
        msg = res["output"]["message"]
        messages.append(msg)
        calls = [b["toolUse"] for b in msg["content"] if "toolUse" in b]
        if not calls:
            text = " ".join(b["text"] for b in msg["content"] if "text" in b).strip()
            text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.S).strip()
            return text, used
        results = []
        for call in calls:
            used.append(call["name"])
            try:
                out = tools[call["name"]](**(call.get("input") or {}))
                results.append({"toolResult": {"toolUseId": call["toolUseId"], "content": [{"json": out}], "status": "success"}})
            except Exception as exc:  # tool errors go back to the model
                results.append({"toolResult": {"toolUseId": call["toolUseId"], "content": [{"text": f"error: {exc}"}], "status": "error"}})
        messages.append({"role": "user", "content": results})
    return ("माफ़ कीजिए, अभी जवाब नहीं बन पाया।" if lang == "hi" else "Sorry, I could not finish that answer."), used


def _mantle_post(body: dict, timeout: float = 15.0) -> dict:
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    url = f"https://bedrock-mantle.{MANTLE_REGION}.api.aws/v1/chat/completions"
    data = json.dumps(body).encode()
    req = AWSRequest(method="POST", url=url, data=data, headers={"content-type": "application/json"})
    creds = boto3.Session().get_credentials().get_frozen_credentials()
    SigV4Auth(creds, "bedrock-mantle", MANTLE_REGION).add_auth(req)
    http = urllib.request.Request(url, data=data, headers=dict(req.headers.items()), method="POST")
    try:
        with urllib.request.urlopen(http, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"mantle HTTP {e.code}: {detail}") from None


def _mantle(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    """Chat Completions tool loop on bedrock-mantle."""
    specs = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["schema"]}} for t in TOOL_SPECS]
    system = _system(lang)
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    extra = {"reasoning_effort": "low"} if "gpt-oss" in MANTLE_MODEL else {}
    used: list[str] = []
    for _ in range(5):
        body = {"model": MANTLE_MODEL, "messages": messages, "tools": specs, "tool_choice": "auto", "max_tokens": 900, "temperature": 0.2, **extra}
        try:
            res = _mantle_post(body)
        except RuntimeError as exc:
            if extra and "HTTP 400" in str(exc):
                extra = {}
                continue
            raise
        msg = res["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.S)
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # the UI shows plain text
            text = re.sub(r"\s*\n+\s*", " ", text).strip()
            return text, used
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            used.append(name)
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
                out = tools[name](**args)
            except Exception as exc:  # tool errors go back to the model
                out = {"error": str(exc)}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(out, ensure_ascii=False)})
    return ("माफ़ कीजिए, अभी जवाब नहीं बन पाया।" if lang == "hi" else "Sorry, I could not finish that answer."), used


def _strands_tools(tools: dict, used: list[str]) -> list:
    from strands import tool  # optional dependency, packaged as a Lambda layer

    @tool
    def day_plan(day: str = "today") -> dict:
        """The site's heat-safe plan for today or tomorrow: verdict, work start/end, stop windows, peak WBGT, and every hour's WBGT, safe work minutes (the limit) and planned work minutes.

        Args:
            day: "today" or "tomorrow" (कल / kal = tomorrow)
        """
        used.append("day_plan")
        return tools["day_plan"](day)

    @tool
    def check_task(day: str, start_hour: int, hours: int = 2, workload: str = "", new_workers: bool = False) -> dict:
        """Check if a task of N hours starting at an hour is heat-safe, and get the safest alternative windows.

        Args:
            day: "today" or "tomorrow" (कल / kal = tomorrow)
            start_hour: 24-hour clock, 0-23 (दोपहर 2 बजे = 14)
            hours: how long the task takes, 1-10
            workload: leave empty for the site's crew workload; else light, moderate, heavy or very_heavy
            new_workers: true if the question is about workers in their first week (stricter limits)
        """
        used.append("check_task")
        return tools["check_task"](day, start_hour, hours, workload or None, new_workers)

    @tool
    def first_aid(symptoms: list[str]) -> dict:
        """Heat-illness first aid from India's national guidelines.

        Args:
            symptoms: any of confused, unconscious, seizure, hot_dry_skin, cannot_drink, dizzy, headache, vomiting, nausea, weak, heavy_sweating, fainted_recovered, cramps, rash
        """
        used.append("first_aid")
        return tools["first_aid"](symptoms)

    return [day_plan, check_task, first_aid]


def _system(lang: str) -> str:
    from datetime import datetime

    now = datetime.now(service.IST).strftime("%H:%M")
    return SYSTEM + f"\nToday is {service.today()}, time now {now} (Asia/Kolkata). Reply language: {'Hindi' if lang == 'hi' else 'English'}."


def _mantle_openai_client():
    """An OpenAI client for Bedrock's OpenAI-compatible endpoint, signing every request with
    SigV4 from the Lambda role (no API key). The HTTP client ignores close() so the Strands
    model can open and close its client per request while we reuse the connection."""
    import httpx
    import openai
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    class SigV4(httpx.Auth):
        requires_request_body = True

        def auth_flow(self, request):
            creds = boto3.Session().get_credentials().get_frozen_credentials()
            signed = AWSRequest(method=request.method, url=str(request.url), data=request.content,
                                headers={"content-type": request.headers.get("content-type", "application/json")})
            SigV4Auth(creds, "bedrock-mantle", MANTLE_REGION).add_auth(signed)
            for k, v in signed.headers.items():
                request.headers[k] = v
            yield request

    class KeepOpen(httpx.AsyncClient):
        async def aclose(self) -> None:  # closed by us at the end of the question
            pass

        async def really_close(self) -> None:
            await super().aclose()

    http = KeepOpen(auth=SigV4(), timeout=httpx.Timeout(15.0, connect=5.0))
    client = openai.AsyncOpenAI(api_key="sigv4", base_url=f"https://bedrock-mantle.{MANTLE_REGION}.api.aws/v1", http_client=http, max_retries=1)
    return client, http


def _strands_mantle(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    """Strands Agents drives the tool loop; the model is gpt-oss on Bedrock (bedrock-mantle)."""
    import asyncio

    from strands import Agent
    from strands.models.openai import OpenAIModel

    used: list[str] = []
    client, http = _mantle_openai_client()
    params = {"max_tokens": 900, "temperature": 0.2}
    if "gpt-oss" in MANTLE_MODEL:
        params["reasoning_effort"] = "low"
    import inspect

    if "client" in inspect.signature(OpenAIModel.__init__).parameters:  # newer Strands: inject the client
        model = OpenAIModel(client=client, model_id=MANTLE_MODEL, params=params)
    else:  # older Strands builds the client from these arguments
        model = OpenAIModel(client_args={"api_key": "sigv4", "base_url": str(client.base_url), "http_client": http, "max_retries": 1}, model_id=MANTLE_MODEL, params=params)
    agent = Agent(model=model, system_prompt=_system(lang), tools=_strands_tools(tools, used), callback_handler=None)
    try:
        result = agent(question)
    finally:
        try:
            asyncio.run(http.really_close())
        except Exception:
            pass
    text = re.sub(r"<thinking>.*?</thinking>", "", str(result), flags=re.S)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"\s*\n+\s*", " ", text).strip(), used


def _strands(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    """Strands Agents with Nova 2 Lite on bedrock-runtime (needs bedrock-runtime quota)."""
    from botocore.config import Config
    from strands import Agent
    from strands.models import BedrockModel

    used: list[str] = []
    model = BedrockModel(model_id=MODEL_ID, temperature=0.2, max_tokens=500, boto_client_config=Config(retries={"max_attempts": 2, "mode": "standard"}, read_timeout=20))
    agent = Agent(model=model, system_prompt=_system(lang), tools=_strands_tools(tools, used), callback_handler=None)
    result = agent(question)
    text = re.sub(r"<thinking>.*?</thinking>", "", str(result), flags=re.S).strip()
    return text, used


SYMPTOM_WORDS = {
    "confused": ("confus", "उलझन", "भ्रम", "बहकी", "बहकने", "पहचान नहीं"),
    "unconscious": ("unconscious", "not waking", "बेहोश", "behosh"),
    "seizure": ("seizure", "दौरा", "मिर्गी", "jhatke", "झटके"),
    "hot_dry_skin": ("hot dry skin", "not sweating", "पसीना नहीं", "पसीना बंद"),
    "dizzy": ("dizz", "चक्कर", "chakkar"),
    "headache": ("headache", "सिरदर्द", "सिर दर्द", "sar dard", "sir dard"),
    "vomiting": ("vomit", "उल्टी", "ulti"),
    "nausea": ("nause", "जी मिचला", "मितली", "ji michla"),
    "weak": ("weak", "कमज़ोरी", "कमजोरी", "kamzori"),
    "fainted_recovered": ("faint", "गिर गया", "गिर पड़ा"),
    "cramps": ("cramp", "ऐंठन", "ainthan"),
    "rash": ("rash", "घमौरी", "ghamori"),
}


def _rule_based(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    q = question.lower()
    found = [s for s, words in SYMPTOM_WORDS.items() if any(w in q for w in words)]
    if found:
        g = tools["first_aid"](found)
        tail = "नीचे दिए कदम अभी कीजिए।" if lang == "hi" else "Do the steps below now."
        if g["call_108"]:
            tail = ("अभी 108 पर कॉल कीजिए। " if lang == "hi" else "Call 108 now. ") + tail
        return f"{g['title']}{'।' if lang == 'hi' else '.'} {tail}", ["first_aid"]
    day = "tomorrow" if any(w in q for w in ("kal", "कल", "tomorrow")) else "today"
    m = re.search(r"(\d{1,2})\s*(?:baje|बजे|pm|am|:00)", q) or re.search(r"\b(\d{1,2})\b(?!\s*(?:ghante|घंटे|hours?|hrs?|मिनट|min))", q)
    if m:
        h = int(m.group(1))
        if any(w in q for w in ("pm", "dopahar", "दोपहर", "शाम", "sham", "evening", "afternoon")) and h < 12:
            h += 12
        if h < 6:
            h += 12
        d = re.search(r"(\d{1,2})\s*(?:ghante|घंटे|hours?|hrs?)", q)
        n = max(1, min(10, int(d.group(1)))) if d else 2
        new = any(w in q for w in ("new worker", "नए मज़दूर", "नए मजदूर", "नये", "naye", "first week"))
        res = tools["check_task"](day, h, n, None, new)
        a, b = res["asked"], next((o for o in res["best"] if o["ok"]), res["best"][0] if res["best"] else None)
        if not a:
            return ("उस समय का पूर्वानुमान नहीं मिला।" if lang == "hi" else "No forecast for that time."), ["check_task"]
        if lang == "hi":
            verdict = "हाँ, कर सकते हैं" if a["ok"] else "नहीं, उस समय सुरक्षित नहीं"
            alt = f" बेहतर समय: {b['start']}–{b['end']} (WBGT {b['max_wbgt']}°C)।" if b and not a["ok"] else ""
            return f"{verdict}। {a['start']}–{a['end']} में WBGT {a['max_wbgt']}°C तक, हर घंटे सिर्फ़ {a['min_safe_minutes']} मिनट काम।{alt}", ["check_task"]
        verdict = "Yes, that works" if a["ok"] else "No, that window is not heat-safe"
        alt = f" Better window: {b['start']}–{b['end']} (WBGT {b['max_wbgt']}°C)." if b and not a["ok"] else ""
        return f"{verdict}. WBGT reaches {a['max_wbgt']}°C between {a['start']} and {a['end']}; {a['min_safe_minutes']} work minutes per hour at most.{alt}", ["check_task"]
    p = tools["day_plan"](day)
    stops = ", ".join(f"{s}–{e}" for s, e in p["stop_windows"]) or ("कोई नहीं" if lang == "hi" else "none")
    when = ("कल" if day == "tomorrow" else "आज") if lang == "hi" else ("Tomorrow" if day == "tomorrow" else "Today")
    if lang == "hi":
        return f"{when} काम {p['work_starts']} से शुरू। भारी काम बंद: {stops}। सबसे ज़्यादा गर्मी {p['peak_time']} पर (WBGT {p['peak_wbgt']}°C)।", ["day_plan"]
    return f"{when}: work starts {p['work_starts']}. Heavy work stops: {stops}. Peak heat at {p['peak_time']} (WBGT {p['peak_wbgt']}°C).", ["day_plan"]


def ask(site: dict, question: str, lang: str | None = None) -> dict:
    """Bedrock Mantle, then Strands and Converse on bedrock-runtime, then rules, within a hard deadline.

    Each model call runs in a worker thread with a deadline (Strands retries throttling with long
    backoff). A throttle or timeout puts that backend on a short cooldown, so the next questions
    go straight to a backend that works.
    """
    lang = lang if lang in ("hi", "en") else _detect_lang(question)
    tools = make_tools(site, lang)
    errors: list[str] = []
    deadline = time.monotonic() + DEADLINE_S
    engines = (
        ("strands", _strands_mantle, "strands-mantle"),  # Strands Agents + gpt-oss on Bedrock
        ("bedrock-mantle", _mantle, "mantle"),  # same model, our own tool loop
        ("strands-nova", _strands, "runtime"),
        ("converse", _converse, "runtime"),
    )
    for engine, run, backend in engines:
        if time.time() < _blocked_until.get(backend, 0):
            errors.append(f"{engine}:cooldown")
            continue
        remaining = deadline - time.monotonic()
        if remaining < 2:
            errors.append(f"{engine}:no-time")
            break
        tools["_state"]["trace"].clear()
        tools["_state"]["first_aid"] = None
        future = _pool.submit(run, question, tools, lang)
        try:
            text, used = future.result(timeout=remaining)
            if text:
                model = MANTLE_MODEL if engine in ("strands", "bedrock-mantle") else MODEL_ID
                return _result({"answer": text, "tools_used": used, "engine": engine, "model": model, "lang": lang}, tools)
        except ImportError:
            continue
        except concurrent.futures.TimeoutError:
            errors.append(f"{engine}:Timeout")
            _blocked_until[backend] = time.time() + COOLDOWN_S
        except Exception as exc:
            errors.append(f"{engine}:{type(exc).__name__}")
            text = f"{type(exc).__name__} {exc}"
            if backend == "runtime" and any(k in text for k in ("Throttl", "AccessDenied", "Too many tokens")):
                _blocked_until[backend] = time.time() + COOLDOWN_S
            elif backend in ("mantle", "strands-mantle"):
                _blocked_until[backend] = time.time() + 60
    tools["_state"]["trace"].clear()
    text, used = _rule_based(question, tools, lang)
    return _result({
        "answer": text,
        "tools_used": used,
        "engine": "rules",
        "model_unavailable": True,
        "error": ",".join(errors) or "unavailable",
        "lang": lang,
    }, tools)


def _result(res: dict, tools: dict) -> dict:
    """Attach the tool trace, and the fixed first-aid protocol whenever first aid was asked:
    the model may paraphrase, but the steps shown and spoken are the national guideline's own."""
    state = tools["_state"]
    res["trace"] = state["trace"][-6:]
    if state["first_aid"]:
        res["protocol"] = state["first_aid"]
    return res
