import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ubb_registry import (DuplicateIdError, InvalidManifestError,
                          UnknownReferenceError, load_registry)  # noqa: E402


def endpoint(endpoint_id="ep-local", endpoint_type="tcp"):
    value = {"kind": "endpoint", "schema_version": 1, "id": endpoint_id, "type": endpoint_type}
    if endpoint_type == "tcp":
        value.update(host="127.0.0.1", port=2323, protocol="telnet")
    elif endpoint_type == "local_process":
        value["command"] = ["/usr/bin/example"]
    elif endpoint_type == "ssh":
        value.update(host="shell.internal", port=22, protocol="ssh")
    elif endpoint_type == "serial":
        value.update(device="/dev/ttyS0", baud=9600, protocol="serial")
    elif endpoint_type in ("supervisor", "remote_supervisor"):
        value.update(host="museum.internal", remote_service_id="remote-target", protocol="supervisor")
    return value


def service(service_id="alpha-bbs", endpoint_id="ep-local", service_type="bbs", integration_id="alpha-integration",
            main_menu=True, via_bbs=None):
    value = {
        "kind": "service", "schema_version": 1, "id": service_id,
        "service": {"type": service_type, "title": service_id.title()},
        "endpoint": endpoint_id,
        "exposure": {"main_menu": main_menu, "via_bbs": via_bbs or []},
        "lifecycle": {"mode": "on_demand", "sharing": "multiuser"},
    }
    if integration_id:
        value["integration"] = integration_id
    return value


def integration(integration_id="alpha-integration", target="alpha-bbs", runtime="native"):
    return {
        "kind": "integration", "schema_version": 1, "id": integration_id,
        "target": target, "automation_level": "assisted", "runtime": runtime,
        "installation": {"steps": [{"type": "manual", "instruction": "fixture only"}]},
        "qualification": {"checks": []},
    }


