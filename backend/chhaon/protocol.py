"""Heat-illness triage for a site supervisor.

Rules and first-aid steps follow India's National Action Plan on Heat Related
Illnesses (NCDC, Ministry of Health and Family Welfare): heatstroke is core
temperature above 40 C with brain involvement (confusion, seizures, collapse)
and is an emergency (call 108, cool aggressively, nothing by mouth if not fully
alert); heat exhaustion has no brain involvement and gets shade, salt-containing
fluids and a re-check, with referral if not better in 30 minutes.

This is a deterministic checklist, not a diagnosis. It always errs towards
escalation.
"""
from __future__ import annotations

RED_FLAGS = ("confused", "unconscious", "seizure", "hot_dry_skin", "cannot_drink")
AMBER = ("dizzy", "headache", "vomiting", "nausea", "weak", "heavy_sweating", "fainted_recovered")
YELLOW = ("cramps",)
GREEN = ("rash",)
ALL_SYMPTOMS = RED_FLAGS + AMBER + YELLOW + GREEN

RECHECK_MINUTES = {"amber": 30, "yellow": 30}

STEPS = {
    "red": {
        "en": [
            "Call 108 now. Say: possible heatstroke at a construction site, and give the site's location (shown below).",
            "Move them to the coolest shade. Lay them down; if vomiting, turn them on their side.",
            "Remove extra clothing. Pour or spray cool water over the whole body and fan hard. If there is a tarpaulin and a water drum: lay them on the tarp, lift its edges and pour water in so the body sits in cool water (keep the head out).",
            "Put wet cloths or ice packs on the neck, armpits and groin.",
            "Give nothing to drink if they are not fully awake. No paracetamol.",
            "Keep cooling without stopping until the ambulance arrives or you reach the hospital. Never leave them alone.",
        ],
        "hi": [
            "अभी 108 पर कॉल कीजिए। बोलिए: साइट पर लू लगने (हीटस्ट्रोक) का केस है, और साइट की लोकेशन बताइए (नीचे लिखी है)।",
            "सबसे ठंडी छाँव में ले जाइए, लिटाइए। उल्टी हो तो करवट पर लिटाइए।",
            "फालतू कपड़े हटाइए। पूरे शरीर पर ठंडा पानी डालिए और ज़ोर से हवा कीजिए। तिरपाल और पानी का ड्रम हो तो: तिरपाल पर लिटाइए, किनारे उठाइए और पानी भरिए ताकि शरीर ठंडे पानी में रहे (सिर बाहर)।",
            "गर्दन, बगल और जांघ के जोड़ पर गीला कपड़ा या बर्फ़ रखिए।",
            "पूरा होश न हो तो कुछ भी पीने को मत दीजिए। पैरासिटामॉल मत दीजिए।",
            "एम्बुलेंस आने या अस्पताल पहुँचने तक ठंडा करना बंद मत कीजिए। उन्हें अकेला मत छोड़िए।",
        ],
    },
    "amber": {
        "en": [
            "Stop work for this person now.",
            "Ask their name, where they are and what day it is. Muddled answers or drowsiness mean heatstroke: call 108.",
            "Shade, lie down, raise the feet a little, loosen clothes.",
            "Small sips of ORS, salted lemon water or coconut water.",
            "Wet cloth on the body and fan.",
            "Re-check in 30 minutes. Not better, worse, or still vomiting: take to hospital.",
            "No more work in the heat for them today.",
        ],
        "hi": [
            "इस साथी का काम अभी रोकिए।",
            "नाम, जगह और आज का दिन पूछिए। जवाब उलझा हुआ हो या नींद-सी आ रही हो तो यह लू (हीटस्ट्रोक) है: 108 पर कॉल कीजिए।",
            "छाँव में लिटाइए, पैर थोड़े ऊपर रखिए, कपड़े ढीले कीजिए।",
            "ORS, नमक-नींबू पानी या नारियल पानी घूँट-घूँट पिलाइए।",
            "शरीर पर गीला कपड़ा रखिए और हवा कीजिए।",
            "30 मिनट बाद फिर देखिए। ठीक न हो, हालत बिगड़े या उल्टी न रुके तो अस्पताल ले जाइए।",
            "आज इन्हें धूप में दोबारा काम मत करवाइए।",
        ],
    },
    "yellow": {
        "en": [
            "Stop and rest in the shade.",
            "Give ORS or salted lemon water, not plain water alone.",
            "Gently stretch the cramped muscle.",
            "No heavy work until it is cooler. Cramps for more than an hour: see a doctor.",
        ],
        "hi": [
            "काम रोकिए, छाँव में आराम कराइए।",
            "ORS या नमक-नींबू पानी दीजिए, सिर्फ़ सादा पानी नहीं।",
            "ऐंठी हुई मांसपेशी को धीरे से खींचिए।",
            "ठंडक होने तक भारी काम नहीं। एक घंटे से ज़्यादा ऐंठन रहे तो डॉक्टर को दिखाइए।",
        ],
    },
    "green": {
        "en": [
            "Keep the skin cool and dry; loose cotton clothes.",
            "Rest in shade during breaks; avoid thick creams on the rash.",
        ],
        "hi": [
            "त्वचा को ठंडा और सूखा रखिए; ढीले सूती कपड़े पहनाइए।",
            "ब्रेक में छाँव में रहिए; घमौरी पर गाढ़ी क्रीम मत लगाइए।",
        ],
    },
}

TITLES = {
    "red": {"en": "Emergency: possible heatstroke", "hi": "इमरजेंसी: लू लगने (हीटस्ट्रोक) का ख़तरा"},
    "amber": {"en": "Heat exhaustion: stop and cool down", "hi": "गर्मी से थकावट: काम रोकिए, ठंडा कीजिए"},
    "yellow": {"en": "Heat cramps: rest and salt", "hi": "गर्मी की ऐंठन: आराम और नमक"},
    "green": {"en": "Heat rash: keep cool", "hi": "घमौरी: ठंडक रखिए"},
}


def classify(symptoms: list[str]) -> str:
    s = {x for x in symptoms if x in ALL_SYMPTOMS}
    if not s:
        raise ValueError("no recognised symptoms")
    if s & set(RED_FLAGS):
        return "red"
    if s & set(AMBER):
        return "amber"
    if s & set(YELLOW):
        return "yellow"
    return "green"


def guidance(level: str, lang: str = "en") -> dict:
    lang = "hi" if lang == "hi" else "en"
    return {
        "level": level,
        "title": TITLES[level][lang],
        "steps": STEPS[level][lang],
        "call_108": level == "red",
        "recheck_minutes": RECHECK_MINUTES.get(level),
        "source": "National Action Plan on Heat Related Illnesses, NCDC / MoHFW",
    }


def after_recheck(level: str, answer: str) -> str:
    """Next level after a re-check. Anything not clearly better escalates."""
    if answer == "better":
        return "resolved"
    if level == "yellow" and answer == "same":
        return "amber"
    return "red"
