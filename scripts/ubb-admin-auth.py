#!/usr/bin/env python3
import argparse,getpass,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from ubb_admin.auth import AuthStore
p=argparse.ArgumentParser(); p.add_argument('--path',default='/etc/ultimate-bbs-box/admin-users.json'); s=p.add_subparsers(dest='command',required=True)
a=s.add_parser('add'); a.add_argument('username'); a.add_argument('--role',default='viewer',choices=('viewer','operator','administrator')); d=s.add_parser('disable'); d.add_argument('username'); s.add_parser('list')
def main():
 x=p.parse_args(); store=AuthStore(x.path)
 if x.command=='list': print(store.list()); return
 if x.command=='disable': store.disable(x.username); print('admin account disabled'); return
 one=getpass.getpass('Password: '); two=getpass.getpass('Confirm: ')
 if one!=two: raise SystemExit('passwords do not match')
 store.add(x.username,one,x.role); print('admin account updated')
if __name__=='__main__':main()
