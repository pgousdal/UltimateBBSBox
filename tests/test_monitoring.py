import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from ubb_monitoring import MonitoringEngine
from ubb_observatory.models import ServiceSummary, ObservatorySnapshot

class MonitoringTests(unittest.TestCase):
    def service(self, state="running", policy="always_on", health="HEALTHY", backup=None, readiness="READY"):
        return ServiceSummary("demo","Demo","bbs","demo","fake",{},policy,"always_on",state,0,False,readiness,backup=backup,health=health)
    def snap(self, *services, hosts=()): return ObservatorySnapshot(tuple(services),(),(),(),tuple(hosts))
    def test_health_lifecycle_and_unknown_host(self):
        with tempfile.TemporaryDirectory() as d:
            e=MonitoringEngine(d,now=lambda:__import__('datetime').datetime(2026,1,1,tzinfo=__import__('datetime').timezone.utc))
            active=e.alerts(self.snap(self.service()),active=True); self.assertTrue(any(x["alert_id"]=="backup:demo" for x in active))
            bad=self.snap(self.service(state="stopped",health="UNHEALTHY"),hosts=({"id":"remote","health":"UNKNOWN"},)); alerts=e.alerts(bad,active=True); self.assertTrue(any(x["alert_id"]=="health:demo" for x in alerts)); self.assertTrue(any(x["alert_id"]=="host:remote" for x in alerts))
    def test_dedup_clear_recurrence_and_bounded_history(self):
        with tempfile.TemporaryDirectory() as d:
            e=MonitoringEngine(d,retention=1); bad=self.snap(self.service(state="failed",health="UNHEALTHY")); one=e.alerts(bad,active=True)[0]; two=e.alerts(bad,active=True)[0]; self.assertEqual(one["first_seen"],two["first_seen"]); self.assertGreater(two["occurrence_count"],one["occurrence_count"])
            clear=e.alerts(self.snap(self.service(state="running",health="HEALTHY",backup={"status":"verified"})),active=False); self.assertTrue(any(x["state"]=="CLEARED" for x in clear)); self.assertTrue((Path(d)/"observatory/alerts.json").exists())
    def test_corrupt_state_recovers_without_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"observatory"; p.mkdir(); (p/"alerts.json").write_text("not-json"); values=MonitoringEngine(d).alerts(self.snap(self.service(backup={"status":"verified"}))); self.assertIsInstance(values,tuple); self.assertNotIn("password",json.dumps(values)); self.assertEqual(json.loads((p/"alerts.json").read_text())["schema_version"],1)

if __name__=="__main__": unittest.main()
