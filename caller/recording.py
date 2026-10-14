"""Saving the call audio and its metadata.

LiveKit Agents records every session itself (RecorderIO): a stereo OGG with
the clinic on the left channel and our patient on the right, both on one
timeline. We copy that file out of the job's temp folder when the call ends.
That avoided setting up Egress plus a storage bucket for the same result.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

CALLS_DIR = Path(__file__).resolve().parent.parent / "calls"


def call_dir_for(room_name: str) -> Path:
    """calls/<YYYYmmdd-HHMMSS>-<scenario-id>/, created on first use."""
    path = CALLS_DIR / room_name.removeprefix("call-")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_recording(session_dir: Path, call_dir: Path) -> Path | None:
    src = session_dir / "audio.ogg"
    if not src.is_file() or src.stat().st_size == 0:
        return None
    dst = call_dir / "recording.ogg"
    shutil.copyfile(src, dst)
    return dst


def save_meta(call_dir: Path, **fields) -> None:
    fields["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (call_dir / "meta.json").write_text(json.dumps(fields, indent=2), encoding="utf-8")
