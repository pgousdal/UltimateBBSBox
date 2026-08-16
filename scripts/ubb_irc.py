"""Product-neutral IRC infrastructure intent for M6.5."""
from __future__ import annotations
import os,re,tempfile
from dataclasses import dataclass
class IRCConfigError(ValueError): pass
_ID=re.compile(r'^[a-z0-9][a-z0-9._-]*$'); _NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'); _CHAN=re.compile(r'^#[A-Za-z0-9][A-Za-z0-9._-]{0,49}$')
def ident(v,label='identifier'):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise IRCConfigError('invalid '+label)
 return v
def name(v,label='name'):
 if not isinstance(v,str) or not _NAME.fullmatch(v): raise IRCConfigError('invalid '+label)
 return v
def channel(v):
 if not isinstance(v,str) or not _CHAN.fullmatch(v) or any(c in v for c in '\r\n '): raise IRCConfigError('invalid channel')
 return v
def external(v):
 if not isinstance(v,str) or not v.startswith('/') or '\n' in v or '\r' in v: raise IRCConfigError('secret must be external reference')
 return v

@dataclass(frozen=True)
class IRCChannel:
 channel:str; description:str=''; enabled:bool=True; visibility:str='public'; invite_only:bool=False; moderated:bool=False; history:str='none'; max_users:int|None=None
 def __post_init__(self):
  object.__setattr__(self,'channel',channel(self.channel))
  if self.visibility not in ('public','private'): raise IRCConfigError('invalid channel visibility')
  if self.history not in ('none','bounded'): raise IRCConfigError('invalid history policy')
  if self.max_users is not None and self.max_users<=0: raise IRCConfigError('invalid max users')

@dataclass(frozen=True)
class IRCBridge:
 service:str; channel:str; bbs_area:str; mode:str='bidirectional'; visibility:str='private'; checkpoint_ref:str|None=None
 def __post_init__(self):
  ident(self.service,'BBS service'); channel(self.channel)
  if not self.bbs_area or '\n' in self.bbs_area or '\r' in self.bbs_area: raise IRCConfigError('invalid BBS area')
  if self.mode not in ('inbound_to_bbs','outbound_from_bbs','bidirectional','scheduled_bridge','native_irc'): raise IRCConfigError('invalid bridge mode')
  if self.visibility not in ('private','public'): raise IRCConfigError('invalid bridge visibility')
  if self.checkpoint_ref: external(self.checkpoint_ref)

@dataclass(frozen=True)
class IRCConfig:
 mode:str='private_only'; server_name:str='irc.ubb.internal'; network_name:str='UBB'; public_hostname:str|None=None; tls_cert_ref:str|None=None; tls_key_ref:str|None=None; channels:tuple[IRCChannel,...]=(); bridges:tuple[IRCBridge,...]=(); auth_secret_ref:str|None=None; oper_secret_ref:str|None=None; listen_tls:bool=True; listen_plain:bool=False; tls_port:int=6697; plain_port:int=6667; max_connections:int=500
 def __post_init__(self):
  if self.mode not in ('private_only','public'): raise IRCConfigError('invalid IRC mode')
  name(self.server_name,'server name'); name(self.network_name,'network name')
  if self.public_hostname: name(self.public_hostname,'public hostname')
  if self.mode=='public' and not self.tls_cert_ref: raise IRCConfigError('public IRC requires TLS')
  if self.tls_cert_ref: external(self.tls_cert_ref)
  if self.tls_key_ref: external(self.tls_key_ref)
  if self.auth_secret_ref: external(self.auth_secret_ref)
  if self.oper_secret_ref: external(self.oper_secret_ref)
  if not 1<=self.tls_port<=65535 or not 1<=self.plain_port<=65535: raise IRCConfigError('invalid listener port')
  if self.max_connections<=0: raise IRCConfigError('invalid connection limit')
  chans=[x.channel for x in self.channels]
  if len(chans)!=len(set(chans)): raise IRCConfigError('duplicate channel')
  mapping=[(x.service,x.channel) for x in self.bridges]
  if len(mapping)!=len(set(mapping)): raise IRCConfigError('duplicate bridge mapping')
  for b in self.bridges:
   if b.visibility=='public' and self.mode!='public': raise IRCConfigError('public bridge requires public IRC mode')
 def render(self):
  lines=[f'servername {self.server_name}',f'networkname {self.network_name}',f'mode {self.mode}',f'maxconnections {self.max_connections}']
  if self.listen_tls: lines.append(f'tls-listen {self.tls_port}')
  if self.listen_plain: lines.append(f'plain-listen {self.plain_port}')
  if self.tls_cert_ref: lines.append('tls-cert '+self.tls_cert_ref)
  return '\n'.join(lines)+'\n'
 def to_safe_dict(self):
  return {'mode':self.mode,'server_name':self.server_name,'network_name':self.network_name,'public_hostname':self.public_hostname,'tls':bool(self.tls_cert_ref and self.tls_key_ref),'tls_port':self.tls_port,'plain_listener':self.listen_plain,'plain_port':self.plain_port,'channel_count':len(self.channels),'bridge_count':len(self.bridges),'max_connections':self.max_connections}
def write_atomic(path,content):
 target=os.path.abspath(os.fspath(path)); os.makedirs(os.path.dirname(target),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.ubb-irc-',dir=os.path.dirname(target),text=True)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(content); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,target)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
