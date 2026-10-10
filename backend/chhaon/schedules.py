"""EventBridge Scheduler: one one-time schedule per announcement.

No always-on server checking the clock: each break is a real timer that invokes the
announce Lambda at the planned minute (Asia/Kolkata) and deletes itself after it
fires. Re-publishing a plan replaces that day's schedules. (The phone reads the
resulting feed every 10 s while announcements are on.)
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

IST = timezone(timedelta(hours=5, minutes=30))
_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("scheduler")
    return _client


def _name(site_id: str, date: str, at: str, kind: str) -> str:
    raw = f"{site_id}-{date.replace('-', '')}-{at.replace(':', '')}-{kind}"
    return re.sub(r"[^0-9A-Za-z_.-]", "-", raw)[:64]


def _create(name: str, when: datetime, payload: dict) -> None:
    client().create_schedule(
        Name=name,
        GroupName=os.environ["SCHEDULE_GROUP"],
        ScheduleExpression=f"at({when.strftime('%Y-%m-%dT%H:%M:%S')})",
        ScheduleExpressionTimezone="Asia/Kolkata",
        FlexibleTimeWindow={"Mode": "OFF"},
        ActionAfterCompletion="DELETE",
        Target={
            "Arn": os.environ["ANNOUNCE_FN_ARN"],
            "RoleArn": os.environ["SCHEDULER_ROLE_ARN"],
            "Input": json.dumps(payload),
            "RetryPolicy": {"MaximumRetryAttempts": 2, "MaximumEventAgeInSeconds": 300},
        },
        Description="Chhaon heat-break announcement",
    )


def delete(names: list[str]) -> None:
    for n in names:
        try:
            client().delete_schedule(Name=n, GroupName=os.environ["SCHEDULE_GROUP"])
        except ClientError:
            pass  # already fired and deleted itself


def publish_day(site_id: str, date: str, events: list[dict], replace: list[str] | None = None) -> list[str]:
    """Create schedules for every future event of `date`. Returns the schedule names."""
    delete(replace or [])
    now = datetime.now(IST)
    names: list[str] = []
    for ev in events:
        when = datetime.fromisoformat(f"{date}T{ev['at']}:00").replace(tzinfo=IST)
        if when <= now + timedelta(seconds=30):
            continue
        name = _name(site_id, date, ev["at"], ev["kind"])
        try:
            _create(name, when.replace(tzinfo=None), {"site_id": site_id, "date": date, "event": ev})
        except client().exceptions.ConflictException:
            delete([name])
            _create(name, when.replace(tzinfo=None), {"site_id": site_id, "date": date, "event": ev})
        names.append(name)
    return names


def test_in(site_id: str, seconds: int = 60) -> dict:
    # Scheduler fires one-time schedules at minute resolution, so aim at the start of a minute
    # (at least ~45 s away): the test then arrives when the screen says it will.
    when = (datetime.now(IST) + timedelta(seconds=max(45, seconds - 15) + 59)).replace(second=0, microsecond=0)
    ev = {"at": when.strftime("%H:%M:%S"), "kind": "test", "minutes": 0}
    name = _name(site_id, when.strftime("%Y-%m-%d"), when.strftime("%H%M%S"), "test")
    _create(name, when.replace(tzinfo=None, microsecond=0), {"site_id": site_id, "date": when.strftime("%Y-%m-%d"), "event": ev})
    return {"schedule": name, "fires_at": when.isoformat(timespec="seconds")}
