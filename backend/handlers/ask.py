"""POST /api/ask: the supervisor's question, answered by the Bedrock agent."""
from __future__ import annotations

import traceback

from chhaon import agent, metrics, store
from chhaon.http import HttpError, body, respond, source_ip, valid_id


def speakable_key(text: str, lang: str) -> str:
    import hashlib

    return "speak#" + hashlib.sha256(f"{lang}|{text.strip()}".encode()).hexdigest()[:32]


def handler(event, context):
    try:
        data = body(event)
        if not store.allow(f"ask#{source_ip(event)}", 8):
            raise HttpError(429, "too many questions, try again in a minute")
        site = store.get_site(valid_id(str(data.get("site_id", ""))))
        if not site:
            raise HttpError(404, "site not found")
        question = str(data.get("question") or "").strip()
        if not 2 <= len(question) <= 400:
            raise HttpError(400, "ask a question of up to 400 characters")
        result = agent.ask(site, question, data.get("lang"))
        # only text Chhaon itself produced may be turned into speech later (POST /speak)
        lang = result.get("lang", "hi")
        store.set_marker(speakable_key(result.get("answer", ""), lang), "1", ttl_days=1)
        if result.get("protocol"):
            p = result["protocol"]
            store.set_marker(speakable_key(" ".join([p["title"], *p["steps"]]), lang), "1", ttl_days=1)
        metrics.emit({"AgentAnswers": 1}, {"Engine": result.get("engine", "unknown")})
        return respond(200, result)
    except HttpError as e:
        return respond(e.status, {"error": e.message})
    except Exception:
        traceback.print_exc()
        return respond(500, {"error": "internal error"})
