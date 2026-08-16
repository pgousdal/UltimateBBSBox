"""Shared safe loading and JSON Schema validation for UBB manifests."""
from __future__ import annotations

import json
import pathlib

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = {
    "artifact": ROOT / "schemas" / "artifact-v1.schema.json",
    "endpoint": ROOT / "schemas" / "endpoint-v1.schema.json",
    "service": ROOT / "schemas" / "service-v1.schema.json",
    "integration": ROOT / "schemas" / "integration-v1.schema.json",
}


def load_document(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            return json.load(handle)
        return yaml.safe_load(handle)


def validation_errors(path: pathlib.Path) -> list[str]:
    try:
        document = load_document(path)
    except Exception as exc:
        return [f"cannot parse: {exc}"]
    if not isinstance(document, dict):
        return ["manifest root must be an object"]
    kind = document.get("kind")
    schema_path = SCHEMAS.get(kind)
    if schema_path is None:
        return [f"unknown kind {kind!r}; expected one of {', '.join(sorted(SCHEMAS))}"]
    schema = load_document(schema_path)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(document), key=lambda error: list(error.path))]


def catalog_paths(root: pathlib.Path = ROOT / "catalog") -> list[pathlib.Path]:
    return sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml"))


def cross_reference_errors(paths: list[pathlib.Path]) -> list[str]:
    documents: list[tuple[pathlib.Path, dict]] = []
    errors: list[str] = []
    ids_by_kind: dict[str, dict[str, tuple[pathlib.Path, dict]]] = {}
    for path in paths:
        try:
            document = load_document(path)
        except Exception:
            continue
        if not isinstance(document, dict) or not isinstance(document.get("id"), str):
            continue
        kind = document.get("kind")
        kind_ids = ids_by_kind.setdefault(str(kind), {})
        document_id = document["id"]
        if document_id in kind_ids:
            errors.append(f"{path}: duplicate {kind} id {document_id!r}; first declared in {kind_ids[document_id][0]}")
        else:
            kind_ids[document_id] = (path, document)
        documents.append((path, document))

    services = ids_by_kind.get("service", {})
    endpoints = ids_by_kind.get("endpoint", {})
    integrations = ids_by_kind.get("integration", {})
    for path, document in documents:
        kind = document.get("kind")
        if kind == "service":
            endpoint_id = document.get("endpoint")
            if endpoint_id not in endpoints:
                errors.append(f"{path}: endpoint {endpoint_id!r} is not declared")
            integration_id = document.get("integration")
            if integration_id:
                integration = integrations.get(integration_id)
                if integration is None:
                    errors.append(f"{path}: integration {integration_id!r} is not declared")
                elif integration[1].get("target") != document.get("id"):
                    errors.append(f"{path}: integration {integration_id!r} targets {integration[1].get('target')!r}, not this service")
            for bbs_id in document.get("exposure", {}).get("via_bbs", []):
                bbs = services.get(bbs_id)
                if bbs is None:
                    errors.append(f"{path}: via_bbs target {bbs_id!r} is not declared")
                elif bbs[1].get("service", {}).get("type") != "bbs":
                    errors.append(f"{path}: via_bbs target {bbs_id!r} is not a BBS service")
        elif kind == "integration":
            target_id = document.get("target")
            if target_id not in services:
                errors.append(f"{path}: integration target {target_id!r} is not a declared service")
    return errors
