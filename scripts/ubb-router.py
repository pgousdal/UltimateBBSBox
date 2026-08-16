#!/usr/bin/env python3
"""Inspect M4 route exposure and authorization policy."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ubb_registry import RegistryError, load_registry
from ubb_router import RoutePolicy, RouteRequest, RouteType, RouterError

ROOT = pathlib.Path(__file__).resolve().parents[1]


def parser():
    main = argparse.ArgumentParser(description="Ultimate BBS Box session route policy")
    main.add_argument("--catalog", default=str(ROOT / "catalog"))
    main.add_argument("--json", action="store_true")
    commands = main.add_subparsers(dest="command", required=True)
    services = commands.add_parser("services"); services.add_argument("--direct", action="store_true")
    authorize = commands.add_parser("authorize"); authorize.add_argument("target"); authorize.add_argument("--via")
    return main


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        registry = load_registry(args.catalog)
        policy = RoutePolicy(registry)
        if args.command == "services":
            services = policy.list_direct_services() if args.direct else tuple(registry.services.values())
            value = [service.to_dict() for service in services]
            if args.json:
                print(json.dumps(value, indent=2, sort_keys=True))
            else:
                for service in services:
                    print(f"{service.id}\t{service.type}\t{service.title}")
        else:
            request = RouteRequest(args.target, RouteType.VIA_SERVICE if args.via else RouteType.DIRECT, args.via)
            value = policy.authorize(request)
            if args.json:
                print(json.dumps({"authorized": True, "route": value}, indent=2, sort_keys=True))
            else:
                route = "direct" if not args.via else f"via {args.via}"
                print(f"AUTHORIZED {args.target} {route} -> {value['endpoint']['id']} ({value['endpoint']['type']})")
        return 0
    except (RouterError, RegistryError) as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
