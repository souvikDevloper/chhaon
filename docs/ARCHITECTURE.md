# Architecture

![Chhaon on AWS](architecture.svg)

Chhaon is serverless and event-driven. Nothing runs between breaks: a plan is computed on request, each announcement is a one-time timer, and a heat-illness case is a workflow that waits without holding a server. Region: **ap-south-1 (Mumbai)**, close to the users and the data.

## One rule

**The model explains; code decides.** WBGT, work/rest limits, the shift plan, triage and escalation are deterministic Python with unit tests (including checks against real weather). The Bedrock agent can only read their output through tools. Safety-critical announcements are fixed templates, never generated text, so the same instruction always sounds the same.

## Flows

### 1. Plan a day
`GET /api/sites/{id}/plan?day=today`
1. API Lambda loads the site from DynamoDB.
2. Fetches the Open-Meteo hourly forecast (cached in DynamoDB for an hour per location).
3. For each hour slot: averages the instantaneous variables at both ends, takes radiation from the next record (it is a preceding-hour mean), places the sun at the slot's midpoint, and computes outdoor WBGT with the Liljegren model (10 m wind reduced to 2 m with a stability class, urban exponents).
4. Looks up the safe share of the hour for the workload and acclimatisation (ACGIH screening table; Action Limit for new workers; NIOSH exposure ramp).
5. Keeps the normal 9-to-6 hours where they are safe, then moves the unsafe minutes into the coolest hours of the allowed window (06:00–19:00, or 05:00–22:00 with night work), never above the safe share.
6. Builds the announcement list: work start, each rest, the long pause and its end, day end.

### 2. Announce on time
`POST /api/sites/{id}/publish` and the 05:00 IST daily schedule
- For each future announcement, the API creates an **EventBridge Scheduler** one-time schedule: `at(2026-10-09T10:45:00)` in `Asia/Kolkata`, flexible window off, retry twice, `ActionAfterCompletion: DELETE`. Re-publishing deletes and recreates that day's schedules, so there are never duplicates.
- When a schedule fires, the **announce Lambda** renders the fixed Hindi template, asks **Polly** (Kajal, neural, `hi-IN`) for the audio unless the same sentence is already in S3, and appends the announcement to the site feed in DynamoDB.
- The supervisor's phone polls the feed every 10 seconds and plays new audio through the site speaker. A service worker caches the audio and the app shell; a Wake Lock keeps the screen on.
- `POST /test-announcement` creates a real schedule 60 seconds out, so anyone can watch the whole path work.

### 3. Someone is unwell
`POST /api/sites/{id}/incidents` starts a **Step Functions** Standard workflow:

```
Begin → Triage ─red──────────────────────────────→ Emergency → AwaitHandover (task token) → HandedOver
              ├─amber/yellow→ FirstAid → Wait 30 min → Recheck (task token) → Decide ─better→ Recovered
              │                                                              ├─worse/same→ Emergency
              │                                                              └─(yellow, same)→ FirstAid
              └─green→ Advice                       timeouts on Recheck / AwaitHandover → Escalate
```

- Every step writes to the incident timeline in DynamoDB, which the phone shows live.
- A re-check is a `waitForTaskToken` task: the token is stored server-side and never sent to the browser; the supervisor's answer calls `SendTaskSuccess`.
- Emergency finds the nearest hospitals with **Amazon Location** (Places `SearchNearby`, category hospital) and emails the safety officer through **SNS**.
- Escalation is conservative: anything other than "better" goes up a level, and silence escalates.
- Demo sites wait 20 seconds instead of 30 minutes.

### 4. Ask
`POST /api/ask` runs a separate Lambda with **Bedrock** (Nova 2 Lite via the global inference profile). Tools: `day_plan`, `check_task`, `first_aid`. The Strands Agents SDK drives the loop when its layer is attached; otherwise the same tools run through the Converse API. If Bedrock is unavailable, a rule-based answer is returned and labelled as such. Answers can be spoken with Polly.

## Data model (one DynamoDB table)

| PK | SK | What | Expires |
|---|---|---|---|
| `SITE#<id>` | `META` | site settings | 30 days (demo: 7) |
| `SITE#<id>` | `PLAN#<date>` | plan + schedule names | 7 days |
| `SITE#<id>` | `FEED#<iso>#<id>` | announcements, alerts | 3 days |
| `INC#<id>` | `META` | incident, timeline, pending question | 30 days |
| `ACTIVE` | `SITE#<id>` | sites the morning job plans | with the site |
| `WX#<lat>#<lon>` | `HOUR#<yyyymmddhh>` | forecast cache | 1 hour |
| `RL#<key>` | `MIN#<minute>` | per-IP rate limit counters | 2 minutes |

Incidents use optimistic locking (`v` attribute) because the workflow and the supervisor can write at the same time.

## Security and reliability

- Least-privilege IAM per function: e.g. only the API and morning functions can create schedules, only in their group; only the Scheduler role can invoke the announce function.
- HTTP API throttling plus per-IP limits in DynamoDB for the routes that cost money (Bedrock, Polly) or create resources.
- S3 is private behind CloudFront Origin Access Control; security headers via the managed policy.
- No accounts or personal data beyond a worker's first name in an incident, which expires after 30 days.
- Alarms: API errors and any failed protocol run notify the alert topic. X-Ray tracing on all functions and the state machine. Log retention 14 days.
- A $15 monthly budget alert.

## Cost shape

Everything is pay-per-use and idle costs nothing. Per site per day: one forecast call (cached), roughly 10–20 Scheduler invocations, the same number of short Lambda runs, and Polly only for sentences not yet in the S3 cache (a site's daily announcements repeat, so audio is almost always cached after the first day). Bedrock is used only when someone asks a question.

## Run without AWS

`python dev/server.py` runs the real handlers with in-memory fakes for DynamoDB, S3, Polly, Scheduler, Step Functions (a small interpreter of the same protocol), Location and SNS, and serves the app at http://localhost:8787.