class RegistryFixture:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        for name in ("services", "endpoints", "integrations"):
            (self.root / name).mkdir(parents=True)

    def write(self, directory, name, document):
        path = self.root / directory / name
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def valid(self):
        self.write("endpoints", "local.yml", endpoint())
        self.write("endpoints", "remote.yml", endpoint("ep-remote", "remote_supervisor"))
        self.write("services", "alpha.yml", service())
        self.write("services", "remote.yml", service("remote-shell", "ep-remote", "shell", None, False, ["alpha-bbs"]))
        self.write("integrations", "alpha.yml", integration())


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = RegistryFixture(pathlib.Path(self.temp.name) / "catalog")
        self.fixture.valid()

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        return load_registry(self.fixture.root)

    def test_load_and_lookup_each_kind(self):
        registry = self.load()
        self.assertEqual(registry.service("alpha-bbs").title, "Alpha-Bbs")
        self.assertEqual(registry.endpoint("ep-local").type, "tcp")
        self.assertEqual(registry.integration("alpha-integration").runtime, "native")

    def test_service_resolves_endpoint_and_integration(self):
        value = self.load().resolve("alpha-bbs")
        self.assertEqual(value["endpoint"]["id"], "ep-local")
        self.assertEqual(value["endpoint"]["location"], "local")
        self.assertEqual(value["integration"]["id"], "alpha-integration")

    def test_remote_endpoint_resolution_without_integration(self):
        value = self.load().resolve("remote-shell")
        self.assertEqual(value["endpoint"]["type"], "remote_supervisor")
        self.assertEqual(value["endpoint"]["location"], "remote")
        self.assertEqual(value["endpoint"]["remote_service_id"], "remote-target")
        self.assertIsNone(value["integration"])

    def test_all_endpoint_types_are_metadata(self):
        for endpoint_type in ("local_process", "ssh", "serial"):
            self.fixture.write("endpoints", f"{endpoint_type}.yml", endpoint(f"ep-{endpoint_type}", endpoint_type))
        registry = self.load()
        self.assertEqual(registry.endpoint("ep-local_process").normalized()["location"], "local")
        self.assertEqual(registry.endpoint("ep-ssh").normalized()["location"], "remote")
        self.assertEqual(registry.endpoint("ep-serial").normalized()["type"], "serial")
        self.assertEqual(registry.endpoint("ep-local").normalized()["type"], "tcp")

    def test_service_filters(self):
        registry = self.load()
        self.assertEqual([item.id for item in registry.list_services(service_type="bbs")], ["alpha-bbs"])
        self.assertEqual([item.id for item in registry.list_services(main_menu=True)], ["alpha-bbs"])
        self.assertEqual([item.id for item in registry.list_services(main_menu=False)], ["remote-shell"])
        self.assertEqual([item.id for item in registry.list_services(via_bbs="alpha-bbs")], ["remote-shell"])
        self.assertEqual([item.id for item in registry.list_services(bbs_only=True)], ["remote-shell"])
        self.assertEqual([item.id for item in registry.list_services(endpoint_type="remote_supervisor")], ["remote-shell"])
        self.assertEqual([item.id for item in registry.list_services(runtime="native")], ["alpha-bbs"])

    def test_duplicate_service_id_rejected(self):
        self.fixture.write("services", "duplicate.yml", service())
        with self.assertRaises(DuplicateIdError): self.load()

    def test_duplicate_endpoint_id_rejected(self):
        self.fixture.write("endpoints", "duplicate.yml", endpoint())
        with self.assertRaises(DuplicateIdError): self.load()

    def test_duplicate_integration_id_rejected(self):
        self.fixture.write("integrations", "duplicate.yml", integration())
        with self.assertRaises(DuplicateIdError): self.load()

    def test_unknown_endpoint_reference(self):
        self.fixture.write("services", "alpha.yml", service(endpoint_id="missing"))
        with self.assertRaises(UnknownReferenceError): self.load()

    def test_unknown_integration_reference(self):
        self.fixture.write("services", "alpha.yml", service(integration_id="missing"))
        with self.assertRaises(UnknownReferenceError): self.load()

    def test_integration_unknown_target(self):
        self.fixture.write("integrations", "alpha.yml", integration(target="missing"))
        with self.assertRaises(UnknownReferenceError): self.load()

    def test_malformed_service_manifest(self):
        value = service(); value["service"]["type"] = "not-a-service"
        self.fixture.write("services", "alpha.yml", value)
        with self.assertRaises(InvalidManifestError): self.load()

    def test_malformed_endpoint_manifest(self):
        value = endpoint(); value["port"] = 70000
        self.fixture.write("endpoints", "local.yml", value)
        with self.assertRaises(InvalidManifestError): self.load()

    def test_malformed_integration_manifest(self):
        self.fixture.write("integrations", "alpha.yml", integration(runtime="made_up"))
        with self.assertRaises(InvalidManifestError): self.load()

    def test_unsupported_schema_version(self):
        value = service(); value["schema_version"] = 2
        self.fixture.write("services", "alpha.yml", value)
        with self.assertRaises(InvalidManifestError): self.load()

    def test_deterministic_ordering(self):
        self.fixture.write("services", "zero.yml", service("zero-other", "ep-local", "other", None))
        self.assertEqual(list(self.load().services), ["alpha-bbs", "remote-shell", "zero-other"])

    def test_json_cli_resolve(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/ubb-registry.py"), "--catalog", str(self.fixture.root), "--json", "resolve", "remote-shell"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["service"]["id"], "remote-shell")
        self.assertEqual(value["endpoint"]["type"], "remote_supervisor")

    def test_production_registry_loads(self):
        registry = load_registry(ROOT / "catalog")
        self.assertEqual(registry.resolve("mystic-main")["integration"]["id"], "mystic-linux")
        self.assertEqual(registry.resolve("unix-v7-shell")["endpoint"]["location"], "remote")


if __name__ == "__main__":
    unittest.main()
