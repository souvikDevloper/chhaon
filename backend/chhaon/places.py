"""Amazon Location Service (Places API v2): find a site by name and the nearest hospitals."""
from __future__ import annotations

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("geo-places")
    return _client


def _item(r: dict) -> dict:
    lon, lat = r.get("Position", [None, None])
    phones = [p.get("Value") for p in (r.get("Contacts") or {}).get("Phones", []) if p.get("Value")]
    return {
        "name": r.get("Title"),
        "address": (r.get("Address") or {}).get("Label"),
        "lat": lat,
        "lon": lon,
        "distance_m": r.get("Distance"),
        "phone": phones[0] if phones else None,
    }


def geocode(query: str) -> list[dict]:
    try:
        res = client().geocode(QueryText=query[:200], Filter={"IncludeCountries": ["IND"]}, MaxResults=5)
        items = res.get("ResultItems", [])
        if not items:
            res = client().search_text(QueryText=query[:200], Filter={"IncludeCountries": ["IND"]}, MaxResults=5, BiasPosition=[78.96, 22.59])
            items = res.get("ResultItems", [])
        return [_item(r) for r in items]
    except (ClientError, BotoCoreError):
        return []


def nearest_hospitals(lat: float, lon: float, n: int = 3) -> list[dict]:
    try:
        res = client().search_nearby(
            QueryPosition=[lon, lat],
            QueryRadius=15000,
            Filter={"IncludeCategories": ["hospital"]},
            MaxResults=n,
            AdditionalFeatures=["Contact"],
        )
        items = res.get("ResultItems", [])
    except (ClientError, BotoCoreError):
        items = []
    if not items:
        try:
            res = client().search_text(QueryText="hospital", BiasPosition=[lon, lat], MaxResults=n, AdditionalFeatures=["Contact"])
            items = res.get("ResultItems", [])
        except (ClientError, BotoCoreError):
            return []
    out = [_item(r) for r in items][:n]
    out.sort(key=lambda x: x["distance_m"] if x["distance_m"] is not None else 1e9)
    return out
