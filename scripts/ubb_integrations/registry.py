"""Deterministic registry of trusted repository integrations."""
from __future__ import annotations

from .errors import UnknownIntegrationError


class IntegrationRegistry:
    def __init__(self, integrations=()):
        self._items = {}
        for integration in integrations:
            if integration.id in self._items:
                raise ValueError(f"duplicate integration id: {integration.id}")
            self._items[integration.id] = integration

    @classmethod
    def defaults(cls):
        from integrations.bbs.mystic.integration import MysticLinuxIntegration
        return cls((MysticLinuxIntegration(),))

    def get(self, integration_id):
        try:
            return self._items[integration_id]
        except KeyError as exc:
            raise UnknownIntegrationError(f"unknown integration: {integration_id}") from exc

    def list(self):
        return [self._items[key] for key in sorted(self._items)]

