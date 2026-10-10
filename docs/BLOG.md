# The thermometer points at the wrong hour: building heat-safe shifts on AWS

*Draft for AWS Builder Center. Edit freely; it should sound like you.*

On 30 May 2024, ten people with suspected heatstroke were reported dead at one government hospital in Rourkela, Odisha. That week the state barred its own staff from outdoor work between 11 AM and 3 PM, the hours when the air is hottest.

For Environmental Hacks I wanted to know one thing: was 11 to 3 the right window?

## Temperature is the wrong number

Heat illness doesn't track air temperature. It tracks **WBGT**, the wet bulb globe temperature, which combines air temperature, humidity, sunshine and wind. Occupational-safety limits are written in WBGT: the ACGIH table says, for example, that an acclimatised worker doing heavy work (digging, carrying sacks, a concrete pour) should work no more than 15 minutes an hour once WBGT passes 29°C. Above 30.5°C the table gives no screening value at all: ACGIH says that needs detailed analysis or physiological monitoring, so Chhaon simply stops that work.

No weather station measures WBGT; it needs a black globe and a wet wick in the sun. But Liljegren and colleagues at Argonne published a model in 2008 that computes it from an ordinary forecast: temperature, humidity, wind, solar radiation, pressure and the sun's angle. I ported it to Python, then checked the wet-bulb part against Open-Meteo's own wet-bulb output for 96 hours of Howrah forecast: mean difference −0.05°C, worst 0.46°C.

Then I ran it on the real (ERA5) weather of 30 May 2024. These are modelled values from a 25 km weather grid, not measurements, but the pattern is the point.

- **Aurangabad, Bihar:** the air was hottest at 2 PM, 44.7°C. By WBGT the most dangerous hour was **9 AM**: 39°C air, but humid and still, WBGT 37.9°C. By 2 PM the air was drier and windier and WBGT had fallen to 32.4.
- **Rourkela, Odisha:** heavy work was past the safe limit from **6 AM** and stayed there until 5 PM. The 11-to-3 ban covered four of those eleven hours.

The thermometer points at the wrong hour. And on the day I started building, in Howrah in October, the air at 9 AM was only 29°C while WBGT was 33.6°C.

## What I built

**Chhaon** (छाँव, "shade") is a Hindi-first app for the person who decides when a crew works: the site supervisor with a phone.

- It plans the day hour by hour: WBGT from the site's forecast, the safe share of each hour for the crew's workload, and a shift that keeps the normal hours where they're safe and moves the unsafe minutes into the coolest hours. Workers lose pay when they rest, so the plan tries to keep as much paid work as the heat allows, and shows what a tarpaulin over the work area would give back.
- It announces every break in Hindi, on time, through a speaker on site, and sends the crew a Hindi voice note for WhatsApp, because many workers don't read.
- When someone feels unwell, it walks the supervisor through India's national first-aid protocol (even offline), re-checks, and escalates.

## The AWS parts I'm proud of

**Every break is a timer, not a loop.** Instead of a server checking the clock, each announcement is an Amazon EventBridge Scheduler one-time schedule: `at(2026-10-09T10:45:00)` in `Asia/Kolkata`, with `ActionAfterCompletion: DELETE`. When it fires, a Lambda has Amazon Polly say it in Hindi (the Kajal voice) and caches the MP3 in S3 so the same sentence is never synthesised twice. Between breaks, nothing runs.

**A heat-illness case is a workflow that can wait.** AWS Step Functions runs the protocol: first aid, a 30-minute wait, then a `waitForTaskToken` step that pauses until the supervisor answers "better", "same" or "worse". Anything not clearly better escalates: call 108, the nearest hospitals from Amazon Location Service, and an SNS alert to the safety officer. If nobody answers, the timeout escalates too. Waiting 30 minutes costs nothing because no server holds the state.

**The model explains; code decides.** A Strands Agents agent on Amazon Bedrock (gpt-oss-120b, in the Mumbai region) answers questions like "कल दोपहर 2 बजे ढलाई कर सकते हैं?" ("can we pour concrete at 2 tomorrow?"), but every number comes from tools that call the same tested planner, and the app shows the tool calls under the answer. Safety announcements are fixed templates, never generated text; for first aid, the national guideline's own steps are shown and read out, not the model's paraphrase.

## What fought back

- **Bedrock quotas on a new account.** Every bedrock-runtime quota on my brand-new account was applied at 0, and support could not raise them for a new account. Bedrock's OpenAI-compatible endpoint (bedrock-mantle) has its own quotas and worked. Strands Agents has an OpenAI-compatible model provider, so I pointed it at that endpoint and added a small `httpx` auth hook that signs each request with the Lambda's IAM role (SigV4): no API key anywhere. If no model answers in 18 seconds the app gives a rule-based answer and says so.
- **My first impact number was wrong.** Heavy work never gets a full hour in the ACGIH table, so my "unsafe hours avoided" counted every hour of a heavy-work shift as unsafe, even on a cool day. An independent review caught it. Now an hour only counts when the heat cuts it below what that work is allowed on a cool day, and the dashboard counts each site-day once, with demo sites separate.
- **Hindi through PowerShell.** The AWS CLI reads `file://` inputs in the Windows code page; Devanagari came out garbled until I set `AWS_CLI_FILE_ENCODING=UTF-8`.
- **CloudFormation and YAML anchors.** I reused a retry block with a YAML anchor; CloudFormation rejects aliases. Expanding them by hand fixed it.
- **Speech without a microphone in the loop.** To test Hindi voice questions end to end, I had Polly say the question as 16 kHz PCM and streamed that to Transcribe through the same signed WebSocket the phone uses. It came back as "कल दोपहर दो बजे ढलाई कर सकते हैं।"
- **Designing for sunlight.** Dark themes look great on a laptop and are unreadable outside at noon. The app is white, high-contrast, and marks stopped hours with hatching as well as colour.

## What's next

Testing it with supervisors on real sites comes first. After that: a WBGT meter on site would beat any forecast; feature-phone voice calls and more languages (Bhojpuri, Bengali, Odia) would reach workers directly; and heat-health data from a hospital could tell us which rules actually save lives.

Code: https://github.com/souvikDevloper/chhaon
