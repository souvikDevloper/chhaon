# Chhaon: submission writeup

**Track:** Heat and Water (heatwaves) · **Team:** Souvik Ghosh · **Built:** 8–11 October 2026
**Live:** https://d2cvj3mcid9pim.cloudfront.net · **Code:** https://github.com/souvikDevloper/chhaon · **Video:** _YouTube link_

## The problem

Heat kills people who work outdoors, and the person who decides when they stop is usually a site supervisor with a phone. India's Health Ministry counted 110 confirmed heatstroke deaths and over 40,000 suspected cases between March and mid-June 2024, and doctors say official counts miss many more. On 30 May 2024 ten suspected heatstroke deaths were reported at a single hospital in Rourkela, Odisha.

Two things make the supervisor's decision go wrong:

- **Temperature is the wrong number.** Heat illness tracks WBGT, which adds humidity, sun and wind to air temperature. When we replayed the real weather of 30 May 2024, the air in Aurangabad (Bihar) was hottest at 2 PM (44.7°C), but the most dangerous hour was 9 AM (WBGT 37.9°C). In Rourkela, heavy work was past the safe limit from early morning, hours before Odisha's 11 AM–3 PM ban began. In Howrah on the day we started building, the air at 9 AM was only 29°C while WBGT was 33.6°C: past the limit for heavy work.
- **Rest costs wages.** A rule that only says "stop" gets ignored by people paid by the day.

## What we built

Chhaon (छाँव, "shade") is a Hindi-first web app for site supervisors, running on AWS.

1. **A heat-safe shift plan, hour by hour.** WBGT for every hour from the site's forecast (Liljegren model, validated here against Open-Meteo's wet-bulb values to within 0.5°C), the safe share of each hour for the crew's workload (ACGIH screening limits), and a shift that keeps the normal 9-to-6 hours where they are safe and moves the unsafe minutes into the coolest hours. New workers get the stricter limits and NIOSH's acclimatisation ramp. One number: unsafe hours avoided.
2. **Breaks announced on time, in Hindi.** Each rest, stop and restart is an EventBridge Scheduler timer; when it fires, Amazon Polly speaks it and the phone plays it through a site speaker with the screen kept awake.
3. **A heat-illness protocol.** The supervisor taps symptoms; triage and first aid follow India's National Action Plan on Heat Related Illnesses (NCDC). A Step Functions workflow waits, asks for a re-check and escalates anything not clearly better: call 108, nearest hospitals (Amazon Location), email to the safety officer.
4. **Ask in Hindi or English.** A model on Amazon Bedrock (gpt-oss-120b, Mumbai region) answers ("Can we pour concrete at 2 tomorrow?") by calling the planner as a tool. The model explains; deterministic code makes every safety call.
5. **Replay a real day.** The planner run on the actual weather of 30 May 2024.

Built for where the user is: Hindi first, readable in direct sunlight, large touch targets, no sign-up, works on a cheap phone, keeps the last plan offline.

## Where AWS fits

- **AWS Lambda** (Python 3.12, arm64): WBGT physics, limits and the shift planner; the same tested code serves the API, the timers and the agent's tools.
- **Amazon EventBridge Scheduler**: one `at()` timer per announcement (Asia/Kolkata), deleted after firing, plus a 05:00 IST daily schedule that plans every registered site.
- **AWS Step Functions**: the heat-illness protocol with waits, task-token re-checks and escalation.
- **Amazon Polly** (Kajal, Hindi): announcements, cached in S3 so each sentence is synthesised once.
- **Amazon Bedrock**: the Hindi/English assistant with planner tools. OpenAI gpt-oss-120b through Bedrock's OpenAI-compatible endpoint in ap-south-1, signed with the function's IAM role (no API keys); Nova 2 Lite via **Strands Agents** / Converse as the second engine; a labelled rule-based answer if no model responds.
- **Amazon Location Service**: site search and nearest hospitals.
- **Amazon DynamoDB**: one table for sites, plans, feed and incidents, TTL on health data.
- **Amazon CloudFront + S3, API Gateway**: delivery from Indian edge locations; throttled HTTP API.
- **Amazon SNS + CloudWatch**: safety-officer alerts, alarms, and an impact dashboard counting unsafe hours avoided.
- **AWS SAM / CloudFormation**: the whole stack in one template, least-privilege IAM per function, region ap-south-1 (Mumbai).

Deliberately not used: SMS (needs TRAI DLT registration), SageMaker (nothing to train), always-on servers.

## Honest limits

Area forecasts are not site measurements; the ACGIH table is a screening tool; Chhaon is not a medical device. Replays use ERA5 reanalysis (about 25 km). Demo sites compress the 30-minute re-check to 20 seconds.

## AI tools used

Claude (Anthropic) as a coding agent for the code, tests, infrastructure and docs.
