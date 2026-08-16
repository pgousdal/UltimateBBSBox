"""Provider-neutral public edge and secure-overlay configuration.

This module describes intent only.  It never establishes tunnels, opens firewall
ports, or contacts a provider.  Provider adapters can consume the validated
model in a later deployment layer.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

EDGE_PROVIDERS = ("headscale", "tailscale", "wireguard", "zerotier", "nebula")
SUPPORT_LEVELS = {"recommended", "supported", "human_required", "unsupported"}
PROVIDER_SUPPORT = {
    "headscale": "recommended", "tailscale": "supported", "wireguard": "supported",
    "zerotier": "supported", "nebula": "supported",
}
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class EdgeConfigError(ValueError):
    pass


def _id(value: str, label: str = "identifier") -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise EdgeConfigError(f"invalid {label}")
    return value


def _hostname(value: str) -> str:
    if not isinstance(value, str) or len(value.rstrip(".")) > 253:
        raise EdgeConfigError("invalid hostname")
    value = value.lower().rstrip(".")
    if not value or any(not _LABEL.fullmatch(part) for part in value.split(".")):
        raise EdgeConfigError("invalid hostname")
    return value


def _ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise EdgeConfigError("invalid IP address") from exc


def _cidr(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError as exc:
        raise EdgeConfigError("invalid CIDR") from exc


def _port(value: int) -> int:
    if not isinstance(value, int) or not 1 <= value <= 65535:
        raise EdgeConfigError("invalid port")
    return value


@dataclass(frozen=True)
class OverlayNode:
    node_id: str
    role: str
    addresses: tuple[str, ...] = ()
    public_ipv4: str | None = None
    public_ipv6: str | None = None
    hostname: str | None = None
    capabilities: tuple[str, ...] = ()

    def __post_init__(self):
        _id(self.node_id, "node id")
        if self.role not in ("edge", "site", "client"):
            raise EdgeConfigError("invalid node role")
        object.__setattr__(self, "addresses", tuple(_ip(x) for x in self.addresses))
        if self.public_ipv4 is not None:
            try: version = ipaddress.ip_address(self.public_ipv4).version
            except ValueError as exc: raise EdgeConfigError("invalid public_ipv4") from exc
            if version != 4: raise EdgeConfigError("public_ipv4 must be IPv4")
        if self.public_ipv6 is not None:
            try: version = ipaddress.ip_address(self.public_ipv6).version
            except ValueError as exc: raise EdgeConfigError("invalid public_ipv6") from exc
            if version != 6: raise EdgeConfigError("public_ipv6 must be IPv6")
        if self.hostname:
            object.__setattr__(self, "hostname", _hostname(self.hostname))


@dataclass(frozen=True)
class PrivateSite:
    site_id: str
    node_id: str
    private_cidrs: tuple[str, ...] = ()
    reachable_services: tuple[str, ...] = ()
    dns_identity: str | None = None

    def __post_init__(self):
        _id(self.site_id, "site id"); _id(self.node_id, "node id")
        object.__setattr__(self, "private_cidrs", tuple(_cidr(x) for x in self.private_cidrs))
        if self.dns_identity:
            object.__setattr__(self, "dns_identity", _hostname(self.dns_identity))


@dataclass(frozen=True)
class PublicIdentity:
    hostname: str
    target: str
    enabled: bool = True

    def __post_init__(self):
        object.__setattr__(self, "hostname", _hostname(self.hostname)); _id(self.target, "identity target")


@dataclass(frozen=True)
class Ingress:
    ingress_id: str
    protocol: str
    public_port: int
    target_service: str
    target_port: int
    public_address: str | None = None
    target_host: str | None = None
    hostname: str | None = None
    enabled: bool = True

    def __post_init__(self):
        _id(self.ingress_id, "ingress id")
        if self.protocol not in ("tcp", "udp", "http", "https"):
            raise EdgeConfigError("invalid ingress protocol")
        _port(self.public_port); _port(self.target_port); _id(self.target_service, "target service")
        if self.public_address:
            object.__setattr__(self, "public_address", _ip(self.public_address))
        if self.target_host:
            object.__setattr__(self, "target_host", _ip(self.target_host))
        if self.hostname:
            object.__setattr__(self, "hostname", _hostname(self.hostname))
        if self.protocol in ("tcp", "udp") and self.hostname:
            # Raw streams do not carry the DNS name used by the caller.
            raise EdgeConfigError("hostname routing is only valid for HTTP/HTTPS ingress")


@dataclass(frozen=True)
class Route:
    source: str
    destination_cidr: str
    approved: bool = False
    exit_node: bool = False

    def __post_init__(self):
        _id(self.source, "route source"); object.__setattr__(self, "destination_cidr", _cidr(self.destination_cidr))
        if self.exit_node:
            raise EdgeConfigError("exit-node routes are disabled")


@dataclass(frozen=True)
class EdgeConfig:
    provider: str = "headscale"
    edge_node: OverlayNode = field(default_factory=lambda: OverlayNode("edge-1", "edge"))
    sites: tuple[PrivateSite, ...] = ()
    public_identities: tuple[PublicIdentity, ...] = ()
    ingress: tuple[Ingress, ...] = ()
    routes: tuple[Route, ...] = ()
    derp_enabled: bool = False
    secret_refs: tuple[str, ...] = ()

    def __post_init__(self):
        if self.provider not in EDGE_PROVIDERS: raise EdgeConfigError("unknown overlay provider")
        if not isinstance(self.edge_node, OverlayNode) or self.edge_node.role != "edge": raise EdgeConfigError("edge_node must have edge role")
        sites = {x.site_id for x in self.sites}; ids = {x.node_id for x in self.sites}
        if len(sites) != len(self.sites): raise EdgeConfigError("duplicate private site")
        if len(ids) != len(self.sites): raise EdgeConfigError("duplicate site node")
        names = [x.hostname for x in self.public_identities]
        if len(names) != len(set(names)): raise EdgeConfigError("duplicate public identity")
        services = {service for site in self.sites for service in site.reachable_services}
        for item in self.public_identities:
            if item.target not in (self.edge_node.node_id, *services):
                raise EdgeConfigError("public identity target is not declared")
        seen = []
        for item in self.ingress:
            if item.target_service not in services and item.target_service != self.edge_node.node_id:
                raise EdgeConfigError("ingress target service is not declared")
            key = (item.protocol, item.public_address or "*", item.public_port)
            for old in seen:
                if key == old:
                    raise EdgeConfigError("conflicting public ingress listener")
            seen.append(key)
        for ref in self.secret_refs:
            if not isinstance(ref, str) or not ref or ref.startswith("/") is False:
                raise EdgeConfigError("secret references must be absolute external paths")

    @property
    def support_level(self) -> str:
        return PROVIDER_SUPPORT[self.provider]

    def to_dict(self) -> dict:
        return {
            "provider": self.provider, "support_level": self.support_level,
            "edge_node": {"id": self.edge_node.node_id, "role": self.edge_node.role, "addresses": list(self.edge_node.addresses), "hostname": self.edge_node.hostname},
            "sites": [{"id": x.site_id, "node": x.node_id, "cidrs": list(x.private_cidrs), "services": list(x.reachable_services)} for x in self.sites],
            "public_identities": [{"hostname": x.hostname, "target": x.target, "enabled": x.enabled} for x in self.public_identities],
            "ingress": [{"id": x.ingress_id, "protocol": x.protocol, "address": x.public_address, "port": x.public_port, "target": x.target_service, "target_port": x.target_port} for x in self.ingress],
            "routes": [{"source": x.source, "destination": x.destination_cidr, "approved": x.approved} for x in self.routes],
            "derp": {"enabled": self.derp_enabled},
            "secret_refs": list(self.secret_refs),
        }
