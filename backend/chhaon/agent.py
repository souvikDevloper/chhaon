"""The supervisor's assistant: Amazon Bedrock (Nova 2 Lite) with tools.

The model writes the words. Every number and every safety decision comes from a
tool that runs the same deterministic planner the rest of Chhaon uses. If the
Strands Agents SDK is packaged it drives the loop; otherwise the same tools run
through the Bedrock Converse API directly. If Bedrock is unavailable, a rule
based answer is returned and labelled as such.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable

import boto3

from . import planner, protocol, service

MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-2-lite-v1:0")

SYSTEM = """You are Chhaon, a heat-safety assistant for construction site supervisors in India.
Rules:
- Reply in the language and script of the question. Hindi or Hinglish question: answer in simple Hindi (Devanagari). English question: simple English.
- Use only numbers returned by tools. Never guess a temperature, WBGT or time. Call a tool first.
- Be short: at most 4 sentences. Lead with the decision (yes / no / which time), then the reason with the WBGT number, then one practical tip.
- WBGT is the heat-stress measure (sun, humidity, wind, air temperature). Explain it in plain words if needed, e.g. "धूप + उमस का असर".
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
                "day": {"type": "string", "enum": ["today", "tomorrow"]},
                "start_hour": {"type": "integer", "minimum": 0, "maximum": 23},
                "hours": {"type": "integer", "minimum": 1, "maximum": 10},
                "workload": {"type": "string", "enum": ["light", "moderate", "heavy", "very_heavy"]},
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


