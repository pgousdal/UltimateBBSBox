import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/"scripts"),str(ROOT)]
from integrations.bbs.amiexpress.integration import AmiExpressAmigaIntegration  # noqa: E402
from ubb_integrations import ArtifactRequiredError  # noqa: E402
from ubb_registry import load_registry  # noqa: E402


class CurrentTrackTests(unittest.TestCase):
    def setUp(self): self.integration=AmiExpressAmigaIntegration(); self.base=pathlib.Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil; shutil.rmtree(self.base,ignore_errors=True)

    def document(self, *, digest=None, commit="0f344713f30da7b6a4629643e32b50094cb2bd0b", asset="amiExpress-nightly0f344713f30da7b6a4629643e32b50094cb2bd0b.lha"):
        return {"tag_name":"dev-build","draft":False,"prerelease":True,"published_at":"2023-09-12T10:33:45Z","updated_at":"2026-08-10T15:34:27Z","id":120771713,"html_url":"https://github.com/dmcoles/AmiExpress/releases/tag/dev-build","assets":[{"name":asset,"size":456145,"digest":digest or "sha256:23459a56b086a28f9cad1da59691f0867c2e15f16bc37417723fd10207e42533","browser_download_url":"https://github.com/dmcoles/AmiExpress/releases/download/dev-build/"+asset}]}

    def test_stable_is_unchanged_and_development_is_separate(self):
        stable=self.integration.select_release("5.6.1"); current=self.integration.select_release(self.integration.current_release_key)
        self.assertEqual(stable.artifact_id,"amiexpress-amiga-5.6.1-original"); self.assertEqual(stable.sha256,"f49d051222a4a951597d241469dab24adb198c6849cdb111734fdd8c03571f4d"); self.assertEqual(stable.channel,"stable"); self.assertEqual(current.channel,"development"); self.assertNotEqual(stable.artifact_id,current.artifact_id)

    def test_exact_identity_and_floating_rejection(self):
        current=self.integration.select_release(self.integration.current_release_key); self.assertEqual(current.source_commit,"0f344713f30da7b6a4629643e32b50094cb2bd0b"); self.assertNotIn("latest",current.artifact_id); self.assertNotIn("dev-build",current.artifact_id)
        with self.assertRaises(ArtifactRequiredError): self.integration.parse_github_release({"tag_name":"dev-build","draft":False,"prerelease":True,"assets":[]})

    def test_metadata_parse_and_update_states(self):
        parsed=self.integration.parse_github_release(self.document()); self.assertEqual(parsed["source_commit"],"0f344713f30da7b6a4629643e32b50094cb2bd0b"); self.assertEqual(self.integration.check_updates(self.document())["status"],"NO_CHANGE")
        new=self.document(commit="1"*40,asset="amiExpress-nightly"+"1"*40+".lha"); self.assertEqual(self.integration.check_updates(new)["status"],"NEW_BUILD_AVAILABLE")
        bad=self.document(digest="sha256:"+"a"*64); self.assertEqual(self.integration.check_updates(bad)["status"],"DIGEST_MISMATCH")
        self.assertEqual(self.integration.check_updates({"tag_name":"master"})["status"],"INVALID_UPSTREAM_METADATA")

    def test_ambiguous_and_invalid_metadata(self):
        doc=self.document(); doc["assets"].append(dict(doc["assets"][0],name="other.lha"))
        self.assertEqual(self.integration.check_updates(doc)["status"],"INVALID_UPSTREAM_METADATA")
        doc=self.document(asset="nightly.lha"); self.assertEqual(self.integration.check_updates(doc)["status"],"INVALID_UPSTREAM_METADATA")

    def write_qualification(self, artifact, statuses):
        target=self.base/"qualification"; target.mkdir(exist_ok=True); (target/(artifact+".json")).write_text(json.dumps({"results":[{"status":x} for x in statuses]}))

    def test_promotion_requires_qualification_and_preserves_previous(self):
        current=self.integration.select_release(self.integration.current_release_key); self.write_qualification(current.artifact_id,["PASS"])
        state=self.integration.promote(self.base,current.artifact_id); self.assertEqual(state["current"],current.artifact_id); self.assertIsNone(state["previous"])
        stable=self.integration.select_release("5.6.1"); self.write_qualification(stable.artifact_id,["PASS"])
        with self.assertRaises(ArtifactRequiredError): self.integration.promote(self.base,stable.artifact_id)
        self.write_qualification(current.artifact_id,["PASS"]); state=self.integration.promote(self.base,current.artifact_id,approve_human=True); self.assertEqual(state["previous"],current.artifact_id)

    def test_failed_and_human_promotion_rules(self):
        current=self.integration.select_release(self.integration.current_release_key); self.write_qualification(current.artifact_id,["FAIL"])
        with self.assertRaises(ArtifactRequiredError): self.integration.promote(self.base,current.artifact_id)
        self.write_qualification(current.artifact_id,["HUMAN_REQUIRED"])
        with self.assertRaises(ArtifactRequiredError): self.integration.promote(self.base,current.artifact_id)
        self.assertEqual(self.integration.promote(self.base,current.artifact_id,approve_human=True)["current"],current.artifact_id)

    def test_rollback_is_explicit_and_does_not_touch_live_state(self):
        current=self.integration.select_release(self.integration.current_release_key); self.write_qualification(current.artifact_id,["PASS"]); self.integration.promote(self.base,current.artifact_id)
        state=self.integration.deployment_status(self.base); state["previous"]="amiexpress-amiga-5.6.1-original"; (self.base/"deployment/amiexpress-current.json").write_text(json.dumps(state)); live=self.base/"live"; live.mkdir(); (live/"users").write_text("users")
        rolled=self.integration.rollback(self.base); self.assertEqual(rolled["current"],"amiexpress-amiga-5.6.1-original"); self.assertEqual((live/"users").read_text(),"users")
        empty=AmiExpressAmigaIntegration(); empty_root=self.base/"empty"; empty_root.mkdir()
        with self.assertRaises(ArtifactRequiredError): empty.rollback(empty_root)

    def test_production_catalog_pins_current_and_recommends_always_on(self):
        resolved=load_registry(ROOT/"catalog").resolve("amiexpress-main"); integration=resolved["integration"]; self.assertEqual(integration["release_channels"]["development"]["source_commit"],"0f344713f30da7b6a4629643e32b50094cb2bd0b"); self.assertEqual(integration["recommended_lifecycle"],"always_on"); self.assertNotEqual(resolved["service"]["lifecycle"]["mode"],"always_on")

    def test_no_installation_during_update_check(self):
        self.assertEqual(self.integration.check_updates(self.document())["status"],"NO_CHANGE"); self.assertFalse((self.base/"deployment").exists())

    def test_m1_artifact_identity_is_exact(self):
        release=self.integration.select_release(self.integration.current_release_key); self.assertEqual(release.sha256,"23459a56b086a28f9cad1da59691f0867c2e15f16bc37417723fd10207e42533"); self.assertEqual(release.size,456145); self.assertTrue(release.github_digest.startswith("sha256:"))


if __name__=="__main__": unittest.main()
