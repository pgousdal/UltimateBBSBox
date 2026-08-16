"""Indexed, deterministic, read-only registry queries."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .errors import UnknownReferenceError, UnsupportedEndpointTypeError
from .models import Endpoint, Integration, Service

ENDPOINT_TYPES = frozenset(("local_process", "tcp", "udp", "ssh", "serial", "supervisor", "remote_supervisor"))


@dataclass(frozen=True)
class Registry:
    services: Mapping[str, Service]
    endpoints: Mapping[str, Endpoint]
    integrations: Mapping[str, Integration]

    @classmethod
    def create(cls, services: dict[str, Service], endpoints: dict[str, Endpoint], integrations: dict[str, Integration]) -> "Registry":
        return cls(MappingProxyType(dict(sorted(services.items()))),
                   MappingProxyType(dict(sorted(endpoints.items()))),
                   MappingProxyType(dict(sorted(integrations.items()))))

    def service(self, service_id: str) -> Service:
        try:
            return self.services[service_id]
        except KeyError as exc:
            raise UnknownReferenceError(f"unknown service: {service_id}") from exc

    def endpoint(self, endpoint_id: str) -> Endpoint:
        try:
            endpoint = self.endpoints[endpoint_id]
        except KeyError as exc:
            raise UnknownReferenceError(f"unknown endpoint: {endpoint_id}") from exc
        if endpoint.type not in ENDPOINT_TYPES:
            raise UnsupportedEndpointTypeError(f"unsupported endpoint type: {endpoint.type}")
        return endpoint

    def integration(self, integration_id: str) -> Integration:
        try:
            return self.integrations[integration_id]
        except KeyError as exc:
            raise UnknownReferenceError(f"unknown integration: {integration_id}") from exc

    def list_services(self, *, service_type: str | None = None, main_menu: bool | None = None,
                      via_bbs: str | None = None, bbs_only: bool = False,
                      endpoint_type: str | None = None, runtime: str | None = None) -> tuple[Service, ...]:
        values = []
        for service in self.services.values():
            exposure = service.document["exposure"]
            endpoint = self.endpoint(service.endpoint_id)
            integration = self.integration(service.integration_id) if service.integration_id else None
            if service_type and service.type != service_type:
                continue
            if main_menu is not None and exposure["main_menu"] is not main_menu:
                continue
            if via_bbs and via_bbs not in exposure.get("via_bbs", []):
                continue
            if bbs_only and (exposure["main_menu"] or not exposure.get("via_bbs")):
                continue
            normalized_type = endpoint.normalized()["type"]
            if endpoint_type and normalized_type != endpoint_type:
                continue
            if runtime and (integration is None or integration.runtime != runtime):
                continue
            values.append(service)
        return tuple(values)

    def resolve(self, service_id: str) -> dict:
        service = self.service(service_id)
        endpoint = self.endpoint(service.endpoint_id)
        integration = self.integration(service.integration_id) if service.integration_id else None
        return {
            "service": service.to_dict(),
            "endpoint": endpoint.normalized(),
            "integration": integration.to_dict() if integration else None,
        }
