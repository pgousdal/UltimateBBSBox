import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from integrations.bbs.abbs.integration import ABBSAmigaIntegration
from ubb_registry.loader import load_registry


class ABBS11AndPolicyTests(unittest.TestCase):
    def test_family_releases_and_unchanged_32_identity(self):
        integration = ABBSAmigaIntegration()
        self.assertEqual(set(integration.releases), {"1.1", "3.2-999"})
        old = integration.select_release("3.2-999")
        self.assertEqual(old.artifact_id, "abbs-amiga-3.2-999-original")
        self.assertEqual(old.sha256, "5e9fd4cbf871a2bbd4579a3f9b35a0cd2187676cab8886b16adbfe8b038380e4")
        release = integration.select_release("1.1")
        self.assertEqual(release.filename, "abbs1_1.lha")
        self.assertEqual(release.size, 369000)
        self.assertEqual(release.sha256, "bd7e857788ffb326533d64f096535c183377a33b5d68ff3172a8eeb87ef453a")
        self.assertEqual(release.supported_profiles, ("amiga-a1200-os31",))
        self.assertEqual(release.default_profile, "amiga-a1200-os31")

    def test_11_rights_and_profile_are_release_specific(self):
        release = ABBSAmigaIntegration().select_release("1.1")
        self.assertFalse("amiga-a500-k13" in release.supported_profiles)
        self.assertEqual(release.rights_status, "freeware")
        self.assertIn("redistribution", " ".join(release.rights_evidence).lower())

    def test_tier1_recommendations_do_not_change_configured_mode(self):
        registry = load_registry(ROOT / "catalog")
        self.assertEqual(registry.resolve("mystic-main")["integration"]["recommended_lifecycle"], "always_on")
        self.assertEqual(registry.resolve("abbs-main")["integration"]["recommended_lifecycle"], "always_on")
        self.assertEqual(registry.resolve("mystic-main")["service"]["lifecycle"]["mode"], "always_on")
        self.assertEqual(registry.resolve("abbs-main")["service"]["lifecycle"]["mode"], "always_on")
        service = ROOT / "catalog/services/abbs-main.yml"
        with tempfile.TemporaryDirectory() as temp:
            copy = pathlib.Path(temp) / "catalog"; import shutil; shutil.copytree(ROOT / "catalog", copy)
            path = copy / "services/abbs-main.yml"; path.write_text(path.read_text().replace("mode: always_on", "mode: on_demand"))
            self.assertEqual(load_registry(copy).resolve("abbs-main")["service"]["lifecycle"]["mode"], "on_demand")

    def test_release_acquisition_arguments_are_m1_only(self):
        integration = ABBSAmigaIntegration(); release = integration.select_release("1.1")
        args = integration._args(pathlib.Path(tempfile.mkdtemp()), release)
        self.assertEqual(args.source_url, "https://aminet.net/comm/bbs/abbs1_1.lha")
        self.assertEqual(args.expected_sha256, release.sha256)
        self.assertFalse(args.redistribute_original)
        self.assertFalse(args.publish_to_bbs_filebase)


if __name__ == "__main__":
    unittest.main()
