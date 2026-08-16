#!/usr/bin/env python3
import argparse
from ubb_network import DNSConfig,NTPConfig
from ubb_network_hardening import NetworkInventory,secret_inventory,firewall_intent
def main(argv=None):
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='kind',required=True)
 for k in ('dns','ntp'):
  q=sub.add_parser(k); q.add_argument('command',choices=('render','validate','status'))
 for k in ('status','services','listeners','exposure','dependencies','readiness','secrets','tls','queues','validate','drift'):
  sub.add_parser(k)
 a=p.parse_args(argv); cfg=DNSConfig() if a.kind=='dns' else NTPConfig(mode='client_and_server' if a.kind=='ntp' and a.command=='render' else 'client_only')
 if a.kind in ('dns','ntp'):
  print(cfg.render() if a.command=='render' else ('valid' if a.command=='validate' else 'configured')); return
 inv=NetworkInventory.from_catalog(); inv.validate()
 import json
 if a.kind=='status': out=inv.summary()
 elif a.kind=='services': out={'services':inv.services}
 elif a.kind=='listeners': out={'listeners':[x.__dict__ for x in inv.listeners]}
 elif a.kind=='exposure': out={'firewall':firewall_intent(),'listeners':[x.__dict__ for x in inv.listeners]}
 elif a.kind=='dependencies': out=inv.dependencies
 elif a.kind=='readiness': out=inv.qualification
 elif a.kind=='secrets': out={'secrets':secret_inventory()}
 elif a.kind=='tls': out={'tls':secret_inventory()}
 elif a.kind=='queues': out={'mail':{},'nntp':{},'ftn':{},'offline_exchange':{}}
 elif a.kind=='validate': out={'valid':True,'digest':inv.digest()}
 else: out={'desired_digest':inv.digest(),'deployed_state':'UNKNOWN'}
 print(json.dumps(out,sort_keys=True,indent=2))
if __name__=='__main__': main()
