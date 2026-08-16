import json, pathlib, tempfile, unittest, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ubb_registry.loader import load_registry
from ubb_observatory import Observatory

class ObservatoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=pathlib.Path(self.tmp.name)
        self.catalog=self.base/'catalog'; import shutil; shutil.copytree(ROOT/'catalog',self.catalog)
        self.archive=self.base/'archive'; (self.archive/'metadata').mkdir(parents=True)
        self.supervisor=self.base/'supervisor'; (self.supervisor/'instances').mkdir(parents=True)
        self.router=self.base/'router'; self.router.mkdir()
        meta={"id":"abbs-amiga-1.1-original","artifact":{"original_filename":"abbs1_1.lha","sha256":"a"*64},"preservation":{"status":"READY"},"rights":{"status":"freeware","publish_to_bbs_filebase":False},"provenance":{"source_url":"https://aminet.net/comm/bbs/abbs1_1.lha"}}
        (self.archive/'metadata'/'abbs-amiga-1.1-original.json').write_text(json.dumps(meta))
        meta3=dict(meta); meta3["id"]="abbs-amiga-3.2-999-original"; meta3["artifact"]={**meta["artifact"],"original_filename":"ABBS320_999.lha","sha256":"b"*64}
        (self.archive/'metadata'/'abbs-amiga-3.2-999-original.json').write_text(json.dumps(meta3))
    def tearDown(self): self.tmp.cleanup()
    def obs(self): return Observatory(load_registry(self.catalog),archive_root=self.archive,supervisor_state=self.supervisor,router_state=self.router)
    def test_services_policy_state_and_artifact_are_distinct(self):
        (self.supervisor/'instances'/'abbs-main.json').write_text(json.dumps({"service_id":"abbs-main","state":"stopped","active_session_count":0}))
        rows=self.obs().services(); abbs=next(x for x in rows if x.id=='abbs-main')
        self.assertEqual(abbs.policy,'always_on'); self.assertEqual(abbs.state,'stopped'); self.assertEqual(abbs.artifact['sha256'],'b'*64)
        self.assertTrue(any(x['version']=='1.1' for x in abbs.available_releases))
        self.assertTrue(any(x.id=='mystic-main' for x in rows))
    def test_always_on_alert_and_qualification_states(self):
        (self.supervisor/'instances'/'abbs-main.json').write_text(json.dumps({"service_id":"abbs-main","state":"stopped"}))
        alerts=self.obs().alerts(); self.assertTrue(any(x.id=='always-on:abbs-main' for x in alerts))
        (self.supervisor/'instances'/'mystic-main.json').write_text(json.dumps({"service_id":"mystic-main","state":"running"}))
        self.assertFalse(any(x.id=='always-on:mystic-main' for x in self.obs().alerts()))
    def test_activity_is_bounded_deterministic_and_private(self):
        events=[{"timestamp":"2026-01-01T00:00:01Z","service":"abbs-main","new_state":"running","password":"secret"},{"timestamp":"2026-01-01T00:00:02Z","session_id":"s1","target_service":"abbs-main","event_type":"session_active"}]
        (self.supervisor/'events.jsonl').write_text(json.dumps(events[0])+"\n"); (self.router/'events.jsonl').write_text(json.dumps(events[1])+"\n")
        obs=self.obs(); feed=obs.activity(limit=1); self.assertEqual(len(feed),1); self.assertNotIn('secret',json.dumps([x.to_dict() for x in obs.activity()]))
    def test_corrupt_optional_journal_degrades(self):
        (self.supervisor/'events.jsonl').write_text('{bad\n'); snap=self.obs().snapshot(); self.assertIn('supervisor',snap.degraded_sources); self.assertTrue(snap.services)
    def test_remote_health_unknown(self):
        rows=self.obs().services(); remote=next(x for x in rows if x.id=='unix-v7-shell'); self.assertEqual(remote.host_health,'UNKNOWN')

if __name__=='__main__': unittest.main()
