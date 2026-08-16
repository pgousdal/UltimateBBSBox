#!/usr/bin/env python3
"""Read-only local Admin Observatory CLI."""
from __future__ import annotations
import argparse, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from ubb_registry.loader import load_registry
from ubb_observatory import Observatory

def build_parser():
    p=argparse.ArgumentParser(description="Ultimate BBS Box read-only admin observatory")
    p.add_argument("--catalog", default="catalog"); p.add_argument("--archive-root")
    p.add_argument("--supervisor-state"); p.add_argument("--router-state")
    p.add_argument("--install-root", action="append", default=[], metavar="INTEGRATION=PATH")
    p.add_argument("--json", action="store_true")
    sub=p.add_subparsers(dest="command",required=True)
    for name in ("status","services","sessions","activity","alerts","hosts","readiness","artifacts","backups"):
        cmd=sub.add_parser(name)
        if name in ("activity",): cmd.add_argument("--limit",type=int,default=50)
        if name in ("service",): cmd.add_argument("service_id")
    service=sub.add_parser("service"); service.add_argument("service_id")
    return p

def main(argv=None):
    args=build_parser().parse_args(argv)
    roots={}
    for item in args.install_root:
        if "=" not in item: raise SystemExit("--install-root requires INTEGRATION=PATH")
        key,value=item.split("=",1); roots[key]=value
    observatory=Observatory(load_registry(args.catalog),archive_root=args.archive_root,
        supervisor_state=args.supervisor_state,router_state=args.router_state,install_roots=roots)
    snapshot=observatory.snapshot(args.limit if args.command=="activity" else 100)
    if args.command=="status":
        running=sum(x.state in ("running","ready","maintenance") for x in snapshot.services); callers=sum(x.active_sessions for x in snapshot.services)
        value={"services":len(snapshot.services),"running":running,"active_callers":callers,"maintenance":sum(x.maintenance for x in snapshot.services),"failed":sum(x.state=="failed" for x in snapshot.services),"alerts":len(snapshot.alerts)}
        if not args.json:
            print("ULTIMATE BBS BOX\n"); print(f"Services: {value['services']}  Running: {running}  Active callers: {callers}  Maintenance: {value['maintenance']}  Failed: {value['failed']}  Alerts: {value['alerts']}\n")
            print("NAME                 TYPE POLICY      STATE       CALLERS READINESS")
            for x in snapshot.services: print(f"{x.title[:20]:20} {x.type:5} {str(x.policy or 'unknown'):11} {x.state:11} {x.active_sessions:7} {x.readiness}")
            return 0
    elif args.command=="services": value=[x.to_dict() for x in snapshot.services]
    elif args.command=="service":
        value=next((x.to_dict() for x in snapshot.services if x.id==args.service_id),None)
        if value is None: raise SystemExit(f"unknown service: {args.service_id}")
    elif args.command=="sessions": value=list(snapshot.sessions)
    elif args.command=="activity": value=[x.to_dict() for x in snapshot.activity]
    elif args.command=="alerts": value=[x.to_dict() for x in snapshot.alerts]
    elif args.command=="hosts": value=list(snapshot.hosts)
    elif args.command=="readiness": value=[{"service_id":x.id,"readiness":x.readiness} for x in snapshot.services]
    elif args.command=="artifacts": value=[{"service_id":x.id,"artifact":x.artifact} for x in snapshot.services if x.artifact]
    else: value=[{"service_id":x.id,"backup":x.backup or {"status":"UNKNOWN"}} for x in snapshot.services]
    print(json.dumps(value if args.json else {"data":value,"degraded_sources":list(snapshot.degraded_sources)},indent=2,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
