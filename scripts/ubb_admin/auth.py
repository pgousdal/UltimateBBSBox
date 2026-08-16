from __future__ import annotations
import base64,hashlib,hmac,json,os,pathlib,secrets,threading,time
ROLES={"viewer":0,"operator":1,"administrator":2}
class AuthStore:
 def __init__(self,path): self.path=pathlib.Path(path); self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
 def _load(self):
  try:return json.loads(self.path.read_text())
  except FileNotFoundError:return {"users":{}}
 def _save(self,d):
  t=self.path.with_suffix('.tmp'); t.write_text(json.dumps(d,sort_keys=True,indent=2)+'\n'); os.chmod(t,0o600); os.replace(t,self.path); os.chmod(self.path,0o600)
 @staticmethod
 def hash_password(p):
  s=secrets.token_bytes(16); v=hashlib.pbkdf2_hmac('sha256',p.encode(),s,240000); return 'pbkdf2_sha256$240000$'+base64.urlsafe_b64encode(s).decode()+'$'+base64.urlsafe_b64encode(v).decode()
 @staticmethod
 def verify(p,e):
  try: _,i,s,v=e.split('$',3); x=hashlib.pbkdf2_hmac('sha256',p.encode(),base64.urlsafe_b64decode(s),int(i)); return hmac.compare_digest(x,base64.urlsafe_b64decode(v))
  except Exception:return False
 def add(self,u,p,role='viewer'):
  if role not in ROLES: raise ValueError('invalid role')
  d=self._load(); d['users'][u]={'hash':self.hash_password(p),'role':role,'display_name':u,'enabled':True}; self._save(d)
 def disable(self,u):
  d=self._load()
  if u not in d.get('users',{}): raise KeyError(u)
  d['users'][u]['enabled']=False; self._save(d)
 def authenticate(self,u,p):
  x=self._load().get('users',{}).get(u); return x if x and x.get('enabled',True) and self.verify(p,x.get('hash','')) else None
 def list(self): return [{'username':k,'role':v.get('role'),'enabled':v.get('enabled',True)} for k,v in sorted(self._load().get('users',{}).items())]
class SessionStore:
 def __init__(self,lifetime=28800): self.items={}; self.lifetime=lifetime; self.lock=threading.RLock()
 def create(self,u,r):
  t=secrets.token_urlsafe(32); c=secrets.token_urlsafe(32)
  with self.lock:self.items[t]={'username':u,'role':r,'csrf':c,'expires':time.time()+self.lifetime}
  return t
 def get(self,t):
  with self.lock:
   x=self.items.get(t)
   if not x or x['expires']<time.time(): self.items.pop(t,None); return None
   return dict(x)
 def remove(self,t):
  with self.lock:self.items.pop(t,None)
