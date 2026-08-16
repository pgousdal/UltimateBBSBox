import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/"scripts"),str(ROOT)]
from ubb_integrations.hardening import (Evidence, EvidenceStatus, assert_immutable, backup_live_state,
    golden_working_invariant, readiness_summary, restore_live_state)
from ubb_supervisor import FakeClock, FakeDriver, Supervisor
from ubb_registry import load_registry


class HardeningTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.base=pathlib.Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_readiness_aggregation_distinguishes_human_and_failure(self):
        evidence=[{"status":"PASS"},{"status":"HUMAN_REQUIRED"}]
        self.assertEqual(readiness_summary(evidence,integration="abbs-amiga",release="3.2")["readiness"],"READY_WITH_HUMAN_REQUIREMENTS")
        self.assertEqual(readiness_summary([{"status":"FAIL"}],integration="mystic-linux",release="x")["readiness"],"NOT_READY")
        self.assertEqual(readiness_summary([],integration="mystic-linux",release="x")["readiness"],"BLOCKED")

    def test_evidence_is_structured_without_sensitive_content(self):
        item=Evidence("mystic-linux","fixture","route",EvidenceStatus.PASS,"TCP route opened",artifact_sha256="a"*64,profile="native",evidence_type="synthetic",reference="test-router")
        value=item.to_dict(); self.assertEqual(value["status"],"PASS"); self.assertNotIn("password",json.dumps(value).lower()); self.assertNotIn("terminal_data",json.dumps(value))

    def test_backup_restore_excludes_recoverable_software_and_requires_verified_artifact(self):
        live=self.base/"live"; (live/"users").mkdir(parents=True); (live/"users"/"db").write_text("users"); (live/"messages").write_text("messages"); (live/"software").mkdir(); (live/"software"/"binary").write_text("do not backup")
        backup=self.base/"backup"; manifest=backup_live_state(live,backup,integration="mystic-linux",release="fixture"); self.assertEqual({x["path"] for x in manifest["files"]},{"users/db","messages"}); target=self.base/"restored"
        with self.assertRaises(ValueError): restore_live_state(backup,target,verified_artifact=False)
        restored=restore_live_state(backup,target,verified_artifact=True); self.assertEqual(set(restored["restored"]),{"users/db","messages"}); self.assertFalse((target/"software").exists())

    def test_backup_corruption_fails_and_preservation_invariant_is_strict(self):
        live=self.base/"live"; live.mkdir(); (live/"state").write_text("state"); backup=self.base/"backup"; backup_live_state(live,backup,integration="x",release="y"); (backup/"state").write_text("tampered")
        with self.assertRaises(ValueError): restore_live_state(backup,self.base/"restored",verified_artifact=True)
        obj=self.base/"object"; obj.write_bytes(b"immutable"); digest=hashlib.sha256(obj.read_bytes()).hexdigest(); assert_immutable(obj,digest); obj.write_bytes(b"changed")
        with self.assertRaises(ValueError): assert_immutable(obj,digest)

    def test_golden_working_are_distinct(self):
        golden=self.base/"golden"; working=self.base/"working"; golden.write_bytes(b"base"); digest=hashlib.sha256(b"base").hexdigest(); golden_working_invariant(golden,working,digest)
        with self.assertRaises(ValueError): golden_working_invariant(golden,golden,digest)

    def test_synthetic_crash_reconcile_and_route_hold_cleanup_remain_generic(self):
        registry=load_registry(ROOT/"catalog"); clock=FakeClock(); driver=FakeDriver(); supervisor=Supervisor(registry,self.base/"state",driver_resolver=lambda _s:driver,clock=clock)
        supervisor.reconcile(); session=supervisor.acquire_session("mystic-main"); self.assertEqual(supervisor.status("mystic-main")["active_session_count"],1); driver.start_failures=1; supervisor.release_session("mystic-main",session); supervisor.reconcile(); self.assertEqual(supervisor.status("mystic-main")["active_session_count"],0)


if __name__=="__main__": unittest.main()
