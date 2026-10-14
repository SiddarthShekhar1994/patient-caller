# patient-caller

A Python voice bot that phones a clinic's AI receptionist, plays a patient with a specific goal (book a visit, get a refill, ask about insurance), and records the call so I can find bugs in how the receptionist agent behaves.

It runs on LiveKit Agents in pipeline mode: Deepgram for speech-to-text, OpenAI for the LLM, Cartesia for text-to-speech. Calls go out through a Twilio Elastic SIP trunk.

The bot can only dial one number, the clinic's test line. That number is hard-coded in `caller/config.py` and checked again right before every dial.

Status: Phase 1. The bot places one call and prints a live transcript. Recording comes in Phase 2.

## Install (Windows PowerShell)

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m livekit.agents download-files
Copy-Item .env.example .env
notepad .env
```

If `Activate.ps1` fails with "running scripts is disabled on this system", run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

After activating, plain `py` runs the venv's Python. Don't add `-3.13` from then on, because that skips the venv.

`download-files` fetches the Silero VAD and turn-detector model weights ahead of time so the first call doesn't stall on a download.

## Phone line setup

Do Twilio first. LiveKit needs the address and credentials Twilio gives you.

### 1. Twilio trunk

Twilio moves its console menus around now and then. If a name below doesn't match, search the console for "Elastic SIP Trunking".

1. Confirm the account is upgraded (not trial) and you own one voice-capable US number.
2. Elastic SIP Trunking > Manage > Trunks > Create new SIP Trunk. Name it `patient-caller`.
3. Open the trunk and go to **Termination**.
   - Termination SIP URI: pick something unique, like `patient-caller-sk`. Twilio adds `.pstn.twilio.com`. Write down the full address.
   - Under Authentication > Credential Lists, click **+** to make a new list. Friendly name `livekit`, then a username and password. Twilio wants the password to be 12+ characters with upper case, lower case and a digit. Write both down and save.
   - Leave IP Access Control Lists empty. LiveKit Cloud doesn't call from fixed IPs, so username and password is the option that works.
4. Go to the trunk's **Numbers** page > Add an Existing Number, and pick your number.
5. Check that geo permissions allow calls to the United States (Voice > Settings > Geo permissions). US is usually on by default.

### 2. LiveKit outbound trunk

Use single quotes in PowerShell. Inside double quotes, PowerShell expands anything after a `$`, which would mangle a password containing one.

If `lk` isn't installed yet, run `winget install LiveKit.LiveKitCLI`, then open a new PowerShell window so it lands on your PATH.

```powershell
lk cloud auth
lk project list
```

Log in through the browser, pick your project, and accept it as the default. `lk project list` prints the project's `wss://...livekit.cloud` URL, which is what `LIVEKIT_URL` in `.env` needs. The `https://cloud.livekit.io/projects/...` dashboard link won't work there. If you'd rather paste keys: `lk project add --url 'wss://...' --api-key '...' --api-secret '...' patient-caller`.

```powershell
lk sip outbound create --name 'twilio-out' --address 'patient-caller-sk.pstn.twilio.com' --numbers '+1XXXXXXXXXX' --auth-user 'your-user' --auth-pass 'your-password'
lk sip outbound list
```

Copy the `ST_...` ID into `.env` as `SIP_OUTBOUND_TRUNK_ID`. Set `CALLER_NUMBER` to the same number you passed to `--numbers`.

### 3. Test the trunk on your own phone

Point the test at your own cell, not the clinic line. The submission form asks for your Twilio number, so the graders probably find your calls by it, and a silent test call doesn't belong next to the real ones.

```powershell
lk sip participant create --trunk 'ST_xxxx' --call '+1YOURCELL' --room 'trunk-test' --identity 'trunk-test' --wait
```

Your cell should ring with your Twilio number on caller ID. Answer it. You'll hear silence, since nothing else is in the room yet, and that silence means the trunk works. Hang up.

If it doesn't ring, check these in order:

1. Twilio Console > Monitor > Logs > Errors. Twilio usually says exactly what it rejected.
2. The username and password in `lk sip outbound create` match the Twilio credential list exactly.
3. `--address` is the termination URI, ending in `.pstn.twilio.com`.
4. `--numbers` is the number you bought on this Twilio account, in `+1...` form.
5. The account is upgraded and US geo permissions are on.

To fix a value on the LiveKit side without starting over: `lk sip outbound update --id 'ST_xxxx' --auth-pass 'new-password'` (same pattern for `--address` and `--numbers`).

If Twilio rejects a number you bought with error 21210 or 32204 ("not yet verified" / "Caller ID is unauthorized"), open Monitor > Debugger in the Twilio Console. The request inspector shows the exact From number Twilio received. In my case it was correct and the number itself was stuck, so buying a fresh number fixed it.

## Placing a call

Two PowerShell windows, both in the repo folder with the venv active.

Window 1, start the worker and leave it running:

```powershell
py -m caller worker
```

Wait for a line saying the worker registered. Window 2, place a call:

```powershell
py -m caller run --scenario new_patient_booking
```

The live transcript prints in window 1, timed from the moment the clinic picks up. Window 2 says "Call ended." when the room closes. Stop the worker with Ctrl+C.

Scenarios live in `scenarios/*.yaml`. The number dialed is never read from them. It's a constant in `caller/config.py`.
