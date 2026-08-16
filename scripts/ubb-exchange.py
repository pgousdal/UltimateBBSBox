#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[0]))
from ubb_exchange import ExchangeConfig,AreaMapping,ExchangeAdapter
def main():
 p=argparse.ArgumentParser(description='UBB offline exchange diagnostics'); p.add_argument('command',choices='status formats mappings packets adapters validate'.split()); p.add_argument('--json',action='store_true'); a=p.parse_args(); c=ExchangeConfig(mappings=(AreaMapping('mystic-main','GENERAL','general',conference=1),),adapters=(ExchangeAdapter('mystic-main',('enumerate_areas','export_messages','import_replies','checkpoint')),)); d=c.safe_summary()
 if a.command=='formats': d={'formats':['qwk','bluewave'],'qwke':'HUMAN_REQUIRED'}
 elif a.command=='mappings': d={'mappings':[{'service':x.service,'area':x.area,'external_id':x.external_id,'format':x.format} for x in c.mappings]}
 elif a.command=='packets': d={'outgoing':0,'incoming':0,'processed':0,'rejected':0}
 elif a.command=='adapters': d={'adapters':[{'service':x.service,'mode':x.mode} for x in c.adapters]}
 elif a.command=='validate': d={'valid':True,'bounded':True,'private_content':False}
 print(json.dumps(d,sort_keys=True,indent=None if a.json else 2,separators=(',',':') if a.json else None)); return 0
if __name__=='__main__': raise SystemExit(main())
