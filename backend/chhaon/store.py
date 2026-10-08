"""DynamoDB single-table storage.

PK               SK                    what
SITE#<id>        META                  site settings
SITE#<id>        PLAN#<date>           the day's plan + schedule names
SITE#<id>        FEED#<iso>#<rand>     announcements and alerts (expire after 3 days)
INC#<id>         META                  a heat-illness incident and its timeline (expire after 30 days)
ACTIVE           SITE#<id>             sites that get a plan every morning
WX#<lat>#<lon>   HOUR#<yyyymmddhh>     weather cache (expires after 1 hour)
RL#<key>         MIN#<minute>          rate-limit counters (expire after 2 minutes)

Nested data is stored as JSON strings: no float/Decimal surprises.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")


# ---- sites ----

def put_site(site_id: str, site: dict, ttl_days: int = 30) -> None:
    table().put_item(
        Item={
            "PK": f"SITE#{site_id}",
            "SK": "META",
            "data": json.dumps(site),
            "updated": now_iso(),
            "ttl": int(time.time()) + ttl_days * 86400,
        }
    )
    table().put_item(Item={"PK": "ACTIVE", "SK": f"SITE#{site_id}", "ttl": int(time.time()) + ttl_days * 86400})


def get_site(site_id: str) -> dict | None:
    item = table().get_item(Key={"PK": f"SITE#{site_id}", "SK": "META"}).get("Item")
    return json.loads(item["data"]) if item else None


def active_site_ids() -> list[str]:
    ids: list[str] = []
    kwargs = {"KeyConditionExpression": Key("PK").eq("ACTIVE")}
    while True:
        res = table().query(**kwargs)
        ids += [i["SK"].split("#", 1)[1] for i in res.get("Items", [])]
        if "LastEvaluatedKey" not in res:
            return ids
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]


# ---- plans ----

def put_plan(site_id: str, date: str, plan: dict, schedules: list[str] | None = None) -> None:
    table().put_item(
        Item={
            "PK": f"SITE#{site_id}",
            "SK": f"PLAN#{date}",
            "data": json.dumps(plan),
            "schedules": json.dumps(schedules or []),
            "updated": now_iso(),
            "ttl": int(time.time()) + 7 * 86400,
        }
    )


def get_plan(site_id: str, date: str) -> tuple[dict | None, list[str]]:
    item = table().get_item(Key={"PK": f"SITE#{site_id}", "SK": f"PLAN#{date}"}).get("Item")
    if not item:
        return None, []
    return json.loads(item["data"]), json.loads(item.get("schedules", "[]"))


# ---- feed ----

def add_feed(site_id: str, entry: dict) -> dict:
    ts = now_iso()
    entry = {**entry, "ts": ts, "id": new_id()}
    table().put_item(
        Item={
            "PK": f"SITE#{site_id}",
            "SK": f"FEED#{ts}#{entry['id']}",
            "data": json.dumps(entry),
            "ttl": int(time.time()) + 3 * 86400,
        }
    )
    return entry


def feed(site_id: str, since: str | None = None, limit: int = 30) -> list[dict]:
    cond = Key("PK").eq(f"SITE#{site_id}")
    cond = cond & (Key("SK").gt(f"FEED#{since}~") if since else Key("SK").begins_with("FEED#"))
    res = table().query(KeyConditionExpression=cond, ScanIndexForward=False, Limit=limit)
    items = [json.loads(i["data"]) for i in res.get("Items", [])]
    return list(reversed(items))


# ---- incidents ----

def put_incident(inc_id: str, inc: dict) -> None:
    table().put_item(
        Item={
            "PK": f"INC#{inc_id}",
            "SK": "META",
            "data": json.dumps(inc),
            "v": 0,
            "updated": now_iso(),
            "ttl": int(time.time()) + 30 * 86400,
        }
    )


def get_incident(inc_id: str) -> dict | None:
    item = table().get_item(Key={"PK": f"INC#{inc_id}", "SK": "META"}).get("Item")
    return json.loads(item["data"]) if item else None


def update_incident(inc_id: str, fn) -> dict:
    """Read-modify-write with optimistic locking on `version`."""
    for _ in range(5):
        item = table().get_item(Key={"PK": f"INC#{inc_id}", "SK": "META"}, ConsistentRead=True).get("Item")
        if not item:
            raise KeyError(inc_id)
        inc = json.loads(item["data"])
        version = int(item.get("v", 0))
        inc = fn(inc) or inc
        try:
            table().put_item(
                Item={**item, "data": json.dumps(inc), "v": version + 1, "updated": now_iso()},
                ConditionExpression="#v = :v",
                ExpressionAttributeNames={"#v": "v"},
                ExpressionAttributeValues={":v": version},
            )
            return inc
        except table().meta.client.exceptions.ConditionalCheckFailedException:
            continue
    raise RuntimeError("incident update conflict")


# ---- weather cache ----

def cached_weather(lat: float, lon: float, fetch) -> dict:
    key = {"PK": f"WX#{lat:.2f}#{lon:.2f}", "SK": "HOUR#" + datetime.now(timezone.utc).strftime("%Y%m%d%H")}
    item = table().get_item(Key=key).get("Item")
    if item:
        return json.loads(item["data"])
    data = fetch()
    table().put_item(Item={**key, "data": json.dumps(data), "ttl": int(time.time()) + 3600})
    return data


# ---- rate limiting ----

def allow(key: str, per_minute: int) -> bool:
    minute = int(time.time() // 60)
    res = table().update_item(
        Key={"PK": f"RL#{key}", "SK": f"MIN#{minute}"},
        UpdateExpression="ADD n :one SET #t = :ttl",
        ExpressionAttributeNames={"#t": "ttl"},
        ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + 120},
        ReturnValues="UPDATED_NEW",
    )
    return int(res["Attributes"]["n"]) <= per_minute
