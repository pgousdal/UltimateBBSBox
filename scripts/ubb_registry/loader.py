"""Deterministic loader for repository YAML registry manifests."""
from __future__ import annotations

import pathlib

from ubb_schema import load_document, validation_errors

from .errors import DuplicateIdError, InvalidManifestError, UnknownReferenceError
from .models import Endpoint, Integration, Service
from .registry import Registry

KIND_DIRECTORIES = {"service": "services", "endpoint": "endpoints", "integration": "integrations"}
MODEL_TYPES = {"service": Service, "endpoint": Endpoint, "integration": Integration}


def _paths(root: pathlib.Path) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for directory in KIND_DIRECTORIES.values():
        location = root / directory
        paths.extend(location.rglob("*.yml"))
        paths.extend(location.rglob("*.yaml"))
    return sorted(paths)


def load_registry(root: pathlib.Path | str) -> Registry:
    root = pathlib.Path(root).resolve()
    indexes: dict[str, dict] = {kind: {} for kind in KIND_DIRECTORIES}
    paths = _paths(root)
    if not paths:
        raise InvalidManifestError(f"no registry manifests found beneath {root}")
    for path in paths:
        errors = validation_errors(path)
        if errors:
            raise InvalidManifestError(f"{path}: {'; '.join(errors)}")
        document = load_document(path)
        kind = document["kind"]
        if kind not in indexes:
            raise InvalidManifestError(f"{path}: {kind!r} is not a registry kind")
        expected_directory = KIND_DIRECTORIES[kind]
        if root / expected_directory not in path.parents:
            raise InvalidManifestError(f"{path}: {kind} belongs under {expected_directory}/")
        document_id = document["id"]
        if document_id in indexes[kind]:
            first = indexes[kind][document_id].source
            raise DuplicateIdError(f"duplicate {kind} id {document_id!r}: {first} and {path}")
        indexes[kind][document_id] = MODEL_TYPES[kind](document_id, document, path)
    registry = Registry.create(indexes["service"], indexes["endpoint"], indexes["integration"])
    _validate_references(registry)
    return registry


def _validate_references(registry: Registry) -> None:
    for service in registry.services.values():
        if service.endpoint_id not in registry.endpoints:
            raise UnknownReferenceError(f"service {service.id!r} references unknown endpoint {service.endpoint_id!r}")
        if service.integration_id:
            if service.integration_id not in registry.integrations:
                raise UnknownReferenceError(f"service {service.id!r} references unknown integration {service.integration_id!r}")
            integration = registry.integrations[service.integration_id]
            if integration.target != service.id:
                raise UnknownReferenceError(f"service {service.id!r} references integration {integration.id!r} targeting {integration.target!r}")
        for bbs_id in service.document["exposure"].get("via_bbs", []):
            bbs = registry.services.get(bbs_id)
            if bbs is None:
                raise UnknownReferenceError(f"service {service.id!r} has unknown via_bbs reference {bbs_id!r}")
            if bbs.type != "bbs":
                raise UnknownReferenceError(f"service {service.id!r} via_bbs reference {bbs_id!r} is not a BBS")
    for integration in registry.integrations.values():
        if integration.target not in registry.services:
            raise UnknownReferenceError(f"integration {integration.id!r} targets unknown service {integration.target!r}")
