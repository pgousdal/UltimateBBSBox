"""Product-neutral NNTP/news intent and BBS bridge metadata."""
from __future__ import annotations
import os,re,tempfile
from dataclasses import dataclass

class NewsConfigError(ValueError): pass
_ID=re.compile(r'^[a-z0-9][a-z0-9._-]*$'); _GROUP=re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$'); _HOST=re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$')
def ident(v,label='identifier'):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise NewsConfigError('invalid '+label)
 return v
def group(v):
 if not isinstance(v,str) or len(v)>255 or not _GROUP.fullmatch(v) or v.startswith('.') or v.endswith('.'): raise NewsConfigError('invalid group name')
 return v.lower()
def host(v):
 if not isinstance(v,str) or not _HOST.fullmatch(v.lower()): raise NewsConfigError('invalid hostname')
 return v.lower()
def external_ref(v):
 if not isinstance(v,str) or not v.startswith('/') or '\n' in v or '\r' in v: raise NewsConfigError('secret must be external reference')
 return v

@dataclass(frozen=True)
class Retention:
 max_age_days:int=30; max_articles:int=100000; max_bytes:int=2*1024*1024*1024
 def __post_init__(self):
  if self.max_age_days<=0 or self.max_articles<=0 or self.max_bytes<=0: raise NewsConfigError('retention must be bounded')

@dataclass(frozen=True)
class NewsGroup:
 name:str; description:str=''; enabled:bool=True; read_policy:str='public'; post_policy:str='trusted_network'; moderated:bool=False; retention:Retention|None=None; bbs_service:str|None=None; bbs_area:str|None=None
 def __post_init__(self):
  object.__setattr__(self,'name',group(self.name))
  if self.read_policy not in ('public','authenticated','trusted_network','disabled') or self.post_policy not in ('public','authenticated','trusted_network','moderated','disabled'): raise NewsConfigError('invalid group policy')
  if self.post_policy=='moderated' and not self.moderated: object.__setattr__(self,'moderated',True)
  if self.bbs_service: ident(self.bbs_service,'BBS service')
  if self.bbs_area is not None and (not self.bbs_area or '\n' in self.bbs_area or '\r' in self.bbs_area): raise NewsConfigError('invalid BBS area')

@dataclass(frozen=True)
class NewsAdapter:
 service:str; mode:str; capabilities:tuple[str,...]=(); checkpoint_ref:str|None=None
 def __post_init__(self):
  ident(self.service,'adapter service');
  if self.mode not in ('inbound_to_bbs','outbound_from_bbs','bidirectional','scheduled_exchange','native_nntp'): raise NewsConfigError('invalid adapter mode')
  allowed={'inbound_to_bbs','outbound_from_bbs','bidirectional','scheduled_exchange','native_nntp','mapping'}
  if any(x not in allowed for x in self.capabilities): raise NewsConfigError('invalid adapter capability')
  if self.checkpoint_ref: external_ref(self.checkpoint_ref)

@dataclass(frozen=True)
class NewsFeed:
 peer:str; groups:tuple[str,...]; direction:str='inbound'; secret_ref:str|None=None; schedule:str|None=None; enabled:bool=False
 def __post_init__(self):
  host(self.peer)
  if self.direction not in ('inbound','outbound','bidirectional'): raise NewsConfigError('invalid feed direction')
  for g in self.groups:
   if g.endswith('.*'): group(g[:-2])
   else: group(g)
  if self.secret_ref: external_ref(self.secret_ref)
  if self.schedule and ('\n' in self.schedule or '\r' in self.schedule): raise NewsConfigError('invalid feed schedule')

@dataclass(frozen=True)
class NewsConfig:
 mode:str='private_only'; internal_identity:str='nntp-core.ubb.internal'; public_identity:str|None=None; tls_cert_ref:str|None=None; tls_key_ref:str|None=None; groups:tuple[NewsGroup,...]=(); adapters:tuple[NewsAdapter,...]=(); feeds:tuple[NewsFeed,...]=(); retention:Retention=Retention(); nntp_port:int=119; nntps_port:int|None=None
 def __post_init__(self):
  if self.mode not in ('private_only','public_read','public_read_write'): raise NewsConfigError('invalid NNTP mode')
  host(self.internal_identity)
  if self.public_identity: host(self.public_identity)
  if self.tls_cert_ref: external_ref(self.tls_cert_ref)
  if self.tls_key_ref: external_ref(self.tls_key_ref)
  if not 1<=self.nntp_port<=65535: raise NewsConfigError('invalid NNTP port')
  if self.nntps_port is not None and not 1<=self.nntps_port<=65535: raise NewsConfigError('invalid NNTPS port')
  names=[x.name for x in self.groups]
  if len(names)!=len(set(names)): raise NewsConfigError('duplicate newsgroup')
  mappings=[(x.name,x.bbs_service,x.bbs_area) for x in self.groups if x.bbs_service]
  if len(mappings)!=len({x[1:] for x in mappings}): raise NewsConfigError('duplicate BBS mapping')
  if self.mode=='public_read_write' and not self.tls_cert_ref: raise NewsConfigError('public posting requires TLS configuration')
 def render(self):
  lines=[f'# UBB NNTP mode: {self.mode}',f'listen_port = {self.nntp_port}',f'group_count = {len(self.groups)}',f'retention_days = {self.retention.max_age_days}']
  if self.nntps_port: lines.append(f'nntps_port = {self.nntps_port}')
  return '\n'.join(lines)+'\n'
 def groups_render(self):
  return '\n'.join(f'{g.name}\t{g.description}' for g in sorted(self.groups,key=lambda x:x.name))+'\n'
 def to_safe_dict(self):
  return {'mode':self.mode,'internal_identity':self.internal_identity,'public_identity':self.public_identity,'nntp_port':self.nntp_port,'nntps_port':self.nntps_port,'group_count':len(self.groups),'adapter_count':len(self.adapters),'feed_count':len(self.feeds),'retention':{'max_age_days':self.retention.max_age_days,'max_articles':self.retention.max_articles,'max_bytes':self.retention.max_bytes}}

def write_atomic(path,content):
 target=os.path.abspath(os.fspath(path)); os.makedirs(os.path.dirname(target),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.ubb-news-',dir=os.path.dirname(target),text=True)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(content); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,target)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
