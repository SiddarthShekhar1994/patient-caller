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

## 2026-10-15: Worker crashed in LiveKit's resampler on Windows
Heard: no audio problem, but mid-batch a "Microsoft Visual C++ Runtime Library: Assertion failed" dialog popped up from livekit_ffi.dll (soxr fft4g_cache.h, LSX_FFT_BR == NULL), freezing the worker.
Cause: soxr, the resampler bundled in LiveKit's native library, keeps a shared FFT cache. Several resamplers being created and torn down at once can trip its sanity check, and the Windows build shows that as a blocking dialog. We were adding two resamplers ourselves: room audio at 24 kHz converted to 8 kHz for Deepgram and to 16 kHz for Silero VAD.
Change: room audio input is now 16 kHz (`AudioInputOptions(sample_rate=16000)`) and Deepgram takes 16 kHz, so neither STT nor VAD creates a resampler of its own.
It damaged two calls from that batch, which I deleted: hours_address_parking at 19:13 (the recording stops at 1:11 of a three-minute call) and barge_in_dob_correction at 19:14 (no recording saved). Each scenario has another complete call.

## 2026-10-15: Patient said the receptionist's line
Heard: privacy_other_patient at [00:23]. After giving her husband's birthday, the patient went on in the same breath: "I'm sorry, but I can't share appointment details with anyone other than the patient. Is there something else I can help you with?" That's the receptionist's job, in the patient's voice.
Cause: the model sometimes writes a second paragraph after its answer. It happened in three calls (cancel_with_fee at [01:03] and refill_named_med at [01:54] too). Twice it was just a second turn's worth of talking; here it wrote the other side of the conversation.
Change: `PatientAgent.llm_node` stops passing text to TTS at the first line break of a reply (tool calls still go through, so a goodbye plus end_call works). The prompt now says to keep each turn on one line and only ever say the patient's own words.
Checked: reran privacy_other_patient (20261015-172227). Every patient turn was one line in Angela's own voice.
