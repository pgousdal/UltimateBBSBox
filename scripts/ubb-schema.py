#!/usr/bin/env python3
"""Validate Ultimate BBS Box catalog manifests against the v1 contracts."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = {
    "artifact": ROOT / "schemas" / "artifact-v1.schema.json",
    "endpoint": ROOT / "schemas" / "endpoint-v1.schema.json",
    "service": ROOT / "schemas" / "service-v1.schema.json",
    "integration": ROOT / "schemas" / "integration-v1.schema.json",
}


def load(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix.lower() == ".json":
            return json.load(fh)
        return yaml.safe_load(fh)


def validate(path: pathlib.Path) -> list[str]:
    try:
        document = load(path)
    except Exception as exc:  # user-facing validator
        return [f"cannot parse: {exc}"]
    if not isinstance(document, dict):
        return ["manifest root must be an object"]
    kind = document.get("kind")
    schema_path = SCHEMAS.get(kind)
    if schema_path is None:
        return [f"unknown kind {kind!r}; expected one of {', '.join(sorted(SCHEMAS))}"]
    schema = load(schema_path)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path))]


def manifest_paths(paths: list[str]) -> list[pathlib.Path]:
    if paths:
        return [pathlib.Path(p) for p in paths]
    return sorted((ROOT / "catalog").rglob("*.yml")) + sorted((ROOT / "catalog").rglob("*.yaml"))


def cross_reference_errors(paths: list[pathlib.Path]) -> list[str]:
    documents: list[tuple[pathlib.Path, dict]] = []
    errors: list[str] = []
    ids: dict[str, tuple[pathlib.Path, dict]] = {}
    for path in paths:
        try:
            document = load(path)
        except Exception:
            continue
        if not isinstance(document, dict) or not isinstance(document.get("id"), str):
            continue
        doc_id = document["id"]
        if doc_id in ids:
            errors.append(f"{path}: duplicate id {doc_id!r}; first declared in {ids[doc_id][0]}")
        else:
            ids[doc_id] = (path, document)
        documents.append((path, document))

    for path, document in documents:
        kind = document.get("kind")
        if kind == "service":
            endpoint_id = document.get("endpoint")
            target = ids.get(endpoint_id)
            if target is None:
                errors.append(f"{path}: endpoint {endpoint_id!r} is not declared")
            elif target[1].get("kind") != "endpoint":
                errors.append(f"{path}: endpoint {endpoint_id!r} does not reference an endpoint manifest")
            for bbs_id in document.get("exposure", {}).get("via_bbs", []):
                bbs = ids.get(bbs_id)
                if bbs is None:
                    errors.append(f"{path}: via_bbs target {bbs_id!r} is not declared")
                elif bbs[1].get("kind") != "service" or bbs[1].get("service", {}).get("type") != "bbs":
                    errors.append(f"{path}: via_bbs target {bbs_id!r} is not a BBS service")
        elif kind == "integration":
            target_id = document.get("target")
            target = ids.get(target_id)
            if target is None:
                errors.append(f"{path}: integration target {target_id!r} is not declared")
            elif target[1].get("kind") != "service":
                errors.append(f"{path}: integration target {target_id!r} is not a service manifest")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="manifest paths; defaults to catalog/**/*.yml")
    args = parser.parse_args()
    paths = manifest_paths(args.paths)
    if not paths:
        print("no manifests found", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        errors = validate(path)
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
