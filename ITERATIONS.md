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
