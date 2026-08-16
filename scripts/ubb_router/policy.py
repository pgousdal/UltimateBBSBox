"""Exposure and route-path authorization."""
from __future__ import annotations

from ubb_registry import Registry
from ubb_registry.errors import UnknownReferenceError

from .errors import AuthorizationError, UnknownServiceError
from .models import RouteRequest, RouteType


class RoutePolicy:
    def __init__(self, registry: Registry):
        self.registry = registry

    def list_direct_services(self):
        result = []
        for service in self.registry.services.values():
            exposure = service.document["exposure"]
            access = service.document.get("access", {})
            if exposure["main_menu"] and access.get("direct_allowed", True) and not exposure.get("admin_only", False):
                result.append(service)
        return tuple(result)

    def authorize(self, request: RouteRequest) -> dict:
        try:
            service = self.registry.service(request.target_service)
        except UnknownReferenceError as exc:
            raise UnknownServiceError(f"unknown target service: {request.target_service}") from exc
        exposure = service.document["exposure"]
        access = service.document.get("access", {})
        if exposure.get("admin_only", False):
            raise AuthorizationError(f"service {service.id} requires an administrative assertion not implemented in M4")
        if request.route_type == RouteType.DIRECT:
            if request.origin_service is not None:
                raise AuthorizationError("direct routes cannot declare an origin service")
            if not exposure["main_menu"] or not access.get("direct_allowed", True):
                raise AuthorizationError(f"direct route denied for service {service.id}")
        elif request.route_type == RouteType.VIA_SERVICE:
            if not request.origin_service:
                raise AuthorizationError("via_service routes require an origin service")
            try:
                self.registry.service(request.origin_service)
            except UnknownReferenceError as exc:
                raise UnknownServiceError(f"unknown origin service: {request.origin_service}") from exc
            if request.origin_service not in exposure.get("via_bbs", []):
                raise AuthorizationError(f"route to {service.id} is not allowed via {request.origin_service}")
        else:
            raise AuthorizationError(f"unsupported route type: {request.route_type}")
        return self.registry.resolve(service.id)
