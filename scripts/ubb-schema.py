#!/usr/bin/env python3
"""Validate Ultimate BBS Box catalog manifests against the v1 contracts."""
from __future__ import annotations

import argparse
import pathlib
import sys

from ubb_schema import ROOT, catalog_paths, cross_reference_errors, validation_errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="manifest paths; defaults to catalog/**/*.yml")
    args = parser.parse_args()
    paths = [pathlib.Path(item) for item in args.paths] if args.paths else catalog_paths()
    if not paths:
        print("no manifests found", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        errors = validation_errors(path)
        if errors:
            failed = True
            for error in errors:
                print(f"FAIL {path}: {error}")
        else:
            print(f"PASS {path}")
    if not failed and not args.paths:
        for error in cross_reference_errors(paths):
            failed = True
            print(f"FAIL {error}")
        if not failed:
            print("PASS catalog cross-references")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
