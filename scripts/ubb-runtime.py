#!/usr/bin/env python3
"""Inspect built-in M5 runtime adapters and service configuration."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

from ubb_registry import RegistryError, load_registry
from ubb_runtime import RuntimeAdapterError, RuntimeAdapterRegistry, RuntimeManager

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ultimate BBS Box runtime adapter diagnostics")
    parser.add_argument("--catalog", default=str(ROOT / "catalog")); parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-adapters")
    validate = commands.add_parser("validate"); validate.add_argument("service_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "list-adapters":
            value = RuntimeAdapterRegistry.defaults().describe()
        else:
            registry = load_registry(args.catalog)
            with tempfile.TemporaryDirectory(prefix="ubb-runtime-validation-") as temporary:
                value = RuntimeManager(registry, temporary).validate(args.service_id)
        if args.json: print(json.dumps(value, indent=2, sort_keys=True))
        elif isinstance(value, list):
            for item in value: print(f"{item['runtime']}\t{'supported' if item['supported'] else 'deferred'}\t{item['adapter']}")
        else: print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except (RuntimeAdapterError, RegistryError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
