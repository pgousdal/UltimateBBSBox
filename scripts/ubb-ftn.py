#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[0]))
from ubb_ftn import FTNConfig,FTNNetwork,FTNPeer,FTNArea,FTNAdapter
def sample():
 n=FTNNetwork('local','Local FTN',('2:211/16',),peers=(FTNPeer('uplink','2:211/1','ftn.example.invalid',password_ref='/etc/ubb/ftn.key'),),areas=(FTNArea('LOCAL','local','echomail','mystic-main','GENERAL'),)); return FTNConfig((n,),(FTNAdapter('mystic-main',('import_echomail','export_echomail','scheduled_exchange')),))
def main():
 p=argparse.ArgumentParser(description='UBB FTN diagnostics'); p.add_argument('command',choices='status networks addresses peers areas queues mappings validate render'.split()); p.add_argument('--json',action='store_true'); a=p.parse_args(); c=sample(); d=c.safe_summary()
 if a.command=='networks': d={'networks':[n.network_id for n in c.networks]}
 elif a.command=='addresses': d={'addresses':[x for n in c.networks for x in n.local_addresses]}
 elif a.command=='peers': d={'peers':[{'id':p.peer_id,'address':p.address,'host':p.host} for n in c.networks for p in n.peers]}
 elif a.command=='areas': d={'areas':[{'tag':x.tag,'network':x.network_id,'kind':x.kind} for n in c.networks for x in n.areas]}
 elif a.command=='queues': d={'inbound':0,'outbound':0,'oldest_outbound_age_seconds':0}
 elif a.command=='mappings': d={'mappings':[{'tag':x.tag,'service':x.bbs_service,'area':x.bbs_area} for n in c.networks for x in n.areas if x.bbs_service]}
 elif a.command=='validate': d={'valid':True,'public_listener':False}
 elif a.command=='render': d={'binkd':c.render_binkd(),'tosser':c.render_tosser()}
 print(json.dumps(d,sort_keys=True,indent=None if a.json else 2,separators=(',',':') if a.json else None)); return 0
if __name__=='__main__': raise SystemExit(main())