def make_tools(site: dict, lang: str) -> dict[str, Callable[..., dict]]:
    cache: dict[str, tuple] = {}

    def _plan(day: str):
        date = service.resolve_day(day)
        if date not in cache:
            cache[date] = service.compute(site, date)
        return date, cache[date]

    def day_plan(day: str = "today") -> dict:
        date, (slots, p) = _plan(day)
        c = p.crew
        return {
            "date": date,
            "workload": p.workload,
            "verdict": p.verdict,
            "work_starts": c.first_start,
            "work_ends": c.last_end,
            "stop_windows": c.stop_windows,
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

    def check_task(day: str = "today", start_hour: int = 9, hours: int = 2, workload: str | None = None) -> dict:
        date, (slots, p) = _plan(day)
        res = planner.check_window(slots, service.site_config(site), int(start_hour), int(hours), workload)
        res["date"] = date
        return res

    def first_aid(symptoms: list[str]) -> dict:
        level = protocol.classify(symptoms)
        return protocol.guidance(level, lang)

    return {"day_plan": day_plan, "check_task": check_task, "first_aid": first_aid}


def _detect_lang(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    hinglish = ("kya", "kal", "aaj", "baje", "kaam", "garmi", "dhoop", "sakte", "karna", "nahi", "hai")
    words = set(re.findall(r"[a-z]+", text.lower()))
    return "hi" if len(words & set(hinglish)) >= 2 else "en"


def _converse(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    client = boto3.client("bedrock-runtime")
    tool_config = {"tools": [{"toolSpec": {"name": t["name"], "description": t["description"], "inputSchema": {"json": t["schema"]}}} for t in TOOL_SPECS]}
    messages = [{"role": "user", "content": [{"text": question}]}]
    used: list[str] = []
    for _ in range(5):
        res = client.converse(
            modelId=MODEL_ID,
            system=[{"text": SYSTEM + f"\nToday is {service.today()} (Asia/Kolkata). Reply language: {'Hindi' if lang == 'hi' else 'English'}."}],
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


def _strands(question: str, tools: dict, lang: str) -> tuple[str, list[str]]:
    from strands import Agent, tool  # optional dependency, packaged as a Lambda layer
    from strands.models import BedrockModel

    used: list[str] = []

    @tool
    def day_plan(day: str = "today") -> dict:
        """The site's heat-safe plan for today or tomorrow (WBGT per hour, safe minutes, stop windows)."""
        used.append("day_plan")
        return tools["day_plan"](day)

    @tool
    def check_task(day: str, start_hour: int, hours: int, workload: str = "") -> dict:
        """Check if a task of `hours` from `start_hour` (0-23) is heat-safe; returns safest alternatives."""
        used.append("check_task")
        return tools["check_task"](day, start_hour, hours, workload or None)

    @tool
    def first_aid(symptoms: list[str]) -> dict:
        """First aid for heat illness. symptoms from: confused, unconscious, seizure, hot_dry_skin, cannot_drink, dizzy, headache, vomiting, nausea, weak, heavy_sweating, fainted_recovered, cramps, rash."""
        used.append("first_aid")
        return tools["first_aid"](symptoms)

    model = BedrockModel(model_id=MODEL_ID, temperature=0.2, max_tokens=500)
    agent = Agent(
        model=model,
        system_prompt=SYSTEM + f"\nToday is {service.today()} (Asia/Kolkata). Reply language: {'Hindi' if lang == 'hi' else 'English'}.",
        tools=[day_plan, check_task, first_aid],
        callback_handler=None,
    )
    result = agent(question)
    text = re.sub(r"<thinking>.*?</thinking>", "", str(result), flags=re.S).strip()
    return text, used


def _rule_based(question: str, tools: dict, lang: str) -> str:
    q = question.lower()
    m = re.search(r"(\d{1,2})\s*(?:baje|बजे|pm|am|:00)?", q)
    p = tools["day_plan"]("tomorrow" if any(w in q for w in ("kal", "कल", "tomorrow")) else "today")
    if m:
        h = int(m.group(1))
        if ("pm" in q or "dopahar" in q or "दोपहर" in q or "शाम" in q) and h < 12:
            h += 12
        if h < 6:
            h += 12
        res = tools["check_task"]("tomorrow" if "kal" in q or "कल" in q or "tomorrow" in q else "today", h, 2)
        a, b = res["asked"], res["best"][0] if res["best"] else None
        if lang == "hi":
            verdict = "हाँ, कर सकते हैं" if a and a["ok"] else "नहीं, उस समय सुरक्षित नहीं"
            alt = f" बेहतर समय: {b['start']}–{b['end']} (WBGT {b['max_wbgt']}°C)।" if b else ""
            return f"{verdict}। {a['start']} पर WBGT {a['max_wbgt']}°C रहेगा।{alt}" if a else "उस समय का पूर्वानुमान नहीं मिला।"
        verdict = "Yes, that works" if a and a["ok"] else "No, that window is not heat-safe"
        alt = f" Best window: {b['start']}–{b['end']} (WBGT {b['max_wbgt']}°C)." if b else ""
        return f"{verdict}. WBGT at {a['start']} will be {a['max_wbgt']}°C.{alt}" if a else "No forecast for that time."
    stops = ", ".join(f"{s}–{e}" for s, e in p["stop_windows"]) or ("कोई नहीं" if lang == "hi" else "none")
    if lang == "hi":
        return f"आज काम {p['work_starts']} से शुरू। भारी काम बंद: {stops}। सबसे ज़्यादा गर्मी {p['peak_time']} पर (WBGT {p['peak_wbgt']}°C)।"
    return f"Work starts {p['work_starts']}. Heavy work stops: {stops}. Peak heat at {p['peak_time']} (WBGT {p['peak_wbgt']}°C)."


def ask(site: dict, question: str, lang: str | None = None) -> dict:
    lang = lang if lang in ("hi", "en") else _detect_lang(question)
    tools = make_tools(site, lang)
    engine = "strands"
    try:
        try:
            text, used = _strands(question, tools, lang)
        except ImportError:
            engine = "converse"
            text, used = _converse(question, tools, lang)
        return {"answer": text, "tools_used": used, "engine": engine, "model": MODEL_ID, "lang": lang}
    except Exception as exc:
        return {
            "answer": _rule_based(question, tools, lang),
            "tools_used": ["day_plan"],
            "engine": "rules",
            "model_unavailable": True,
            "error": type(exc).__name__,
            "lang": lang,
        }
