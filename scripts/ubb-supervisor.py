#!/usr/bin/env python3
"""Operate the product-neutral UBB lifecycle supervisor."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ubb_registry import RegistryError, load_registry
from ubb_supervisor import Supervisor, SupervisorError

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog"
DEFAULT_STATE = pathlib.Path("/var/lib/ultimate-bbs-box/supervisor")


def parser():
    main = argparse.ArgumentParser(description="Ultimate BBS Box lifecycle supervisor")
    main.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    main.add_argument("--state-dir", default=str(DEFAULT_STATE))
    main.add_argument("--json", action="store_true")
    commands = main.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status"); status.add_argument("service_id", nargs="?")
    for name in ("start", "restart"):
        command = commands.add_parser(name); command.add_argument("service_id")
    stop = commands.add_parser("stop"); stop.add_argument("service_id"); stop.add_argument("--force", action="store_true")
    maintenance = commands.add_parser("maintenance"); maintenance.add_argument("service_id"); maintenance.add_argument("job_id")
    commands.add_parser("reconcile"); commands.add_parser("tick")
    return main


def emit(value, as_json):
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(f"{item['service_id']}\t{item['state']}\tsessions={item['active_session_count']}\tholds={sum(item['holds'].values())}")
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        supervisor = Supervisor(load_registry(args.catalog), args.state_dir)
        if args.command == "status":
            value = supervisor.status(args.service_id) if args.service_id else supervisor.list_status()
        elif args.command == "start": value = supervisor.start(args.service_id)
        elif args.command == "stop": value = supervisor.stop(args.service_id, force=args.force)
        elif args.command == "restart": value = supervisor.restart(args.service_id)
        elif args.command == "maintenance": value = supervisor.run_maintenance(args.service_id, args.job_id)
        elif args.command == "reconcile": value = supervisor.reconcile()
        elif args.command == "tick": value = supervisor.tick()
        emit(value, args.json)
        return 0
    except (SupervisorError, RegistryError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
