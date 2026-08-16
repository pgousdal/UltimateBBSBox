"""Bounded QWK/Blue Wave exchange metadata and safe archive staging."""
from __future__ import annotations
import hashlib,os,re,tempfile,zipfile
from dataclasses import dataclass
class ExchangeError(ValueError): pass
FORMATS=('qwk','bluewave'); PURPOSES=('user_offline_mail','system_exchange'); STATES=('preparing','ready','delivered','received','importing','imported','rejected','failed')
_ID=re.compile(r'^[a-z0-9][a-z0-9._-]*$'); _ENC=('CP437','CP850','ISO-8859-1','UTF-8','adapter_defined')
def ident(v,label='identifier'):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise ExchangeError('invalid '+label)
 return v
def filename(v):
 if not isinstance(v,str) or '/' in v or '\\' in v or '..' in v or '\r' in v or '\n' in v or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,11}',v): raise ExchangeError('invalid packet filename')
 return v
@dataclass(frozen=True)
class ExchangeFormat:
 name:str; export:bool=True; reply_import:bool=True; system_exchange:bool=True; compression:tuple[str,...]=('zip',); encoding:str='CP437'; extensions:tuple[str,...]=()
 def __post_init__(self):
  if self.name not in FORMATS: raise ExchangeError('unsupported format')
  if self.encoding not in _ENC: raise ExchangeError('invalid encoding')
  if any(x not in ('none','zip') for x in self.compression): raise ExchangeError('compression not allow-listed')
@dataclass(frozen=True)
class AreaMapping:
 service:str; area:str; external_id:str; format:str='qwk'; conference:int|None=None
 def __post_init__(self):
  ident(self.service,'service');
  if not self.area or '\n' in self.area or '\r' in self.area: raise ExchangeError('invalid BBS area')
  ident(self.external_id,'external area')
  if self.format not in FORMATS: raise ExchangeError('unsupported mapping format')
  if self.conference is not None and not 1<=self.conference<=65535: raise ExchangeError('invalid conference')
@dataclass(frozen=True)
class ExchangeAdapter:
 service:str; capabilities:tuple[str,...]; mode:str='external_adapter'; checkpoint_ref:str|None=None
 def __post_init__(self):
  ident(self.service,'service');
  if self.mode not in ('native','external_adapter'): raise ExchangeError('invalid adapter mode')
  allowed={'enumerate_areas','export_messages','import_replies','resolve_user','checkpoint','mark_exported','duplicate_check','system_export','system_import'}
  if any(x not in allowed for x in self.capabilities): raise ExchangeError('invalid adapter capability')
  if self.checkpoint_ref and (not self.checkpoint_ref.startswith('/') or '\n' in self.checkpoint_ref): raise ExchangeError('invalid checkpoint reference')
@dataclass(frozen=True)
class PacketManifest:
 packet_id:str; format:str; purpose:str; source_service:str; created_at:str; direction:str; state:str='preparing'; user_ref:str|None=None; encoding:str='CP437'; compression:str='zip'; file_size:int=0; checksum:str|None=None; message_count:int=0; checkpoint:str|None=None; origin:str='ubb'; schema_version:int=1
 def __post_init__(self):
  ident(self.packet_id,'packet id'); ident(self.source_service,'source service')
  if self.format not in FORMATS or self.purpose not in PURPOSES or self.state not in STATES: raise ExchangeError('invalid packet enum')
  if self.direction not in ('inbound','outbound'): raise ExchangeError('invalid packet direction')
  if self.encoding not in _ENC or self.compression not in ('none','zip'): raise ExchangeError('invalid packet encoding/compression')
  if self.file_size<0 or self.message_count<0: raise ExchangeError('invalid packet bounds')
  if self.user_ref and ('password' in self.user_ref.lower() or '\n' in self.user_ref): raise ExchangeError('unsafe user reference')
 def safe(self): return {'packet_id':self.packet_id,'format':self.format,'purpose':self.purpose,'source_service':self.source_service,'state':self.state,'direction':self.direction,'file_size':self.file_size,'message_count':self.message_count,'encoding':self.encoding,'compression':self.compression,'checkpoint':self.checkpoint,'origin':self.origin,'schema_version':self.schema_version}
@dataclass(frozen=True)
class ExchangeConfig:
 formats:tuple[ExchangeFormat,...]=(ExchangeFormat('qwk'),ExchangeFormat('bluewave'))
 mappings:tuple[AreaMapping,...]=(); adapters:tuple[ExchangeAdapter,...]=(); max_packet_bytes:int=50*1024*1024; max_messages:int=10000; max_files:int=64; max_unpacked_bytes:int=200*1024*1024
 def __post_init__(self):
  ids=[(x.service,x.external_id,x.format) for x in self.mappings]
  if len(ids)!=len(set(ids)): raise ExchangeError('duplicate area mapping')
  if min(self.max_packet_bytes,self.max_messages,self.max_files,self.max_unpacked_bytes)<=0: raise ExchangeError('invalid exchange bounds')
 def safe_summary(self): return {'formats':[x.name for x in self.formats],'mapping_count':len(self.mappings),'adapter_count':len(self.adapters),'max_packet_bytes':self.max_packet_bytes,'max_messages':self.max_messages}
def packet_checksum(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()
def safe_extract_zip(source,destination,max_files=64,max_bytes=200*1024*1024):
 destination=os.path.abspath(os.fspath(destination)); os.makedirs(destination,exist_ok=True); total=0
 with zipfile.ZipFile(source) as z:
  infos=z.infolist()
  if len(infos)>max_files: raise ExchangeError('archive file-count limit exceeded')
  for info in infos:
   name=info.filename
   if name.startswith('/') or '..' in name.split('/') or '\\' in name: raise ExchangeError('unsafe archive path')
   if info.is_dir(): continue
   total+=info.file_size
   if total>max_bytes: raise ExchangeError('archive size limit exceeded')
   target=os.path.abspath(os.path.join(destination,name))
   if not target.startswith(destination+os.sep): raise ExchangeError('archive escape')
  staging=tempfile.mkdtemp(prefix='.ubb-exchange-',dir=destination)
  try:
   z.extractall(staging)
   for root,dirs,files in os.walk(staging):
    for f in files:
     src=os.path.join(root,f); rel=os.path.relpath(src,staging); dst=os.path.join(destination,rel); os.makedirs(os.path.dirname(dst),exist_ok=True); os.replace(src,dst)
  finally:
   import shutil; shutil.rmtree(staging,ignore_errors=True)
