import sys
import threading
import unittest
import hashlib
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ubb_dos import (COMPort, DOSConfigError, DOSDeployment, DOSProfile,
                     DriveMapping, MachineProfile, NodeAllocator, TerminalProfile,
                     backend_evidence, boot_marker_ready, debian_provisioning_plan,
                     default_profiles, freedos_release_metadata, qualification,
                     qualification_evidence, validate_dos_filename,
                     DOSProvisioningError, PinnedDOSInput, verify_preserved_input)
from ubb_runtime import DOSAdapter, RuntimeAdapterRegistry, UnsupportedAdapter


class DOSRuntimeTests(unittest.TestCase):
    def test_profiles_and_backend_adapter(self):
        self.assertIn("freedos-bbs", default_profiles())
        self.assertIsInstance(RuntimeAdapterRegistry.defaults().get("dos"), UnsupportedAdapter)
        self.assertEqual(DOSAdapter.runtime_name, "dos")
        with self.assertRaises(DOSConfigError): MachineProfile(cpu="gaming")

    def test_private_dos_profile_requires_rights(self):
        self.assertEqual(DOSProfile("private", guest_family="msdos", rights="licensed_private").guest_family, "msdos")
        with self.assertRaises(DOSConfigError): DOSProfile("bad", guest_family="msdos")

    def test_terminal_and_com_models(self):
        self.assertTrue(TerminalProfile().binary_safe)
        ports = (COMPort("COM1", endpoint="/tmp/pty"), COMPort("COM2", kind="tcp", endpoint="127.0.0.1:9000"))
        with self.assertRaises(DOSConfigError): DOSDeployment("bbs", default_profiles()["freedos-bbs"], Path("/gold"), Path("/work"), com_ports=(ports[0], ports[0]))
        self.assertEqual(ports[0].capability, "byte_stream")

    def test_isolated_deployment_and_path_rules(self):
        profile = default_profiles()["freedos-bbs"]
        deployment = DOSDeployment("bbs", profile, Path("/srv/golden"), Path("/srv/services/bbs"),
                                   drives=(DriveMapping("C", Path("/srv/services/bbs")),))
        self.assertFalse(deployment.golden_root == deployment.working_root)
        with self.assertRaises(DOSConfigError): DriveMapping("D", Path("/"))
        self.assertEqual(validate_dos_filename("HELLO.TXT"), "HELLO.TXT")
        for name in ("../BAD.TXT", "CON", "TOOLONG99.TXT"):
            with self.assertRaises(DOSConfigError): validate_dos_filename(name)

    def test_concurrent_nodes_release_and_recovery(self):
        allocator = NodeAllocator(4); barrier = threading.Barrier(8); results=[]
        def allocate(i):
            barrier.wait()
            try: results.append(allocator.allocate(f"s{i}"))
            except DOSConfigError: pass
        threads=[threading.Thread(target=allocate,args=(i,)) for i in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(results), 4); self.assertFalse(allocator.release(results[0], "wrong")); self.assertTrue(allocator.release(results[0]))
        self.assertEqual(allocator.recover_stale(set()), 3)

    def test_qualification_is_honest_without_real_runtime(self):
        d = DOSDeployment("bbs", default_profiles()["freedos-bbs"], Path("/gold"), Path("/work"))
        self.assertEqual(qualification(d)["status"], "HUMAN_REQUIRED")

    def test_real_evidence_requires_guest_marker_and_has_machine_readable_state(self):
        self.assertFalse(boot_marker_ready(b"process alive\n"))
        self.assertTrue(boot_marker_ready(b"FreeDOS\nUBB_DOS_READY\n"))
        item = qualification_evidence("boot", "HUMAN_REQUIRED", reason="runtime unavailable")
        self.assertEqual(item["state"], "HUMAN_REQUIRED")
        self.assertIn("architecture", backend_evidence()["host"])

    def test_debian_first_provisioning_and_observed_freedos_identity(self):
        plan = debian_provisioning_plan(release="debian-13")
        self.assertEqual(plan["production_os"], "debian")
        self.assertFalse(plan["ubuntu_ppa"])
        with self.assertRaises(DOSConfigError): debian_provisioning_plan(target_os="ubuntu")
        self.assertEqual(freedos_release_metadata()["state"], "HUMAN_REQUIRED")
        with self.assertRaises(DOSConfigError): freedos_release_metadata(version="1.3")
        plan = debian_provisioning_plan(
            release="13", source_commit="82770aba398485117c56523a1a5c261f6e37ca64",
            source_sha256="8" * 64)
        self.assertEqual(plan["method"], "pinned_source")
        self.assertEqual(plan["install_prefix"], "/opt/ultimate-bbs-box/dosemu2/82770aba3984")
        with self.assertRaises(DOSConfigError):
            debian_provisioning_plan(release="13", source_commit="main", source_sha256="8" * 64)

    def test_provisioning_consumes_only_verified_archive_objects(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "archive"; (root / "objects" / "sha256").mkdir(parents=True)
            (root / "metadata").mkdir(); (root / "state").mkdir()
            (root / "state" / "archive-v1.json").write_text('{}')
            payload = b"pinned source"
            digest = hashlib.sha256(payload).hexdigest()
            obj = root / "objects" / "sha256" / digest[:2] / digest
            obj.parent.mkdir(); obj.write_bytes(payload)
            meta = {"kind":"artifact", "schema_version":1, "id":"fixture",
                    "artifact":{"sha256":digest,"size":len(payload),"role":"source_code","original_filename":"fixture.tar.gz"},
                    "provenance":{"acquired_at":"2026-01-01T00:00:00Z","source":"fixture"},
                    "rights":{"status":"open_source","preserve_locally":True,"install_locally":True,
                              "redistribute_original":False,"publish_to_bbs_filebase":False,"export_from_archive":False},
                    "preservation":{"class":"original","immutable":True}}
            (root / "metadata" / "fixture.json").write_text(json.dumps(meta))
            expected = PinnedDOSInput("fixture", digest, len(payload), "source_code")
            result = verify_preserved_input(root, expected)
            self.assertEqual(result["sha256"], digest)
            obj.write_bytes(b"tampered")
            with self.assertRaises(DOSProvisioningError): verify_preserved_input(root, expected)


if __name__ == "__main__": unittest.main()
