"""Non-HTTP entry points: scheduler targets and the morning planner."""
from __future__ import annotations

import traceback

from chhaon import metrics, service, store


def announce(event, context):
    """Invoked by an EventBridge Scheduler one-time schedule at the planned minute."""
    entry = service.announce_event(event["site_id"], event["event"], event.get("date"))
    return {"ok": True, "id": entry["id"]}


def morning(event, context):
    """Invoked every day at 05:00 IST: plan and schedule today's announcements for every real site."""
    date = service.today()
    done, failed, avoided = 0, 0, 0
    for site_id in store.active_site_ids():
        site = store.get_site(site_id)
        if not site or not site.get("auto_publish"):
            continue
        try:
            res = service.publish(site_id, site, date)
            avoided += res["unsafe_hours_avoided"]
            done += 1
        except Exception:
            failed += 1
            traceback.print_exc()
    metrics.emit({"SitesPlanned": done, "SitePlanFailures": failed})
    return {"date": date, "planned": done, "failed": failed, "unsafe_hours_avoided": avoided}
