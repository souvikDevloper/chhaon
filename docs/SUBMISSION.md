# Chhaon: submission writeup

**Track:** Heat and Water (heatwaves) · **Team:** Souvik Ghosh · **Built:** 8–11 October 2026
**Live:** https://d2cvj3mcid9pim.cloudfront.net · **Code:** https://github.com/souvikDevloper/chhaon · **Video:** _YouTube link_

## The problem

Heat kills people who work outdoors, and the person who decides when they stop is usually a site supervisor with a phone. India's Health Ministry counted 110 confirmed heatstroke deaths and over 40,000 suspected cases between March and mid-June 2024, and the ILO projects heat stress will cost India 5.8% of its working hours in 2030, hitting construction hardest. On 30 May 2024 ten suspected heatstroke deaths were reported at a single hospital in Rourkela, Odisha.

Two things make the supervisor's decision go wrong:

- **Temperature is the wrong number.** Heat illness tracks WBGT, which adds humidity, sun and wind to air temperature. When we replayed the real weather of 30 May 2024, the air in Aurangabad (Bihar) was hottest at 2 PM (44.7°C), but by WBGT the most dangerous hour was 9 AM (modelled WBGT 37.9°C). In Rourkela, heavy work was past the safe limit from 6 AM, hours before Odisha's 11 AM–3 PM ban began. In Howrah on the day we started building, the air at 9 AM was only 29°C while WBGT was 33.6°C: past the limit for heavy work.
- **Rest costs wages.** A rule that only says "stop" gets ignored by people paid by the day.

## What we built

Chhaon (छाँव, "shade") is a Hindi-first web app for site supervisors and their crews, running on AWS.

1. **A heat-safe shift plan, hour by hour.** Modelled WBGT for every hour from the site's forecast (Liljegren model), the safe share of each hour for the crew's workload (ACGIH screening limits), and a shift that keeps the normal 9-to-6 hours where they are safe and moves the unsafe minutes into the coolest hours. It shows how many normal-shift hours the heat made unsafe (none are left in the plan), how much paid work is kept, the worker-hours kept out of unsafe heat, and water for the crew. New workers get the stricter limits and NIOSH's acclimatisation ramp, and their day on site counts up by itself.
2. **Keep the pay.** When heavy work has to stop, the plan shows how much lighter work (measuring, shuttering and rebar prep) is still safe in those hours, and what it is worth in wages. A shade option re-plans the day as if a tarpaulin covered the work area, as an "up to" estimate in rupees (in Howrah on 8 Oct: up to the full shift instead of a five-hour pause). Work is planned in daylight only, lunch stays free, and nobody is called in for a lone 15 minutes.
3. **Breaks called on time, in Hindi.** Each rest, stop and restart is an EventBridge Scheduler timer; when it fires, Amazon Polly speaks it and the phone plays it through a site speaker (a chime, then the message twice) while Chhaon is open on the phone. The day's audio is cached on the phone, so breaks are still called if the network drops. Each playback is reported, so "played on site" is measured, not assumed.
4. **A voice note for workers.** One tap shares the day's plan as a Hindi voice note to the crew's WhatsApp group, so workers who don't read hear the start time, the stop, water and the warning signs.
5. **A heat-illness protocol.** A 108 button first. The supervisor taps symptoms; triage and first aid follow India's National Action Plan on Heat Related Illnesses (NCDC), shown instantly even offline. A Step Functions workflow waits, asks for a re-check (a banner, chime and vibration on any screen) and escalates anything not clearly better; "Getting worse" can be tapped at any time. Emergency: call 108 with the site location to read out, nearest hospitals (Amazon Location), email to the safety officer.
6. **Ask in Hindi or English, by voice.** The supervisor taps the mic and asks in Hindi; Amazon Transcribe streams the speech to text, a Strands Agents agent on Amazon Bedrock (gpt-oss-120b, Mumbai region) answers ("Can we pour concrete at 2 tomorrow?") by calling the planner as a tool and shows its tool calls under the answer, and Polly reads it back. The model explains; deterministic code makes every safety call.
7. **Replay a real day.** The planner run on the actual weather of 30 May 2024.

Built for where the user is: Hindi first with times as people say them ("दोपहर 1 बजे"), readable in direct sunlight, large touch targets, three tabs, no sign-up, works on a cheap phone, keeps the last plan offline.

## Where AWS fits

- **AWS Lambda** (Python 3.12, arm64): WBGT physics, limits and the shift planner; the same tested code serves the API, the timers and the agent's tools.
- **Amazon EventBridge Scheduler**: one `at()` timer per announcement (Asia/Kolkata), deleted after firing, plus a 05:00 IST daily schedule that plans every registered site.
- **AWS Step Functions**: the heat-illness protocol with waits, task-token re-checks and escalation.
- **Amazon Polly** (Kajal, Hindi): announcements and the crew's voice note, cached in S3 so each sentence is synthesised once.
- **Amazon Bedrock + Strands Agents SDK**: the Hindi/English assistant. Strands drives the tool loop; the model is gpt-oss-120b on Bedrock's OpenAI-compatible endpoint in ap-south-1, signed with the function's IAM role (SigV4, no API keys). A plain tool loop on the same model and a labelled rule-based answer are the fallbacks.
- **Amazon Transcribe** (streaming, Hindi): spoken questions, streamed from the phone over a WebSocket the API signs.
- **Amazon Location Service**: site search and nearest hospitals.
- **Amazon DynamoDB**: one table for sites, plans, feed and incidents; TTL on health data; once-per-day markers so impact is never double-counted.
- **Amazon CloudFront + S3, API Gateway**: delivery from Indian edge locations; throttled HTTP API.
- **Amazon SNS + CloudWatch**: safety-officer alerts, alarms, and an impact dashboard (worker-hours kept out of unsafe heat, real sites and demo sites separate; announcements sent and played).
- **AWS SAM** (template and SAM CLI): the whole stack in one template, linted with `sam validate --lint` and deployed with `sam deploy`, least-privilege IAM per function, region ap-south-1 (Mumbai). Under a dollar per site per month at list prices, most of it Polly for the daily voice note.

Deliberately not used: SMS (needs TRAI DLT registration), SageMaker (nothing to train), always-on servers.

## Honest limits

Area forecasts are not site measurements; the WBGT code matches Liljegren's own C implementation to within 0.01°C but has not been checked against a WBGT meter on site; the ACGIH table is a screening tool; weather is from Open-Meteo's free, non-commercial API; Chhaon is not a medical device. Replays use ERA5 reanalysis (about 25 km). The shade option is an estimate. Polly speaks Hindi and Indian English only. Demo sites compress the 30-minute re-check to 20 seconds. Not yet tested with a supervisor on a working site.

## AI tools used

- **Building it:** Claude (Anthropic) as a coding agent for the code, tests, infrastructure and docs.
- **Inside the product:** OpenAI's open-weight gpt-oss-120b on Amazon Bedrock, driven by the Strands Agents SDK, writes the assistant's answers from planner tool results. No AI model makes a safety decision: WBGT, limits, the shift plan, triage and escalation are deterministic, tested code, and announcements are fixed templates.
