#!/usr/bin/env python3
"""Evaluate derived monitoring state once and return Nagios-style status."""
from __future__ import annotations
import argparse, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from ubb_registry.loader import load_registry
from ubb_observatory import Observatory
from ubb_monitoring import MonitoringEngine

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("command",nargs="?",default="evaluate",choices=("evaluate","heartbeat")); p.add_argument("heartbeat_action",nargs="?",choices=("ingest",)); p.add_argument("heartbeat_file",nargs="?"); p.add_argument("--catalog",default="catalog"); p.add_argument("--state-root",default="/var/lib/ultimate-bbs-box"); p.add_argument("--json",action="store_true"); a=p.parse_args(argv)
    engine=MonitoringEngine(a.state_root)
    if a.command=="heartbeat":
        if a.heartbeat_action!="ingest" or not a.heartbeat_file: raise SystemExit("heartbeat ingest requires a JSON file")
        import json as _json
        record=_json.loads(pathlib.Path(a.heartbeat_file).read_text()); result=engine.heartbeat_ingest(record); print(_json.dumps(result,sort_keys=True)); return 0
    obs=Observatory(load_registry(a.catalog),supervisor_state=pathlib.Path(a.state_root)/"supervisor",backup_root=pathlib.Path(a.state_root)/"backups")
    snapshot=obs.snapshot(); alerts=engine.alerts(snapshot,active=True); critical=sum(x.get("severity")=="critical" for x in alerts); warning=sum(x.get("severity")=="warning" for x in alerts)
    result={"health":{k:sum(getattr(s,"health","UNKNOWN")==k for s in snapshot.services) for k in ("HEALTHY","DEGRADED","UNHEALTHY","UNKNOWN")},"alerts":list(alerts)}
    print(json.dumps(result,sort_keys=True) if a.json else f"active alerts: {len(alerts)} (critical={critical}, warning={warning})")
    return 2 if critical else (1 if warning else 0)
if __name__=="__main__": sys.exit(main())
