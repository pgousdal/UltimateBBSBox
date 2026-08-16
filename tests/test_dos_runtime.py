import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ubb_dos import (COMPort, DOSConfigError, DOSDeployment, DOSProfile,
                     DriveMapping, MachineProfile, NodeAllocator, TerminalProfile,
                     default_profiles, qualification, validate_dos_filename)
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


if __name__ == "__main__": unittest.main()
