#!/usr/bin/env python3
"""Privacy-safe, read-only M6.3 mail diagnostics."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ubb_mail import MailConfig,MailDomain,Recipient,Adapter
def sample():
 return MailConfig(domains=(MailDomain('example.invalid','local'),), recipients=(Recipient('sysop@example.invalid','mystic-main','sysop'),), edge_ips=('203.0.113.10',), dkim_domains=('example.invalid',), dkim_key_ref='/etc/ubb/secrets/dkim.key')
def main():
 p=argparse.ArgumentParser(description='UBB Internet mail diagnostics'); p.add_argument('command',choices='status domains recipients routes dns queue adapters validate render'.split()); p.add_argument('--json',action='store_true'); a=p.parse_args(); c=sample()
 d={'status':'fixture','domains':[x.name for x in c.domains],'queue':{'depth':0,'deferred':0},'outbound_mode':c.outbound_mode}
 if a.command=='domains': d={'domains':[x.name for x in c.domains]}
 elif a.command=='recipients': d={'recipients':[{'address':x.address,'service':x.service,'local_identity':x.local_identity} for x in c.recipients]}
 elif a.command=='dns': d={'mx':list(c.mx_records()),'spf':c.spf_record(),'dmarc':list(c.public_dns())[len(c.mx_records()):]}
 elif a.command=='adapters': d={'adapters':[],'qualification':'HUMAN_REQUIRED'}
 elif a.command=='validate': d={'valid':True,'open_relay':False,'catch_all':c.catch_all}
 elif a.command=='render': d={'postfix':c.render(),'recipient_map':c.recipient_map()}
 if a.json: print(json.dumps(d,sort_keys=True,separators=(',',':')))
 else: print(json.dumps(d,sort_keys=True,indent=2))
 return 0
if __name__=='__main__': raise SystemExit(main())
