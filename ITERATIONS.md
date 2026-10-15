# Iterations

What I changed after listening to calls. Oldest first.

Each entry:

```
## YYYY-MM-DD: short title
Heard: what sounded wrong (call folder and timestamp)
Cause: why it happened
Change: file and setting, old value -> new value
```

## 2026-10-14: Patient read its hang-up command out loud
Heard: first call (new_patient_booking), transcript at [02:01]: "Goodbye! functions.end_call()". The model wrote the tool call as text instead of making it, so it went to TTS, no hang-up happened, and the clinic ended the call.
Cause: gpt-4.1-mini sometimes emits a tool call as plain text. The prompt said "call end_call in the same turn", which nudged it to write the call inline.
Change: prompt now says "use the end_call tool ... never say the tool's name out loud". `PatientAgent.llm_node` strips any `functions.x(...)` text from the LLM stream before it reaches TTS, and treats a leaked end_call as a real one (waits for the goodbye to play, then hangs up).

## 2026-10-15: Patient talked over the real greeting
Heard: hours_address_parking and barge_in_dob_correction at [00:07]. The line opens with "This call may be recorded for quality and training purposes." The patient answered that with "Hi! I'm..." and got cut off by the actual "Thanks for calling..." greeting.
Cause: the disclaimer is a complete sentence, so the turn detector handed us the turn after about 0.7 s, which is correct for a normal turn but wrong here.
Change: `PatientAgent.on_user_turn_completed` skips replying to a turn that's only a recording disclaimer (no question in it), so the patient waits for the real hello like a person would.

## 2026-10-15: Persona phone numbers had no area code
Heard: barge_in_dob_correction from [01:32] to [03:04]. The receptionist asked for the full ten-digit number four times. The patient only knew "555-0108", so the call never got to booking.
Cause: the scenario files used seven-digit numbers.
Change: every persona now has a ten-digit number (805-555-01xx).

## 2026-10-15: Clinic greeting named its parent company
Heard: from 2026-10-15 on, the greeting at [00:07] includes the name of the company behind the test line. That name must not appear anywhere in this repo.
Change: transcript.py masks it as "[company]" in everything saved. `py -m caller redact` cleans transcripts saved before the fix.
