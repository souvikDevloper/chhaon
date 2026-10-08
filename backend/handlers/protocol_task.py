"""Step Functions task for the heat-illness protocol.

The state machine owns the timing (waits, timeouts, escalation); this Lambda
does one small step per call and writes it to the incident timeline that the
supervisor's phone is watching.
"""
from __future__ import annotations

import json
import os

import boto3

from chhaon import places, protocol, store

_sns = None


def _publish(subject: str, message: str) -> bool:
    global _sns
    topic = os.environ.get("ALERT_TOPIC_ARN")
    if not topic:
        return False
    _sns = _sns or boto3.client("sns")
    _sns.publish(TopicArn=topic, Subject=subject[:99], Message=message)
    return True


def _log(state: dict, kind: str, text: str, **changes) -> dict:
    def apply(i):
        i.update(changes)
        i["timeline"].append({"t": store.now_iso(), "kind": kind, "text": text})
        return i

    return store.update_incident(state["incident_id"], apply)


def handler(event, context):
    action = event["action"]
    state = event.get("state") or event
    lang = state.get("lang", "hi")
    inc_id = state["incident_id"]

    if action == "begin":
        _log(state, "protocol", "Protocol started" if lang == "en" else "प्रोटोकॉल शुरू", status="open")
        return state

    if action == "emergency":
        site = store.get_site(state["site_id"]) or {}
        hospitals = places.nearest_hospitals(float(site.get("lat", 0)), float(site.get("lon", 0))) if site else []
        inc = _log(
            state,
            "emergency",
            "Call 108. Cool the person now. Nearest hospitals found." if lang == "en" else "108 पर कॉल कीजिए। अभी ठंडा कीजिए। नज़दीकी अस्पताल नीचे हैं।",
            level="red",
            status="emergency",
            guidance=protocol.guidance("red", lang),
            hospitals=hospitals,
        )
        sent = _publish(
            f"Chhaon EMERGENCY: possible heatstroke at {site.get('name', 'site')}",
            f"Worker: {inc['worker']}\nSymptoms: {', '.join(inc['symptoms'])}\nSite: {site.get('name')} ({site.get('lat')}, {site.get('lon')})\n"
            f"Nearest hospital: {hospitals[0]['name'] + ', ' + str(hospitals[0]['address']) if hospitals else 'not found'}\n"
            "The supervisor has been told to call 108 and start cooling.",
        )
        store.add_feed(state["site_id"], {"type": "alert", "incident_id": inc_id, "level": "red", "notified": sent})
        return {**state, "level": "red"}

    if action == "care":
        level = state["level"]
        _log(
            state,
            "care",
            (f"First aid started. Re-check in {protocol.RECHECK_MINUTES.get(level, 30)} minutes." if lang == "en" else f"प्राथमिक उपचार शुरू। {protocol.RECHECK_MINUTES.get(level, 30)} मिनट बाद दोबारा देखिए।"),
            level=level,
            status="caring",
            guidance=protocol.guidance(level, lang),
        )
        return state

    if action == "ask":
        question = event["question"]
        options = ["better", "same", "worse"] if question == "recheck" else ["handed_over"]
        _log(
            state,
            "question",
            {"recheck": "How is the worker now?", "handover": "Tell me when the ambulance arrives or you reach hospital."}[question]
            if lang == "en"
            else {"recheck": "अब साथी की हालत कैसी है?", "handover": "एम्बुलेंस आए या अस्पताल पहुँचें तो बताइए।"}[question],
            pending={"question": question, "options": options, "token": event["token"], "asked_at": store.now_iso()},
        )
        return {"asked": question}

    if action == "decide":
        answer = (state.get("recheck") or {}).get("answer", "worse")
        nxt = protocol.after_recheck(state["level"], answer)
        if nxt == "resolved":
            _log(state, "resolved", "Better. No more work in the heat today." if lang == "en" else "हालत बेहतर। आज धूप में दोबारा काम नहीं।", status="resolved")
        return {**state, "level": nxt, "recheck": None}

    if action == "close":
        _log(state, "closed", "Handed over to medical care." if lang == "en" else "मेडिकल टीम को सौंप दिया गया।", status="handed_over", pending=None)
        return state

    if action == "escalate":
        site = store.get_site(state["site_id"]) or {}
        sent = _publish(
            f"Chhaon: no response on a heat-illness case at {site.get('name', 'site')}",
            f"Incident {inc_id}: the supervisor has not confirmed the worker's condition. Please call the site now.",
        )
        _log(
            state,
            "escalated",
            ("No reply. Safety officer alerted." if sent else "No reply. Please check on the worker now.") if lang == "en" else ("जवाब नहीं मिला। सेफ़्टी ऑफ़िसर को सूचना भेजी।" if sent else "जवाब नहीं मिला। तुरंत साथी को देखिए।"),
            status="escalated",
            pending=None,
        )
        return state

    raise ValueError(f"unknown action {action}")
