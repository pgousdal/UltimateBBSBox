#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ubb_news import NewsConfig,NewsGroup,NewsAdapter,Retention
def sample():
 return NewsConfig(groups=(NewsGroup('comp.ubb.general','UBB discussion'),),adapters=(NewsAdapter('mystic-main','scheduled_exchange',('inbound_to_bbs','outbound_from_bbs','mapping')),),retention=Retention())
def main():
 p=argparse.ArgumentParser(description='UBB NNTP diagnostics'); p.add_argument('command',choices='status groups mappings adapters feeds spool validate render'.split()); p.add_argument('--json',action='store_true'); a=p.parse_args(); c=sample(); d=c.to_safe_dict()
 if a.command=='groups': d={'groups':[{'name':g.name,'description':g.description,'read':g.read_policy,'post':g.post_policy} for g in c.groups]}
 elif a.command=='mappings': d={'mappings':[{'group':g.name,'service':g.bbs_service,'area':g.bbs_area} for g in c.groups if g.bbs_service]}
 elif a.command=='adapters': d={'adapters':[{'service':x.service,'mode':x.mode} for x in c.adapters]}
 elif a.command=='feeds': d={'feeds':[]}
 elif a.command=='spool': d={'article_count':0,'spool_bytes':0,'oldest_age_seconds':0}
 elif a.command=='validate': d={'valid':True,'mode':c.mode,'bounded_retention':True}
 elif a.command=='render': d={'config':c.render(),'groups':c.groups_render()}
 print(json.dumps(d,sort_keys=True,indent=None if a.json else 2,separators=(',',':') if a.json else None)); return 0
if __name__=='__main__': raise SystemExit(main())
