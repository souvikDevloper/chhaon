# Chhaon (छाँव)

**Heat-safe shifts for India's outdoor workers.** Chhaon turns a site's weather forecast into an hour-by-hour work plan for a construction crew, announces every break in Hindi at the right minute, and walks a supervisor through first aid when a worker gets sick from the heat.

Environmental Hacks, Bharat Builds Tour 2026 · **Track: Heat and Water** (heatwaves)

- **Live app:** _added after deploy_
- **Demo video:** _added after recording_
- **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

![Chhaon on AWS](docs/architecture.svg)

---

## The problem

India's Health Ministry counted **110 confirmed heatstroke deaths and over 40,000 suspected cases** between 1 March and 18 June 2024 ([AP](https://past.jamaica-gleaner.com/article/world-news/20240620/extreme-heat-india-killed-more-100-people-past-three-and-half-months)), and doctors say the official count misses many more ([Guardian, via The Cool Down](https://www.thecooldown.com/?p=751295)). People who work outdoors take the worst of it. On 30 May 2024 alone, ten deaths from suspected heatstroke were reported at the government hospital in Rourkela, Odisha, and the state barred its own employees from outdoor work between 11 AM and 3 PM ([Reuters via Business Standard](https://www.business-standard.com/india-news/15-succumb-to-suspected-heatstroke-in-bihar-odisha-over-24-hours-124053100673_1.html)).

On a construction site the decision of when to stop is made by a site supervisor (munshi) with a phone, usually from the thermometer reading or not at all. Two things go wrong:

1. **Temperature is the wrong number.** Heat illness depends on WBGT (wet bulb globe temperature), which adds humidity, sun and wind. A humid 32°C afternoon in the sun can be more dangerous than a dry 40°C one. Most "heat alert" apps never compute it.
2. **Rest costs wages.** Workers don't stop because a lost hour is lost pay. A rule that just says "stop" gets ignored.

## What Chhaon does

| For the supervisor | How |
|---|---|
| **Today's plan, hour by hour** | WBGT for every hour from the site's forecast (Liljegren model), the safe share of each hour for the crew's workload (ACGIH screening limits), and a shift that keeps the normal 9-to-6 hours where they are safe and moves the unsafe minutes into the coolest hours. One number on screen: *unsafe hours avoided*. |
| **New workers protected** | Workers in their first week get the stricter limits and NIOSH's acclimatisation ramp (20% of a normal day on day 1, +20% per day). |
| **Breaks announced on time, in Hindi** | Every rest, stop and restart becomes an EventBridge Scheduler timer. When it fires, Amazon Polly (Kajal) speaks it in Hindi; the phone plays it through a site speaker and keeps its screen awake. |
| **Someone feels unwell** | Tap the symptoms. Triage and first-aid steps follow India's [National Action Plan on Heat Related Illnesses](https://ncdc.mohfw.gov.in/wp-content/uploads/2024/05/1.Nation-Action-plan-on-Heat-Related-llnesses.pdf). A Step Functions workflow waits 30 minutes, asks for a re-check, and escalates anything not clearly better: call 108, nearest hospitals from Amazon Location, email to the safety officer. |
| **Ask in Hindi or English** | "कल दोपहर 2 बजे ढलाई कर सकते हैं?" An Amazon Bedrock agent answers using the planner as a tool. The model explains; it never makes the safety call. |
| **Replay a real day** | Run the planner on the actual weather of 30 May 2024 in Rourkela and Aurangabad and see what it would have said. |

It is built for the person using it: Hindi first, readable in direct sunlight (white background, large type, hatching as well as colour), big touch targets, no sign-up, works on a cheap Android phone and keeps the last plan when the network drops.

## Where AWS fits

