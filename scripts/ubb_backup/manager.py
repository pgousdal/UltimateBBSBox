"""Product-neutral, staged living-state backup manager."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, pathlib, shutil, tarfile, tempfile, uuid
from dataclasses import dataclass, asdict

class BackupError(Exception): pass
@dataclass(frozen=True)
class BackupManifest:
    backup_id:str; target_id:str; release:str|None; created_at:str; payload:str; payload_sha256:str
    components:tuple; excluded:tuple; size:int; consistency:str; verification:str="READY"
    def to_dict(self): return asdict(self)
@dataclass(frozen=True)
class RestorePlan:
    backup_id:str; target_id:str; components:tuple; destination_root:str; requires_verified_backup:bool=True
    overwrite_live_state:bool=True; preserves_software:bool=True
    def to_dict(self): return asdict(self)

def _hash(path):
 d=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): d.update(b)
 return d.hexdigest()

class BackupManager:
 def __init__(self,root,declarations=None): self.root=pathlib.Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True,mode=0o750); self.declarations=declarations or {}
 def declare(self,target,source_root,include=("config","users","messages","files_metadata","uploads"),exclude=("software","cache","logs","tmp"),consistency="stopped"):
  self.declarations[target]={"source":pathlib.Path(source_root).resolve(),"include":tuple(include),"exclude":tuple(exclude),"consistency":consistency}
 def _decl(self,target):
  try:return self.declarations[target]
  except KeyError as e:raise BackupError(f"backup target is not registered: {target}") from e
 def create(self,target,release=None,active_sessions=0,consistency=None):
  d=self._decl(target); mode=consistency or d['consistency']
  if mode not in ('stopped','live_best_effort'):raise BackupError('invalid consistency mode')
  if mode=='stopped' and active_sessions:raise BackupError('active callers prevent stopped-consistency backup')
  if not d['source'].is_dir():raise BackupError('registered living-state root is missing')
  stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'); bid=f"{target}-{stamp}-{uuid.uuid4().hex[:8]}"; staging=pathlib.Path(tempfile.mkdtemp(prefix='.backup-',dir=self.root)); payload=staging/'payload.tar'
  try:
   with tarfile.open(payload,'w') as tf:
    for src in sorted(d['source'].rglob('*')):
     rel=src.relative_to(d['source'])
     if src.is_symlink() or rel.is_absolute() or '..' in rel.parts or any(p in d['exclude'] for p in rel.parts):
      if src.is_symlink():raise BackupError(f'unsafe symlink in living state: {rel}')
      continue
     if src.is_file():
      info=tf.gettarinfo(str(src),arcname=rel.as_posix()); info.mtime=0; info.uid=info.gid=0; info.uname=info.gname=''
      with src.open('rb') as f:tf.addfile(info,f)
   digest=_hash(payload); final=self.root/bid; final.mkdir(mode=0o750); shutil.move(str(payload),final/'payload.tar')
   manifest=BackupManifest(bid,target,release,dt.datetime.now(dt.timezone.utc).isoformat(),'payload.tar',digest,tuple(d['include']),tuple(d['exclude']), (final/'payload.tar').stat().st_size,mode)
   (final/'manifest.json').write_text(json.dumps(manifest.to_dict(),sort_keys=True,indent=2)+'\n'); (final/'backup-manifest.json').write_text(json.dumps(manifest.to_dict(),sort_keys=True,indent=2)+'\n'); shutil.rmtree(staging,ignore_errors=True)
   return manifest
  except Exception:
   shutil.rmtree(staging,ignore_errors=True); raise
 def list(self,target=None):
  out=[]
  for p in sorted(self.root.iterdir()):
   m=p/'manifest.json'
   if not m.is_file():continue
   try:x=json.loads(m.read_text());
   except (OSError,json.JSONDecodeError):continue
   if target is None or x.get('target_id')==target:out.append(x)
  return out
 def show(self,bid):
  p=self.root/bid/'manifest.json'
  if not p.is_file():raise BackupError('backup not found')
  return json.loads(p.read_text())
 def verify(self,bid):
  m=self.show(bid); payload=self.root/bid/m['payload'];
  if not payload.is_file() or _hash(payload)!=m['payload_sha256']:raise BackupError('backup checksum failed')
  with tarfile.open(payload) as tf:
   for x in tf.getmembers():
    n=pathlib.PurePosixPath(x.name)
    if n.is_absolute() or '..' in n.parts or x.issym() or x.islnk():raise BackupError('unsafe backup payload')
  return {**m,'verification':'PASS'}
 def restore_plan(self,bid,target,destination_root):
  m=self.show(bid)
  if m['target_id']!=target:raise BackupError('backup target mismatch')
  return RestorePlan(bid,target,tuple(m['components']),str(pathlib.Path(destination_root).resolve()))
 def restore(self,bid,target,destination_root,verified=False):
  if not verified:self.verify(bid)
  plan=self.restore_plan(bid,target,destination_root); dest=pathlib.Path(plan.destination_root).resolve(); dest.mkdir(parents=True,exist_ok=True)
  with tarfile.open(self.root/bid/'payload.tar') as tf:
   for member in tf.getmembers():
    n=pathlib.PurePosixPath(member.name)
    if n.is_absolute() or '..' in n.parts or member.issym() or member.islnk():raise BackupError('unsafe restore payload')
   tf.extractall(dest,filter='data')
  return {'backup_id':bid,'target_id':target,'restored':True,'software_preserved':True}
