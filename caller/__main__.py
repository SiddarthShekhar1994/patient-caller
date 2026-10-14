"""CLI.

Terminal 1:  py -m caller worker                          (leave it running)
Terminal 2:  py -m caller run --scenario new_patient_booking
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
    run = sub.add_parser("run", help="place one call")
    run.add_argument("--scenario", required=True, help=", ".join(list_scenario_ids()))
    args = parser.parse_args()

    cfg = load_config()  # fails fast on a bad .env, and loads it into os.environ

    if args.cmd == "worker":
        from livekit.agents import cli

        from .session import server

        sys.argv = [sys.argv[0], "start"]
        cli.run_app(server)
        return

    scenario = load_scenario(args.scenario)
    asyncio.run(_run_one(cfg, scenario.id))


async def _run_one(cfg, scenario_id: str) -> None:
    from .telephony import start_call, wait_for_call_end

    room = await start_call(cfg, scenario_id)
    print(f"Calling the clinic for '{scenario_id}' (room {room}).")
    print("The live transcript prints in the worker terminal.")
    if await wait_for_call_end(cfg, room):
        print("Call ended.")
    else:
        print("Call didn't start or didn't end cleanly; check the worker terminal.")


if __name__ == "__main__":
    main()
