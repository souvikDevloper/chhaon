# Chhaon demo video: one supervisor's day (target 2:50, hard limit 3:00)

The judges see only this video. It has to show **what Chhaon does, who it is for, and where AWS fits**, with AWS **on screen** while it works, not just named. Tell it as one day on one site. Keep the voice-over calm, short and free of jargon (no "ACGIH", "Liljegren", "task token" out loud; those go in captions or the README).

## Before recording

**The evening before (so the dashboard has real numbers):**
1. In the app, tap **Add my site**, search your own area (or use 📍), pick the workload a nearby site actually does, set the crew size, save. Real sites are planned by the 05:00 IST daily schedule, so tomorrow morning the CloudWatch tile "real sites" has a true number, separate from demo clicks.
2. Ask the supervisor of a nearby site (with permission) if you can film 2–3 minutes: the phone on a Bluetooth speaker, a break announcement playing, workers in shade. Faces are optional; hands, boots, helmets and the speaker are enough.

**Setup on the day:**
- Desktop Chrome, live URL, DevTools device mode 390×844 so the app looks like a phone. Language Hindi. Zoom 100%.
- Second tab: AWS console, region **Mumbai (ap-south-1)**: EventBridge Scheduler → Schedules (group `chhaon-breaks`); Step Functions → `ProtocolStateMachine-…` → latest execution (Graph view); CloudWatch → Dashboards → `chhaon-impact`; Lambda → `chhaon-AskFunction-…` → Monitor (optional).
- Record with OBS or Windows Game Bar (Win+Alt+R) with system audio, so Polly's Hindi voice is heard.
- Open the demo site once and ask the first Ask chip off-camera, so the assistant is warm.
- Read today's numbers off the app before writing the captions (they change daily).

**Captions:** put the AWS service name as a lower-third caption whenever it is doing the work on screen (listed in the table). That is what makes "where AWS fits" obvious without a lecture.

## Shot list

| Time | On screen | Caption (lower third) | Voice-over |
|---|---|---|---|
| 0:00–0:12 | Site footage at mid-morning: crew in the sun, the phone and speaker on a table. Overlay: *India, summer 2024: 110 confirmed heatstroke deaths, 40,000+ suspected (Health Ministry).* | – | "In the summer of 2024, India counted a hundred and ten confirmed heatstroke deaths and more than forty thousand suspected cases. Many were people who work outside, like this crew." |
| 0:12–0:30 | Phone weather app showing the air temperature now (e.g. 29°C). Then Chhaon's **Today** card with the WBGT for that hour. | Modelled WBGT from the site's forecast | "At nine this morning the air was only [29] degrees. A thermometer says that's fine. But heat illness depends on WBGT: heat, humidity, sun and wind together. Right now it's [33], over the limit for heavy work." |
| 0:30–0:50 | Scroll the Today screen slowly: the two strips (normal 9-to-6 with red bars vs the Chhaon plan with hatched stop), the impact line, the water line, the **shade** card. | AWS Lambda: hour-by-hour heat limits and the shift plan | "Chhaon is for the site supervisor. Every hour it works out how many minutes of heavy work are safe, and moves the work out of the dangerous hours, keeping as much paid work as the heat allows. It even shows what a tarpaulin over the work area would give back." |
| 0:50–1:15 | Tap **Turn on announcements**. Cut to the **Scheduler console**: today's schedules listed with times. Back on site: the speaker plays the Hindi announcement (let 4 s of Polly play). | Amazon EventBridge Scheduler → AWS Lambda → Amazon Polly (Hindi) | "Each break becomes a real timer on AWS. When it fires, a Lambda function has Amazon Polly say it in Hindi, at the minute it's due, through the site's speaker. The audio is cached on the phone, so breaks are still called if the network drops." |
| 1:15–1:28 | Tap **Send the crew a voice note** → the phone's share sheet → WhatsApp group. (Optional: a worker listening.) | Amazon Polly voice note | "Workers who don't read get the day's plan as a voice note: start time, the stop, water, and the warning signs." |
| 1:28–2:02 | **Unwell** tab: the red 108 button at the top. Tap *Dizzy* + *Vomiting* → first-aid steps. Wait for the re-check card (20 s in the demo) → **Getting worse** → red screen: Call 108, nearest hospitals. Cut to the **Step Functions graph** of that execution. | AWS Step Functions · Amazon Location Service · Amazon SNS | "If someone feels unwell, the supervisor taps what they see. A Step Functions workflow follows India's national first-aid protocol, asks again after thirty minutes, here twenty seconds, and if it's getting worse: call 108, the nearest hospitals, and an alert to the safety officer." |
| 2:02–2:20 | **Ask** tab → tap 🎤 and say "कल दोपहर दो बजे ढलाई कर सकते हैं?" (the words appear as you speak) → the answer, the line *Strands Agents · Amazon Bedrock · gpt-oss-120b* and the trace `check_task(day=tomorrow, start_hour=14, hours=2)`. Tap **Hear the answer**. (If the mic is awkward on a laptop, tap the chip instead.) | Amazon Transcribe → Strands Agents + Amazon Bedrock → Amazon Polly | "Supervisors can just ask, in Hindi. Amazon Transcribe hears the question, a Strands agent on Amazon Bedrock answers by running the same planner as a tool and shows its working, and Polly reads it back. The model explains; the safety decision is always the code's." |
| 2:20–2:38 | Tap the **30 May 2024** card at the bottom of Today → Aurangabad: "hottest air 2 PM, 44.7°C" vs "most dangerous hour 9 AM, WBGT 37.9". | Replay on the real weather of 30 May 2024 | "We replayed the real weather of a day people died. The air was hottest at two, but by WBGT the most dangerous hour was nine in the morning. The thermometer points at the wrong hour." |
| 2:38–2:52 | CloudWatch **chhaon-impact** dashboard: *Worker-hours kept out of unsafe heat* (real sites vs demo), announcements sent and played. 2 s of the architecture diagram. | Amazon CloudWatch · all serverless in Mumbai | "Everything runs serverless on AWS in Mumbai, and every hour of work moved out of unsafe heat is counted." |
| 2:52–3:00 | Logo, live URL, GitHub. | – | "Chhaon. Shade, on time." |

**Rules for the recording**
- Never edit an answer, a number or a screen. If the Ask answer shows "AI model unavailable", ask again.
- If you could not film a site, use a still photo you took yourself for 0:00–0:12 and skip the speaker shot (keep the console + app audio).
- Under 3:00 (YouTube shows the length). Public or unlisted. Check the link in a private window.
- Title: *Chhaon: heat-safe shifts for India's outdoor workers (Environmental Hacks, Heat and Water)*.
