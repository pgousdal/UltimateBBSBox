#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from ubb_deployment import DeploymentManager
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("command",choices=("list","show","provenance","verify")); p.add_argument("service_id",nargs="?"); p.add_argument("--archive-root",required=True); p.add_argument("--deployment-root",required=True); p.add_argument("--json",action="store_true"); a=p.parse_args(argv); m=DeploymentManager(a.archive_root,a.deployment_root)
 if a.command=="list": v=m.list()
 else:
  if not a.service_id: raise SystemExit("service id required")
  v=m.show(a.service_id) if a.command=="show" else (m.provenance(a.service_id) if a.command=="provenance" else {"verified":m.verify(a.service_id)})
 print(json.dumps(v,sort_keys=True,indent=2,default=lambda x:x.to_dict() if hasattr(x,"to_dict") else str(x)))
if __name__=="__main__": main()