Each service does a job you can see in the demo. Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Service | Its job in Chhaon |
|---|---|
| **AWS Lambda** (Python 3.12, arm64) | The planner: WBGT physics, limits and shift optimiser. Deterministic and unit-tested; the same code serves the API, the timers and the agent's tools. |
| **Amazon EventBridge Scheduler** | One one-time `at()` schedule per announcement, in Asia/Kolkata time, deleted after it fires. Plus a 05:00 IST daily schedule that plans every registered site. No polling, nothing running between breaks. |
| **AWS Step Functions** | The heat-illness protocol: first aid, a 30-minute wait, a re-check via task token, escalation on "same", "worse" or silence. |
| **Amazon Polly** | Hindi announcements (Kajal, neural). Each sentence is synthesised once and cached in S3. |
| **Amazon Bedrock** (Nova 2 Lite) + **Strands Agents** | The Hindi/English assistant. Tools: today's plan, check a task window, first aid. Falls back to a rule-based answer if the model is unavailable, and says so. |
| **Amazon Location Service** | Find the site by name; nearest hospitals for an emergency. |
| **Amazon DynamoDB** | Sites, plans, the announcement feed and incidents in one table, with TTL on health data. |
| **Amazon CloudFront + S3** | The app and the cached audio, served from India edge locations; `/api/*` routed to the HTTP API. |
| **Amazon API Gateway** (HTTP API) | Throttled public API; per-IP rate limits for the costly routes. |
| **Amazon SNS + CloudWatch** | Safety-officer emails, alarms on errors and failed protocol runs, and a dashboard with *unsafe hours avoided* as a custom metric. |
| **AWS SAM / CloudFormation** | The whole stack in one template. Least-privilege IAM per function. |

**Deliberately not used:** SMS (Indian SMS needs TRAI DLT sender and template registration, which takes longer than a hackathon); SageMaker (there is no model to train: physics and published limits do the job); always-on servers (every component is pay-per-use).

## Method

- **WBGT.** Outdoor WBGT = 0.7 natural wet bulb + 0.2 globe + 0.1 air temperature, computed with a port of Liljegren et al. (2008), *Modeling the Wet Bulb Globe Temperature Using Standard Meteorological Measurements*, J. Occup. Environ. Hyg. 5(10). Inputs from the [Open-Meteo](https://open-meteo.com/) forecast: temperature, humidity, 10 m wind (reduced to 2 m), shortwave and direct radiation, pressure, and the sun's position for each hour.
- **Limits.** ACGIH heat-stress screening criteria, as published by [CCOHS](https://www.ccohs.ca/oshanswers/phys_agents/heat/heat_control.html): the WBGT at which 75–100%, 50–75%, 25–50% or 0–25% of each hour may be worked, by workload, for acclimatised workers (TLV) and new workers (Action Limit). Above the 0–25% limit, that workload stops.
- **Acclimatisation.** [NIOSH](https://www.cdc.gov/niosh/heat-stress/recommendations/acclimatization.html): new workers 20% on day 1 and +20% a day.
- **First aid.** India's [National Action Plan on Heat Related Illnesses](https://ncdc.mohfw.gov.in/wp-content/uploads/2024/05/1.Nation-Action-plan-on-Heat-Related-llnesses.pdf) (NCDC, MoHFW).

## Run it

**Without AWS** (real handlers, in-memory fakes, synthetic or saved weather):

```bash
python dev/server.py          # http://localhost:8787
cd backend && python -m unittest discover -s . -p "test_*.py"
```

**On AWS** (AWS CLI v2, no SAM CLI needed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\jobs\deploy.ps1 -Region ap-south-1 -AlertEmail you@example.com
```

`deploy.ps1` packages `infra/template.yaml`, deploys the stack, and publishes `web/` to S3 behind CloudFront. `strands-layer.ps1` builds the optional Strands Agents layer.

## Limits, honestly

- The forecast is for the area (a few km), not one spot; a WBGT meter on site is better. The ACGIH table is a screening tool, not a prescription. Chhaon is not a medical device; in an emergency, call 108.
- Replays use ERA5 reanalysis (about a 25 km grid), not station measurements.
- Demo sites compress the 30-minute re-check to 20 seconds so it can be seen in a demo.
- Voice is Hindi and Indian English: those are the Indian languages Amazon Polly speaks today.

## Built with

Python, plain JavaScript (no framework, no build step), AWS. AI tools used: **Claude (Anthropic)** as a coding agent.

MIT licence. Built by Souvik Ghosh during Environmental Hacks, 8–11 October 2026.
