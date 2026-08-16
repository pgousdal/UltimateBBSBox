"""M2 configuration, M3 driver, and M4 stream bridges."""
from __future__ import annotations

import pathlib

from .errors import RuntimeConfigError
from .registry import RuntimeAdapterRegistry


class RuntimeDriverBridge:
    def __init__(self, adapter, config):
        self.adapter = adapter; self.config = config

    def start(self, instance, declaration):
        self.adapter.prepare(instance, self.config)
        return self.adapter.start(instance, self.config).to_dict()

    def stop(self, instance, declaration): return self.adapter.stop(instance, self.config).to_dict()
    def status(self, instance, declaration): return self.adapter.status(instance, self.config).to_dict()
    def is_ready(self, instance, declaration, readiness):
        return self.adapter.readiness(instance, self.config, readiness).ready
    def run_maintenance(self, instance, declaration, job):
        return self.adapter.run_maintenance(instance, self.config, job)


class RuntimeManager:
    def __init__(self, registry, state_dir, adapters=None):
        self.registry = registry
        self.state_dir = pathlib.Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.adapters = adapters or RuntimeAdapterRegistry.defaults()
        self._drivers = {}

    def configuration(self, service_id):
        service = self.registry.service(service_id)
        endpoint = self.registry.endpoint(service.endpoint_id).normalized()
        if service.integration_id:
            integration = self.registry.integration(service.integration_id)
            runtime = integration.runtime
            config = dict(integration.document.get("runtime_config", {}))
        elif endpoint["type"] == "local_process":
            runtime = "native"
            command = endpoint.get("command", [])
            config = {"executable": command[0], "argv": command[1:]} if command else {}
        else:
            raise RuntimeConfigError(f"service {service_id} has no runtime integration")
        if runtime == "native" and not config and endpoint["type"] == "local_process":
            command = endpoint.get("command", [])
            config = {"executable": command[0], "argv": command[1:]} if command else {}
        return runtime, config

    def adapter_for(self, service_id):
        runtime, _ = self.configuration(service_id)
        return self.adapters.get(runtime)

    def driver_for(self, service):
        if service.id not in self._drivers:
            runtime, config = self.configuration(service.id)
            self._drivers[service.id] = RuntimeDriverBridge(self.adapters.get(runtime), config)
        return self._drivers[service.id]

    def validate(self, service_id):
        runtime, config = self.configuration(service_id)
        adapter = self.adapters.get(runtime)
        if hasattr(adapter, "validate_config"):
            adapter.validate_config(config)
        return {"service_id": service_id, "runtime": runtime,
                "adapter": type(adapter).__name__, "runtime_config": _redacted_config(config)}

    def open_stream(self, service_id, instance):
        runtime, config = self.configuration(service_id)
        return self.adapters.get(runtime).open_stream(instance, config)


class RuntimeStreamResolver:
    def __init__(self, manager, supervisor): self.manager = manager; self.supervisor = supervisor
    def __call__(self, service_id):
        return self.manager.open_stream(service_id, self.supervisor.instances[service_id])


def _redacted_config(config):
    value = dict(config)
    if "environment" in value:
        value["environment"] = {key: "<redacted>" for key in value["environment"]}
    return value
