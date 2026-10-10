# Chhaon demo video: one supervisor's day (target 2:50, hard limit 3:00)

The judges see only this video. It has to show **what Chhaon does, who it is for, and where AWS fits**, with AWS **on screen** while it works, not just named. Tell it as one day on one site. Keep the voice-over calm, short and free of jargon (no "ACGIH", "Liljegren", "task token" out loud; those go in captions or the README).

## Before recording

**The day before:**
1. In the app, tap **Add my site**, search your own area (or use 📍), pick the workload a nearby site actually does, set the crew size and the daily wage, save. Real sites are planned by the 05:00 IST daily schedule, so the CloudWatch tile "real sites" gets a true number, separate from demo clicks.
2. **Required: real people.** Show Chhaon to a site supervisor (munshi) or contractor near you. Film, with permission: the phone on a Bluetooth speaker playing a break, workers in shade (faces optional), and 10 seconds of the supervisor saying in Hindi what they think. Write down one thing they asked for. This is the opening of the video.

**Setup on the day:**
- Desktop Chrome, live URL, DevTools device mode 390×844 so the app looks like a phone. Language Hindi. Zoom 100%.
- Second tab, AWS console, region **Mumbai (ap-south-1)**: EventBridge Scheduler → Schedules (group `chhaon-breaks`); Step Functions → `ProtocolStateMachine-…` → the latest execution (Graph view); CloudWatch → Dashboards → `chhaon-impact`.
- Third tab: the inbox of the alert email address, so the SNS email can be shown arriving.
- Record with OBS or Windows Game Bar (Win+Alt+R) with system audio, so Polly's Hindi voice is heard.
- Open the demo site once and ask the first Ask question off-camera, so the assistant is warm.
- Read today's numbers off the app before writing the captions (they change daily).

**Never wait on camera.** Record each wait off-camera and cut:
- **Test announcement:** tap "Test announcement" about two minutes before you need it. It arrives at the start of the next full minute (the time is shown); start recording that shot just before.
- **Re-check:** the demo re-check arrives about 20–30 seconds after "Tell me what to do". Jump-cut the wait.
- **Ask:** cut the 1–3 seconds of "thinking".

**Captions:** put the AWS service name as a lower-third caption whenever it is doing the work on screen (listed in the table). That is what makes "where AWS fits" obvious without a lecture.

## Shot list

| Time | On screen | Caption (lower third) | Voice-over |
|---|---|---|---|
| 0:00–0:14 | **Your site footage**: crew in the sun; the supervisor's 5-second Hindi reaction (subtitled). Overlay: *India, summer 2024: 110 confirmed heatstroke deaths, 40,000+ suspected (Health Ministry).* | – | "In the summer of 2024, India counted a hundred and ten confirmed heatstroke deaths and more than forty thousand suspected cases. Many were people who work outside, like this crew, and the person who decides when they rest is the supervisor." |
| 0:14–0:30 | Phone weather app with the air temperature now. Then Chhaon's **Today** card with the WBGT for that hour. | Modelled WBGT from the site's forecast | "This morning the air was only [29] degrees. A thermometer says that's fine. But heat illness depends on WBGT: heat, humidity, sun and wind together. Right now it's [33], over the limit for heavy work." |
| 0:30–0:52 | Scroll Today slowly: the strips (normal 9-to-6 with red bars vs the Chhaon plan with hatched stop, सुबह/दोपहर/शाम labels), the impact line, the water line, then the two cards: **lighter work during the stop** and **shade**, both in rupees. | AWS Lambda: hour-by-hour heat limits and the shift plan | "Chhaon works out, hour by hour, how much heavy work is safe, and moves it out of the dangerous hours, in daylight. When heavy work has to stop, it shows what lighter work is still safe, and what a tarpaulin is worth in wages, so a rest doesn't have to mean lost pay." |
| 0:52–1:14 | Tap **Turn on announcements**. Cut to the **Scheduler console**: today's schedules with their times. Cut to site footage or the app: the chime and the Hindi announcement (4 s of Polly). | Amazon EventBridge Scheduler → AWS Lambda → Amazon Polly (Hindi) | "Each break becomes a real timer on AWS. When it fires, a Lambda function has Amazon Polly say it in Hindi, through the site's speaker. The day's audio is cached on the phone, so breaks are still called if the network drops." |
| 1:14–1:26 | Tap **Send the crew a voice note** → the share sheet → WhatsApp group. | Amazon Polly voice note | "Workers who don't read get the plan as a voice note: when to work, when to stop, water, and the warning signs." |
| 1:26–2:02 | **Unwell** tab (108 button at the top). Tap *Dizzy* + *Vomiting* → first-aid steps, a 108 button and "Getting worse". [cut] The re-check card → **Getting worse** → red screen: Call 108, "Tell 108" with the site location, nearest hospitals. Cut to the **Step Functions graph** of that execution, then 2 s of the **SNS email** arriving in the inbox. | AWS Step Functions · Amazon Location Service · Amazon SNS | "If someone feels unwell, the supervisor taps what they see. A Step Functions workflow follows India's national first-aid protocol and asks again after thirty minutes, here twenty seconds. If it's getting worse: call 108, the nearest hospitals, and an email to the safety officer." |
| 2:02–2:22 | **Ask** tab → tap 🎤 and say "कल दोपहर दो बजे ढलाई कर सकते हैं?" (the words appear) → the answer, the 📋 line from the plan, the trace `check_task(day=tomorrow, start_hour=14, hours=2)` and *Strands Agents · Amazon Bedrock · gpt-oss-120b*. Tap **Hear the answer**. | Amazon Transcribe → Strands Agents + Amazon Bedrock → Amazon Polly | "Supervisors can just ask, in Hindi. Amazon Transcribe hears the question, a Strands agent on Amazon Bedrock answers by running the same planner as a tool, and Polly reads it back. The numbers come from the code, and the app shows them." |
| 2:22–2:40 | Tap the **30 May 2024, Aurangabad** card at the bottom of Today: "hottest air 2 PM, 44.7°C" vs "most dangerous hour 9 AM, WBGT 37.9". | Replay on the real weather of 30 May 2024 | "We replayed the real weather of a day people died. The air was hottest at two, but by WBGT the most dangerous hour was nine in the morning. The thermometer points at the wrong hour." |
| 2:40–2:52 | 2 s CloudWatch **chhaon-impact** (worker-hours kept out of unsafe heat, real sites vs demo), 2 s architecture diagram, back to the site footage. | Amazon CloudWatch · all serverless in Mumbai | "All serverless on AWS in Mumbai. Every hour of work moved out of unsafe heat is counted." |
| 2:52–3:00 | Logo, live URL, GitHub. | – | "Chhaon. Shade, on time." |

**Rules for the recording**
- Never edit an answer, a number or a screen. If the Ask answer shows "AI model unavailable", ask again.
- Keep the supervisor's words as they said them, with subtitles.
- Under 3:00 (YouTube shows the length). Public or unlisted. Check the link in a private window.
- Title: *Chhaon: heat-safe shifts for India's outdoor workers (Environmental Hacks, Heat and Water)*.
