import hashlib
import io
import json
import pathlib
import socket
import shutil
import sys
import tarfile
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import ubb_archive as archive  # noqa: E402
from integrations.bbs.mystic.integration import MysticLinuxIntegration  # noqa: E402
from ubb_integrations import (ArtifactRequiredError, IntegrationRegistry, QualificationStatus,
                              UnknownIntegrationError, assert_preservation_first,
                              prohibited_downloads)  # noqa: E402
from ubb_registry import load_registry  # noqa: E402
from ubb_router import MemoryConnector, RouteRequest, Router  # noqa: E402
from ubb_runtime import RuntimeManager  # noqa: E402
from ubb_supervisor import FakeClock, FakeDriver, Supervisor  # noqa: E402


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = pathlib.Path(self.temp.name)
        self.archive_root = self.base / "archive"; archive.init_archive(self.archive_root)
        self.install_root = self.base / "mystic"
        self.integration = MysticLinuxIntegration()
        self.distribution = self.base / self.integration.original_filename
        with tarfile.open(self.distribution, "w:gz") as bundle:
            for name, content, mode in (("mystic/mis", b"#!/bin/sh\n", 0o755),
                                        ("mystic/data/default.dat", b"default", 0o644),
                                        ("mystic/text/welcome.txt", b"welcome", 0o644)):
                info = tarfile.TarInfo(name); info.size = len(content); info.mode = mode
                bundle.addfile(info, io.BytesIO(content))

    def tearDown(self): self.temp.cleanup()

    def acquire(self, artifact_id="mystic-fixture"):
        return self.integration.acquire(self.archive_root, local_file=self.distribution, artifact_id=artifact_id)

    def test_discovery_lookup_unknown_and_assisted_contract(self):
        registry = IntegrationRegistry.defaults()
        self.assertEqual([item.id for item in registry.list()], ["abbs-amiga", "mystic-linux"])
        self.assertEqual(registry.get("mystic-linux").runtime, "native")
        self.assertEqual(registry.get("mystic-linux").automation_level, "assisted")
        with self.assertRaises(UnknownIntegrationError): registry.get("not-known")

    def test_production_registry_relationship_and_native_runtime(self):
        registry = load_registry(ROOT / "catalog")
        resolved = registry.resolve("mystic-main")
        self.assertEqual(resolved["endpoint"]["id"], "mystic-local")
        self.assertEqual(resolved["integration"]["id"], "mystic-linux")
        runtime, config = RuntimeManager(registry, self.base / "runtime").configuration("mystic-main")
        self.assertEqual(runtime, "native"); self.assertEqual(config["stream"]["type"], "tcp")
        self.assertEqual(config["readiness"]["type"], "tcp_port")

    def test_acquisition_uses_m1_and_rights_are_conservative(self):
        value = self.acquire()
        self.assertEqual(value, archive.verify_one(self.archive_root, "mystic-fixture"))
        self.assertEqual(value["artifact"]["sha256"], hashlib.sha256(self.distribution.read_bytes()).hexdigest())
        self.assertEqual(value["provenance"]["source_url"], self.integration.source_url)
        self.assertTrue(value["rights"]["install_locally"])
        self.assertFalse(value["rights"]["redistribute_original"])
        self.assertFalse(value["rights"]["publish_to_bbs_filebase"])

    def test_installer_requires_verified_preserved_artifact(self):
        with self.assertRaises(archive.ArchiveError):
            self.integration.install(self.archive_root, "not-preserved", self.install_root)
        value = self.acquire(); object_path = archive.object_path(self.archive_root, value["artifact"]["sha256"])
        object_path.chmod(0o644); object_path.write_bytes(b"tampered")
        with self.assertRaises(archive.VerificationError):
            self.integration.install(self.archive_root, "mystic-fixture", self.install_root)

    def test_install_uses_object_is_idempotent_and_preserves_live_state(self):
        value = self.acquire(); object_path = archive.object_path(self.archive_root, value["artifact"]["sha256"])
        original = object_path.read_bytes()
        first = self.integration.install(self.archive_root, "mystic-fixture", self.install_root)
        self.assertTrue(first.changed); self.assertEqual(object_path.read_bytes(), original)
        live = self.install_root / "live/data/operator-state.dat"; live.write_text("living")
        second = self.integration.install(self.archive_root, "mystic-fixture", self.install_root)
        self.assertFalse(second.changed); self.assertEqual(live.read_text(), "living")
        self.assertTrue((self.install_root / "software/current/data").is_symlink())
        self.assertEqual((self.install_root / "software/current/data/operator-state.dat").read_text(), "living")

    def test_manual_evidence_and_qualification_states(self):
        self.acquire(); self.integration.install(self.archive_root, "mystic-fixture", self.install_root)
        pending = self.integration.configure(self.install_root)
        self.assertEqual(pending.status, QualificationStatus.HUMAN_REQUIRED)
        passed = self.integration.configure(self.install_root, self.integration.manual_evidence)
        self.assertEqual(passed.status, QualificationStatus.PASS)
        results = self.integration.qualify(self.archive_root, "mystic-fixture", self.install_root,
                                           runtime_ready=True, route_open=True, clean_stop=True,
                                           live_state_survived=True)
        statuses = {item.check: item.status for item in results}
        self.assertEqual(statuses["artifact_verified"], QualificationStatus.PASS)
        self.assertEqual(statuses["login_menu"], QualificationStatus.HUMAN_REQUIRED)

    def test_qualification_fails_closed_on_tampering(self):
        value = self.acquire(); self.integration.install(self.archive_root, "mystic-fixture", self.install_root)
        obj = archive.object_path(self.archive_root, value["artifact"]["sha256"]); obj.chmod(0o644); obj.write_bytes(b"bad")
        result = self.integration.qualify(self.archive_root, "mystic-fixture", self.install_root)
        self.assertEqual(result[0].status, QualificationStatus.FAIL)

    def test_m3_lifecycle_modes_use_production_declaration(self):
        registry = load_registry(ROOT / "catalog"); driver = FakeDriver()
        supervisor = Supervisor(registry, self.base / "state", driver_resolver=lambda _service: driver, clock=FakeClock())
        supervisor.reconcile(); self.assertEqual(supervisor.status("mystic-main")["state"], "running")
        supervisor.stop("mystic-main", force=True); supervisor.start("mystic-main", reason="admin")
        self.assertEqual(supervisor.status("mystic-main")["state"], "running")
        supervisor.stop("mystic-main", force=True)

        catalog = self.base / "on-demand-catalog"; shutil.copytree(ROOT / "catalog", catalog)
        service_path = catalog / "services/mystic-main.yml"
        service_path.write_text(service_path.read_text().replace("mode: always_on", "mode: on_demand"))
        on_demand = load_registry(catalog); driver = FakeDriver()
        supervisor = Supervisor(on_demand, self.base / "on-demand-state",
                                driver_resolver=lambda _service: driver, clock=FakeClock())
        supervisor.reconcile(); self.assertEqual(supervisor.status("mystic-main")["state"], "stopped")
        session = supervisor.acquire_session("mystic-main")
        self.assertEqual(supervisor.status("mystic-main")["state"], "running")
        supervisor.release_session("mystic-main", session)

    def test_m4_route_and_failed_route_hold_cleanup(self):
        registry = load_registry(ROOT / "catalog"); driver = FakeDriver()
        supervisor = Supervisor(registry, self.base / "state", driver_resolver=lambda _service: driver, clock=FakeClock())
        connector = MemoryConnector(); router = Router(registry, supervisor, self.base / "router", connectors={"tcp": connector})
        handle = router.open_session(RouteRequest("mystic-main"))
        self.assertEqual(supervisor.status("mystic-main")["active_session_count"], 1)
        handle.close(); self.assertEqual(supervisor.status("mystic-main")["active_session_count"], 0)
        failure = MemoryConnector(error=OSError("fixture failure"))
        router = Router(registry, supervisor, self.base / "router-fail", connectors={"tcp": failure})
        with self.assertRaises(OSError): router.open_session(RouteRequest("mystic-main"))
        self.assertEqual(supervisor.status("mystic-main")["active_session_count"], 0)
        supervisor.stop("mystic-main", force=True)

    def test_local_tcp_route_fixture(self):
        server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1); port = server.getsockname()[1]
        thread = threading.Thread(target=lambda: server.accept()[0].close()); thread.start()
        from ubb_router.transports import TCPConnector
        stream = TCPConnector().connect({"host": "127.0.0.1", "port": port}, .5); stream.close()
        thread.join(2); server.close(); self.assertFalse(thread.is_alive())

    def test_downloader_guard_is_precise(self):
        role = self.base / "roles/mystic_bbs/tasks"; role.mkdir(parents=True)
        (role / "bad.yml").write_text("- get_url:\n    url: https://example.invalid/product.zip\n")
        self.assertEqual(prohibited_downloads(self.base), ["roles/mystic_bbs/tasks/bad.yml"])
        (role / "bad.yml").write_text("- ansible.builtin.apt:\n    name: [curl, wget]\n")
        assert_preservation_first(self.base)
        assert_preservation_first(ROOT)

    def test_future_fs_uae_implementation_can_satisfy_contract(self):
        class SyntheticAmigaIntegration:
            id = "synthetic-amiga"; runtime = "fs_uae"; automation_level = "assisted"
            def acquire(self, *args, **kwargs): return {}
            def verify_artifacts(self, *args): return {}
            def install(self, *args): return None
            def configure(self, *args, **kwargs): return None
            def qualify(self, *args, **kwargs): return []
        item = IntegrationRegistry((SyntheticAmigaIntegration(),)).get("synthetic-amiga")
        self.assertEqual(item.runtime, "fs_uae")


if __name__ == "__main__": unittest.main()
