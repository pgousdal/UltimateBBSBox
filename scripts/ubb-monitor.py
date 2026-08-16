#!/usr/bin/env python3
"""Evaluate derived monitoring state once and return Nagios-style status."""
from __future__ import annotations
import argparse, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from ubb_registry.loader import load_registry
from ubb_observatory import Observatory
from ubb_monitoring import MonitoringEngine

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("evaluate",nargs="?",default="evaluate"); p.add_argument("--catalog",default="catalog"); p.add_argument("--state-root",default="/var/lib/ultimate-bbs-box"); p.add_argument("--json",action="store_true"); a=p.parse_args(argv)
    obs=Observatory(load_registry(a.catalog),supervisor_state=pathlib.Path(a.state_root)/"supervisor",backup_root=pathlib.Path(a.state_root)/"backups")
    snapshot=obs.snapshot(); engine=MonitoringEngine(a.state_root); alerts=engine.alerts(snapshot,active=True); critical=sum(x.get("severity")=="critical" for x in alerts); warning=sum(x.get("severity")=="warning" for x in alerts)
    result={"health":{k:sum(getattr(s,"health","UNKNOWN")==k for s in snapshot.services) for k in ("HEALTHY","DEGRADED","UNHEALTHY","UNKNOWN")},"alerts":list(alerts)}
    print(json.dumps(result,sort_keys=True) if a.json else f"active alerts: {len(alerts)} (critical={critical}, warning={warning})")
    return 2 if critical else (1 if warning else 0)
if __name__=="__main__": sys.exit(main())
