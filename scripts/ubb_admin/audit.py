import datetime,json,os,pathlib,secrets
class AuditLog:
 def __init__(self,path): self.path=pathlib.Path(path); self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
 def append(self,actor,role,action,target,result,source='web',message='',request_id=None,remote=None):
  x={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'actor':actor,'role':role,'action':action,'target':target,'result':result,'source':source,'message':message[:500],'request_id':request_id or secrets.token_urlsafe(12)}
  if remote:x['remote']=remote
  fd=os.open(self.path,os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o640)
  try:os.write(fd,(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()); os.fsync(fd)
  finally:os.close(fd)
  return x
 def read(self,limit=100):
  try:lines=self.path.read_text().splitlines()[-limit:]
  except FileNotFoundError:return []
  return [json.loads(x) for x in reversed(lines) if x]
