#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[0]))
from ubb_irc import IRCConfig,IRCChannel,IRCBridge
def sample(): return IRCConfig(channels=(IRCChannel('#ubb'),),bridges=(IRCBridge('mystic-main','#ubb','CHAT',mode='scheduled_bridge'),))
def main():
 p=argparse.ArgumentParser(description='UBB IRC diagnostics'); p.add_argument('command',choices='status channels bridges listeners validate render'.split()); p.add_argument('--json',action='store_true'); a=p.parse_args(); c=sample(); d=c.to_safe_dict()
 if a.command=='channels': d={'channels':[{'name':x.channel,'visibility':x.visibility,'history':x.history} for x in c.channels]}
 elif a.command=='bridges': d={'bridges':[{'service':x.service,'channel':x.channel,'mode':x.mode} for x in c.bridges]}
 elif a.command=='listeners': d={'tls':c.listen_tls,'tls_port':c.tls_port,'plaintext':c.listen_plain,'plain_port':c.plain_port}
 elif a.command=='validate': d={'valid':True,'mode':c.mode,'public_tls_required':c.mode=='public'}
 elif a.command=='render': d={'config':c.render()}
 print(json.dumps(d,sort_keys=True,indent=None if a.json else 2,separators=(',',':') if a.json else None)); return 0
if __name__=='__main__': raise SystemExit(main())
