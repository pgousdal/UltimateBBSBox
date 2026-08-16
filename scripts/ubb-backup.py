#!/usr/bin/env python3
"""Inspect/create/verify generic backups using trusted declarations."""
import argparse,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from ubb_backup import BackupManager
p=argparse.ArgumentParser(); p.add_argument('--root',default='/srv/ultimate-bbs-box/backups'); s=p.add_subparsers(dest='command',required=True)
c=s.add_parser('create'); c.add_argument('target'); c.add_argument('--source',required=True); c.add_argument('--active-sessions',type=int,default=0)
l=s.add_parser('list'); l.add_argument('--target'); sh=s.add_parser('show'); sh.add_argument('backup_id'); v=s.add_parser('verify'); v.add_argument('backup_id'); rp=s.add_parser('restore-plan'); rp.add_argument('backup_id'); rp.add_argument('target'); rp.add_argument('--destination',required=True)
def main():
 a=p.parse_args(); m=BackupManager(a.root)
 if a.command=='create': m.declare(a.target,a.source); out=m.create(a.target,active_sessions=a.active_sessions).to_dict()
 elif a.command=='list': out=m.list(a.target)
 elif a.command=='show': out=m.show(a.backup_id)
 elif a.command=='verify': out=m.verify(a.backup_id)
 else: out=m.restore_plan(a.backup_id,a.target,a.destination).to_dict()
 print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()
