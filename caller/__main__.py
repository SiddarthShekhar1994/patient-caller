"""CLI.

Terminal 1:  py -m caller worker                          (leave it running)
Terminal 2:  py -m caller run --scenario new_patient_booking
             py -m caller run --all                       (one call at a time)
             py -m caller voices                          (list Cartesia voices)
             py -m caller review                          (writes bug_candidates.md)
"""

import argparse
import asyncio
import sys

from .config import load_config
from .scenarios import list_scenario_ids, load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(prog="py -m caller")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("worker", help="start the voice agent worker and leave it running")
    run = sub.add_parser("run", help="place calls")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--scenario", help=", ".join(list_scenario_ids()))
    which.add_argument("--all", action="store_true", help="every scenario, one at a time")
    run.add_argument("--pause", type=int, default=20, help="seconds between calls with --all")
    sub.add_parser("voices", help="list English Cartesia voices to pick persona voices from")
    review = sub.add_parser("review", help="scan saved calls and write bug_candidates.md")
    review.add_argument("--model", help="OpenAI model for the review (default: LLM_MODEL)")
    args = parser.parse_args()

    cfg = load_config()  # fails fast on a bad .env, and loads it into os.environ

    if args.cmd == "worker":
        from livekit.agents import cli

        from .session import server

        sys.argv = [sys.argv[0], "start"]
        cli.run_app(server)
    elif args.cmd == "voices":
        _list_voices()
    elif args.cmd == "review":
        from .review import run_review

        out = asyncio.run(run_review(args.model or cfg.llm_model))
        print(f"Wrote {out.name}. Listen to each timestamp before trusting it.")
    else:
        ids = list_scenario_ids() if args.all else [args.scenario]
        for sid in ids:
            load_scenario(sid)  # validate them all before dialing anything
        asyncio.run(_run_many(cfg, ids, args.pause))


async def _run_many(cfg, ids: list[str], pause: int) -> None:
    from .telephony import start_call, wait_for_call_end

    for n, sid in enumerate(ids, 1):
        room = await start_call(cfg, sid)
        print(f"[{n}/{len(ids)}] Calling the clinic for '{sid}' (room {room}).")
        print("The live transcript prints in the worker terminal.")
        if await wait_for_call_end(cfg, room):
            print("Call ended.")
        else:
            print("Call didn't start or didn't end cleanly; check the worker terminal.")
            return
        if n < len(ids):
            print(f"Next call in {pause}s (Ctrl+C to stop).")
            await asyncio.sleep(pause)


def _list_voices() -> None:
    import os

    import httpx

    resp = httpx.get(
        "https://api.cartesia.ai/voices",
        params={"limit": 100},
        headers={"X-API-Key": os.environ["CARTESIA_API_KEY"], "Cartesia-Version": "2025-04-16"},
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    voices = body.get("data", body) if isinstance(body, dict) else body
    for v in voices:
        if v.get("language", "en") != "en":
            continue
        desc = (v.get("description") or "").replace("\n", " ")[:70]
        print(f"{v['id']}  {v.get('gender', '?'):<10} {v.get('name', '')[:28]:<28} {desc}")


if __name__ == "__main__":
    main()
