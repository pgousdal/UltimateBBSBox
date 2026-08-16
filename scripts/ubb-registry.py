#!/usr/bin/env python3
"""Inspect and validate the Ultimate BBS Box service registry."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ubb_registry import RegistryError, load_registry

DEFAULT_CATALOG = pathlib.Path(__file__).resolve().parents[1] / "catalog"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ultimate BBS Box service and endpoint registry")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="catalog root containing services/, endpoints/, integrations/")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    listing = commands.add_parser("list")
    listing.add_argument("--type", dest="service_type")
    exposure = listing.add_mutually_exclusive_group()
    exposure.add_argument("--main-menu", action="store_true")
    exposure.add_argument("--hidden", action="store_true")
    listing.add_argument("--via-bbs")
    listing.add_argument("--bbs-only", action="store_true")
    listing.add_argument("--endpoint-type", choices=("local_process", "tcp", "ssh", "serial", "remote_supervisor"))
    listing.add_argument("--runtime")
    show = commands.add_parser("show"); show.add_argument("service_id")
    commands.add_parser("endpoints")
    endpoint = commands.add_parser("endpoint"); endpoint.add_argument("endpoint_id")
    commands.add_parser("integrations")
    integration = commands.add_parser("integration"); integration.add_argument("integration_id")
    resolve = commands.add_parser("resolve"); resolve.add_argument("service_id")
    graph = commands.add_parser("graph"); graph.add_argument("service_id")
    return parser


def emit(value, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            if "service" in item:
                print(f"{item['id']}\t{item['service']['type']}\t{item['service']['title']}")
            else:
                print(f"{item['id']}\t{item.get('type', item.get('runtime', ''))}")
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_registry(args.catalog)
        if args.command == "validate":
            value = {"valid": True, "services": len(registry.services), "endpoints": len(registry.endpoints), "integrations": len(registry.integrations)}
            if args.json:
                emit(value, True)
            else:
                print(f"registry valid: {value['services']} services, {value['endpoints']} endpoints, {value['integrations']} integrations")
        elif args.command == "list":
            main_menu = True if args.main_menu else False if args.hidden else None
            services = registry.list_services(service_type=args.service_type, main_menu=main_menu,
                                                via_bbs=args.via_bbs, bbs_only=args.bbs_only,
                                                endpoint_type=args.endpoint_type, runtime=args.runtime)
            emit([service.to_dict() for service in services], args.json)
        elif args.command == "show": emit(registry.service(args.service_id).to_dict(), args.json)
        elif args.command == "endpoints": emit([item.to_dict() for item in registry.endpoints.values()], args.json)
        elif args.command == "endpoint": emit(registry.endpoint(args.endpoint_id).normalized(), args.json)
        elif args.command == "integrations": emit([item.to_dict() for item in registry.integrations.values()], args.json)
        elif args.command == "integration": emit(registry.integration(args.integration_id).to_dict(), args.json)
        elif args.command in ("resolve", "graph"):
            value = registry.resolve(args.service_id)
            if args.command == "graph" and not args.json:
                integration = value["integration"]["id"] if value["integration"] else "(none)"
                print(f"{value['service']['id']} -> {value['endpoint']['id']} -> {integration}")
            else:
                emit(value, args.json)
        return 0
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
