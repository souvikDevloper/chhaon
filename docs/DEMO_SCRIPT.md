# Chhaon demo video: script and shot list (target 2:50, hard limit 3:00)

The judges see only this video. Rules: it must show what Chhaon does, who it is for, and where AWS fits, with AWS **on screen** (console shots), not just named.

**Setup before recording**
- Desktop Chrome, open the live URL, DevTools device mode at 390×844 (iPhone 12/13 size) so the app looks like a phone. Language Hindi. Zoom 100%.
- Second tab: AWS console, region **Mumbai (ap-south-1)**, with these open: EventBridge Scheduler → Schedules (group `chhaon-breaks`); Step Functions → the protocol state machine; CloudWatch → Dashboards → `chhaon-impact`.
- Record with OBS or Windows Game Bar (Win+Alt+R). Record system audio so Polly's Hindi voice is heard.
- Before recording: open the demo site once, press "Test announcement in 1 minute", and start recording ~20 s before it fires so you don't have to wait on camera.

| Time | On screen | Voice-over (English; keep it calm and slow) |
|---|---|---|
| 0:00–0:14 | Your own footage: a construction site near you at midday, workers in the sun (ask permission; faces optional). Overlay: *30 May 2024, Rourkela: 10 suspected heatstroke deaths reported at one hospital.* | "In the summer of 2024, India counted 110 confirmed heatstroke deaths and more than forty thousand suspected cases. Most of the people at risk work outdoors, like this crew." |
| 0:14–0:34 | Phone weather app or the app's card: **29°C** at 9 AM in Howrah. Then Chhaon's card: **WBGT 33.6**. | "This morning in Howrah the air was only 29 degrees. A thermometer says that's fine. But heat illness depends on WBGT, which adds humidity, sun and wind. At 9 AM, WBGT was 33.6. That is past the safe limit for heavy work." |
| 0:34–0:46 | Welcome screen → tap **Open the demo site**. | "Chhaon is for the person who decides when a crew works: the site supervisor, with a phone, standing in the sun. Hindi first, no sign-up." |
| 0:46–1:10 | Today screen. Point at the two strips: normal 9-to-6 (red marks) vs Chhaon plan (hatched stop hours). Point at "unsafe hours avoided" and the new-workers note. | "Every hour, Chhaon computes WBGT from the site's forecast, applies the ACGIH work-rest limits for the crew's workload, and moves the work out of the unsafe hours, keeping as much paid work as the heat allows. Workers in their first week get stricter limits." |
| 1:10–1:32 | Tap **Turn on announcements**. Cut to the Scheduler console: list of today's schedules. Back to the app: the test announcement arrives and **Polly speaks Hindi** (let it play 3–4 s). | "Each break becomes a real timer in Amazon EventBridge Scheduler. When it fires, a Lambda function has Amazon Polly say it in Hindi, and the phone plays it through the site's speaker." |
| 1:32–2:02 | **Unwell** tab → tap Dizzy + Vomiting → steps appear. Wait for the re-check card → tap **Getting worse** → red emergency screen: Call 108, nearest hospitals. Cut to Step Functions execution graph. | "If a worker feels unwell, the supervisor taps what they see. AWS Step Functions runs India's national first-aid protocol: shade, salts, a re-check in thirty minutes (twenty seconds in this demo). Getting worse escalates: call 108, the nearest hospitals from Amazon Location, and an alert to the safety officer." |
| 2:02–2:18 | **Ask** tab → tap the Hindi chip "कल दोपहर 2 बजे ढलाई कर सकते हैं?" → answer appears; tap **Hear the answer**. | "Supervisors can ask in Hindi. A model on Amazon Bedrock, here in the Mumbai region, answers by calling the planner as a tool. The model explains; the safety decision is always code." (The line under the answer shows *Amazon Bedrock · gpt-oss-120b* and the tool it used.) |
| 2:18–2:40 | **Replay** → Aurangabad: "Hottest air 14:00, 44.7°C" vs "Most dangerous hour 09:00, WBGT 37.9". Then Rourkela: unsafe from 6 AM; the official ban started at 11. | "We replayed the real weather of the day people died. In Aurangabad the air was hottest at 2 PM, but the most dangerous hour was 9 AM. In Rourkela, heavy work was unsafe from early morning, hours before the official ban began. The thermometer points at the wrong hour." |
| 2:40–2:52 | Architecture diagram, then the CloudWatch dashboard with **Unsafe work-hours avoided**. | "All serverless on AWS in Mumbai, defined in one template, and every unsafe hour moved out of the heat is counted on CloudWatch." |
| 2:52–3:00 | Logo + URL + GitHub. | "Chhaon. Shade, on time." |

**Before the Ask shot:** ask the chip question once off-camera so the Lambda is warm. If an answer ever shows the "AI model unavailable" label, ask again; never edit an answer in. Optional 2-second cut: CloudWatch dashboard tile *Assistant answers by engine* showing `bedrock-mantle`.

**Checklist before upload**
- Under 3:00 (YouTube shows the length). Public or unlisted.
- Open the link in a private window to check it plays signed-out.
- Title: *Chhaon: heat-safe shifts for India's outdoor workers (Environmental Hacks, Heat and Water)*.
