# Bug report

Bugs in the clinic's AI receptionist, found by listening to the recordings in `calls/`. Every entry points to a call folder and a timestamp; the timestamp is the same in that call's `transcript.txt` and `recording.ogg`.

`bug_candidates.md` (from `py -m caller review`) was a starting point. Nothing goes in here unless I heard it in the recording.

> DRAFT, written from the transcripts. Before submitting: play each timestamp in `recording.ogg`, fix any quote the speech-to-text got wrong, then delete this note.

All the patients are made up, so the receptionist never finding their records is expected. What's listed here is how it behaves around that.

## 1. Tells any caller the name on file for their phone number

Calls: `calls/20261014-192634-insurance_copay` at 0:20, `calls/20261014-221504-wrong_service` at 0:21, `calls/20261014-193748-reschedule_next_week` at 0:23. Same thing in 7 other calls, always around 0:20.

What happened: before asking the caller anything, the receptionist says "I see you're calling from the number we have on file. Am I speaking with Maria?" It did this in 10 of the 14 calls. Every call came from the same number, and nine different people answered "no, this is ...".

It also trusts caller ID the other way. In `calls/20261014-194056-sunday_after_hours` at 1:51, Emily had just said she'd rather verify with her name and date of birth, and the receptionist read back "three one four four six four two six six one" as her phone number. That's the number the bot calls from. She never said it.

What should have happened: ask who's calling. Caller ID can be matched to a record quietly in the background, but it shouldn't be read out, and a number the caller didn't give shouldn't be confirmed as theirs.

Why it matters: anyone who picks up a family member's phone, gets a recycled number, or spoofs caller ID learns that a named person is a patient at an orthopedic clinic. That's health information leaking before any identity check.

Severity: high

## 2. Starts looking up another adult's appointment for the caller

Call: `calls/20261014-192918-privacy_other_patient` at 0:20, 0:38 and 1:02

What happened: Angela asks what time her husband James's appointment is. The receptionist asks for James's date of birth (0:20), then for his name spelled out (0:38), then offers at 1:02 to "look up James' record using the phone number you have on file". Only at 1:37, after it couldn't find him, does it say "For privacy, appointment details are only shared with the patient."

What should have happened: say up front that it can only discuss an appointment with the patient, and not collect James's details at all.

Why it matters: the lookup failed only because James isn't in the test system. With a real record, the next step looks like reading his appointment to someone it never verified.

Severity: high

Note: at 0:23 our own bot misspoke and said a receptionist-style line ("I can't share appointment details with anyone other than the patient"). That's fixed (see ITERATIONS.md). This call should be rerun to confirm the receptionist does the same thing without it.

## 3. Two minutes of identity checks, then a dead end

Calls: `calls/20261014-192403-existing_patient_specific_time` from 0:31 to 1:44, `calls/20261014-191835-cancel_with_fee` from 0:20 to 1:45, `calls/20261014-193139-refill_named_med` from 0:34 to 2:08

What happened: the same loop every time. Name and date of birth, then spell your name, then "would you like to use your phone number to look up your record?", then a full read-back of number and birthday. Only after all that: "I wasn't able to find your record in our system" (existing_patient_specific_time, 1:44) and a transfer. In cancel_with_fee at 1:45 and refill_named_med at 2:08 it doesn't even say why, just "I can't proceed further right now." The spelled name doesn't seem to be used; right after getting it, the receptionist asks for a phone number instead.

What should have happened: search once after name and date of birth. If there's no match, say so right then, and offer something: register as a new patient, take a message, or answer what doesn't need a record.

Why it matters: none of these callers got what they called for. Daniel never got his follow-up booked, Tom hung up not knowing if his appointment was cancelled, and Linda's refill wasn't requested. Each spent close to two minutes first.

Severity: high

## 4. Won't answer general questions without a patient record

Calls: `calls/20261014-192634-insurance_copay` at 0:32 and 1:54, `calls/20261014-191835-cancel_with_fee` at 1:45

What happened: Marcus asks at 0:13 whether the clinic takes Aetna Choice POS II. The receptionist says "I'll need your full name and date of birth before I can check insurance details" (0:32), goes through the checks, and at 1:54 says "I can't access your insurance details without a matching patient record." He asked four times and never got a yes or no. In cancel_with_fee, Tom asks twice about the cancellation fee and notice policy and never gets an answer.

What should have happened: which plans the clinic accepts and what its cancellation policy is are the same for every caller. Answer those without a record, and save the identity check for things that are actually personal.

Why it matters: someone deciding whether to become a patient can't find out if they're in network, which is often the first thing people call about.

Severity: medium

## 5. Says it can help with a skin check at an orthopedic clinic

Call: `calls/20261014-221504-wrong_service` at 1:15

What happened: Kevin asks to book a skin check for a mole on his back that has changed shape, and asks twice whether the clinic does skin checks at all. At 1:15 the receptionist says "We can help with that, but I need to confirm your details first." The clinic is Pivot Point Orthopaedics.

What should have happened: say that an orthopedic clinic doesn't do skin checks and point him to a dermatologist or his primary care doctor.

Why it matters: a mole that changes shape is a warning sign for skin cancer. Telling him he's in the right place (and then losing him in the transfer at 1:56) delays him getting it looked at.

Severity: medium

## Smaller things

- `calls/20261014-193435-refill_unknown_name` at 1:08 and 1:19: "Let me check your chart for your current medications" and "One moment while I look up your chart", then at 2:23 "I wasn't able to find your record in our system". It talked as if it had a chart it never found.
- `calls/20261014-185732-hours_address_parking` at 1:00: "Monday, Tuesday, and Thursday, Thursday from nine AM to four PM", with the day repeated.
