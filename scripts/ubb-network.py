#!/usr/bin/env python3
import argparse
from ubb_network import DNSConfig,NTPConfig
def main(argv=None):
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='kind',required=True)
 for k in ('dns','ntp'):
  q=sub.add_parser(k); q.add_argument('command',choices=('render','validate','status'))
 a=p.parse_args(argv); cfg=DNSConfig() if a.kind=='dns' else NTPConfig(mode='client_and_server' if a.kind=='ntp' and a.command=='render' else 'client_only')
 print(cfg.render() if a.command=='render' else ('valid' if a.command=='validate' else 'configured'))
if __name__=='__main__': main()
