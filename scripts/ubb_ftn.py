"""Typed FTN transport/core intent. No FTN protocol implementation is included."""
from __future__ import annotations
import os,re,tempfile
from dataclasses import dataclass
class FTNConfigError(ValueError): pass
_ID=re.compile(r'^[a-z0-9][a-z0-9._-]*$'); _ADDR=re.compile(r'^(\d+):(\d+)/(\d+)(?:\.(\d+))?$'); _AREA=re.compile(r'^[A-Z0-9][A-Z0-9_-]{0,63}$')
def ident(v,label='identifier'):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise FTNConfigError('invalid '+label)
 return v
def ftn_address(v):
 m=_ADDR.fullmatch(str(v));
 if not m: raise FTNConfigError('invalid FTN address')
 z,n,node,p=(int(x) if x is not None else 0 for x in m.groups())
 if not (0<z<=65535 and 0<=n<=65535 and 0<=node<=65535 and 0<=p<=65535): raise FTNConfigError('FTN address out of range')
 return f'{z}:{n}/{node}'+(f'.{p}' if m.group(4) is not None else '')
def external(v):
 if not isinstance(v,str) or not v.startswith('/') or '\n' in v or '\r' in v: raise FTNConfigError('secret must be external reference')
 return v
@dataclass(frozen=True)
class FTNPeer:
 peer_id:str; address:str; host:str; port:int=24554; password_ref:str|None=None; enabled:bool=True; poll_policy:str='interval'
 def __post_init__(self):
  ident(self.peer_id,'peer id'); object.__setattr__(self,'address',ftn_address(self.address))
  if not self.host or '\n' in self.host or '\r' in self.host: raise FTNConfigError('invalid peer host')
  if not 1<=self.port<=65535: raise FTNConfigError('invalid peer port')
  if self.password_ref: external(self.password_ref)
  if self.poll_policy not in ('always_listening','interval','scheduled','manual'): raise FTNConfigError('invalid poll policy')
@dataclass(frozen=True)
class FTNArea:
 tag:str; network_id:str; kind:str='echomail'; bbs_service:str|None=None; bbs_area:str|None=None; enabled:bool=True
 def __post_init__(self):
  if not _AREA.fullmatch(self.tag): raise FTNConfigError('invalid area tag')
  ident(self.network_id,'network id')
  if self.kind not in ('echomail','netmail'): raise FTNConfigError('invalid area kind')
  if self.bbs_service: ident(self.bbs_service,'BBS service')
@dataclass(frozen=True)
class FTNAdapter:
 service:str; capabilities:tuple[str,...]; mode:str='scheduled_exchange'; checkpoint_ref:str|None=None
 def __post_init__(self):
  ident(self.service,'adapter service')
  allowed={'import_echomail','export_echomail','import_netmail','export_netmail','native_ftn','batch_exchange','scheduled_exchange'}
  if any(x not in allowed for x in self.capabilities): raise FTNConfigError('invalid adapter capability')
  if self.mode not in ('always_listening','interval','scheduled','manual'): raise FTNConfigError('invalid adapter mode')
  if self.checkpoint_ref: external(self.checkpoint_ref)
@dataclass(frozen=True)
class FTNNetwork:
 network_id:str; display_name:str; local_addresses:tuple[str,...]; peers:tuple[FTNPeer,...]=(); areas:tuple[FTNArea,...]=(); enabled:bool=True; public_listener:bool=False; bind_host:str='127.0.0.1'; spool_root:str='/var/lib/ubb/ftn'; encoding:str='network-defined'; nodelist_ref:str|None=None; archive_method:str='zip'
 def __post_init__(self):
  ident(self.network_id,'network id');
  if not self.local_addresses: raise FTNConfigError('network requires local address')
  object.__setattr__(self,'local_addresses',tuple(ftn_address(x) for x in self.local_addresses))
  if self.encoding not in ('CP437','CP850','ISO-8859-1','UTF-8','network-defined'): raise FTNConfigError('invalid encoding')
  if self.archive_method not in ('none','zip','arc','arj','lzh'): raise FTNConfigError('archive method not allow-listed')
  if self.public_listener and self.bind_host in ('0.0.0.0','::') and not self.peers: raise FTNConfigError('public listener requires explicit peers')
  if self.nodelist_ref: external(self.nodelist_ref)
  tags=[x.tag for x in self.areas]
  if len(tags)!=len(set(tags)): raise FTNConfigError('duplicate area tag')
@dataclass(frozen=True)
class FTNConfig:
 networks:tuple[FTNNetwork,...]=(); adapters:tuple[FTNAdapter,...]=(); listen_port:int=24554
 def __post_init__(self):
  ids=[x.network_id for x in self.networks]
  if len(ids)!=len(set(ids)): raise FTNConfigError('duplicate network')
  if not 1<=self.listen_port<=65535: raise FTNConfigError('invalid listener port')
  for n in self.networks:
   if n.public_listener and n.bind_host in ('0.0.0.0','::') and not n.peers: raise FTNConfigError('public listener requires explicit peers')
 def render_binkd(self):
  lines=[f'listen {self.listen_port}']
  for n in sorted(self.networks,key=lambda x:x.network_id):
   lines.append(f'# network {n.network_id}'); lines.append(f'node-dir {n.spool_root}/inbound')
   for p in sorted(n.peers,key=lambda x:x.peer_id): lines.append(f'peer {p.address} {p.host}:{p.port}')
  return '\n'.join(lines)+'\n'
 def render_tosser(self): return '\n'.join(f'network {n.network_id} areas {len(n.areas)} encoding {n.encoding} archive {n.archive_method}' for n in sorted(self.networks,key=lambda x:x.network_id))+'\n'
 def safe_summary(self): return {'network_count':len(self.networks),'peer_count':sum(len(n.peers) for n in self.networks),'area_count':sum(len(n.areas) for n in self.networks),'listen_port':self.listen_port,'public_networks':sum(n.public_listener for n in self.networks)}
def write_atomic(path,content):
 target=os.path.abspath(os.fspath(path)); os.makedirs(os.path.dirname(target),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.ubb-ftn-',dir=os.path.dirname(target),text=True)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(content); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,target)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
