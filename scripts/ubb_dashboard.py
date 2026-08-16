"""Small read-only HTTP presentation layer for the M8.1 observatory."""
from __future__ import annotations
import argparse, html, json, pathlib, sys
import secrets, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from ubb_registry.loader import load_registry
from ubb_observatory import Observatory
from ubb_admin import AuthStore, SessionStore, AuditLog, AdminActionService
from ubb_integrations.registry import IntegrationRegistry
from ubb_supervisor import Supervisor
from ubb_backup import BackupManager, BackupError
from ubb_monitoring import MonitoringEngine, health_summary

CSS="""body{font:15px system-ui,sans-serif;background:#10141b;color:#e9edf2;margin:0}main{max-width:1200px;margin:auto;padding:1.5rem}nav a{color:#9bd1ff;margin-right:1rem}.cards{display:flex;gap:1rem;flex-wrap:wrap}.card,table{background:#19212c;border:1px solid #334255;border-radius:6px;padding:1rem}.card{min-width:8rem}table{width:100%;border-collapse:collapse;padding:0}th,td{text-align:left;padding:.55rem;border-bottom:1px solid #334255}th{color:#b9c7d8}.badge{padding:.15rem .4rem;border-radius:3px;border:1px solid #718096}.critical{color:#ff9c9c}.warning{color:#ffd27d}.info{color:#9bd1ff}.muted{color:#a8b3c2}a{color:#9bd1ff}a:focus,button:focus{outline:2px solid #fff}code{font-family:monospace}h1,h2{margin-top:1.2rem}ul{padding-left:1.2rem}"""

def _jsonable(value):
    if hasattr(value,"to_dict"): return value.to_dict()
    if isinstance(value,tuple): return [_jsonable(x) for x in value]
    if isinstance(value,list): return [_jsonable(x) for x in value]
    if isinstance(value,dict): return {k:_jsonable(v) for k,v in value.items()}
    return value

class DashboardApp:
    def __init__(self, observatory, auth_store=None, sessions=None, audit=None, actions=None, require_auth=False, monitoring=None):
        self.observatory=observatory; self.auth=auth_store; self.sessions=sessions or SessionStore(); self.audit=audit; self.actions=actions; self.require_auth=require_auth; self.monitoring=monitoring; self.failed={}
    def authenticate(self,token): return self.sessions.get(token) if token else None
    def snapshot(self): return self.observatory.snapshot()
    def login(self,user,password,remote=''):
        key=(remote,user); now=time.time(); blocked=self.failed.get(key,0)
        if blocked>now: return None
        record=self.auth.authenticate(user,password) if self.auth else None
        if not record:
            self.failed[key]=now+min(300,2**min(8,int(self.failed.get(key,now)-now+1))); return None
        self.failed.pop(key,None); return self.sessions.create(user,record['role'])
    def api(self,path,query=None):
        snap=self.snapshot(); data=snap.to_dict(); parts=[x for x in path.split("/") if x]
        if parts==["api","v1","status"]:
            services=data["services"]; return {"services":len(services),"running":sum(x["state"] in ("running","ready","maintenance") for x in services),"active_callers":sum(x["active_sessions"] for x in services),"maintenance":sum(x["maintenance"] for x in services),"failed":sum(x["state"]=="failed" for x in services),"alerts":len(data["alerts"])}
        if parts==["api","v1","health"]: return health_summary(snap)
        if len(parts)==4 and parts[:3]==["api","v1","hosts"]:
            return next((x for x in data["hosts"] if x.get("id")==parts[3]),None)
        if len(parts)>=3 and parts[:3]==["api","v1","services"]:
            if len(parts)==3:return data["services"]
            for item in data["services"]:
                if item["id"]==parts[3]: return item
            return None
        if parts[:3]==["api","v1","alerts"]:
            alerts=list(self.monitoring.alerts(snap) if self.monitoring else (x.to_dict() for x in snap.alerts))
            query=query or {}
            if query.get("severity"): alerts=[x for x in alerts if x.get("severity")==query["severity"][0]]
            if query.get("service"): alerts=[x for x in alerts if x.get("service_id")==query["service"][0]]
            if query.get("host"): alerts=[x for x in alerts if x.get("host_id")==query["host"][0]]
            if query.get("state"): alerts=[x for x in alerts if x.get("state","ACTIVE")==query["state"][0]]
            if len(parts)==3:return alerts
            return next((x for x in alerts if x.get("alert_id",x.get("id"))==parts[3]),None)
        mapping={"sessions":"sessions","activity":"activity","alerts":"alerts","readiness":None,"artifacts":None,"backups":None,"hosts":"hosts"}
        if len(parts)==3 and parts[:2]==["api","v1"] and parts[2] in mapping:
            key=parts[2]
            if key=="readiness": return [{"service_id":x["id"],"release":x["release"],"readiness":x["readiness"]} for x in data["services"]]
            if key=="artifacts": return [{"service_id":x["id"],"artifact":x["artifact"]} for x in data["services"] if x["artifact"]]
            if key=="backups": return [{"service_id":x["id"],"backup":x["backup"]} for x in data["services"]]
            return data[key]
        return None
    def page(self,path,session=None):
        snap=self.snapshot(); data=snap.to_dict(); data["alerts"]=list(self.monitoring.alerts(snap) if self.monitoring else [x.to_dict() for x in getattr(snap,"alerts",())]); parts=[x for x in path.split("/") if x]
        title="Ultimate BBS Box Observatory"; body=""
        if path=="/" or path=="":
            s=data["services"]; body=f"<h1>{title}</h1><div class='cards'>"+"".join(f"<div class='card'><strong>{html.escape(k)}</strong><br><big>{v}</big></div>" for k,v in (("Services",len(s)),("Running",sum(x['state'] in ('running','ready','maintenance') for x in s)),("Active callers",sum(x['active_sessions'] for x in s)),("Maintenance",sum(x['maintenance'] for x in s)),("Failed",sum(x['state']=='failed' for x in s)),("Alerts",len(data['alerts']))))+"</div>"
            body+="<h2>Services</h2>"+self._service_table(s)
        elif len(parts)==2 and parts[0]=="service":
            item=next((x for x in data["services"] if x["id"]==parts[1]),None)
            if item is None:return None
            body=f"<h1>{html.escape(item['title'])}</h1><p><code>{html.escape(item['id'])}</code></p>"+self._definition(item)
            if session and self.require_auth: body += self._controls(item,session)
        elif len(parts)==2 and parts[0]=="hosts":
            host=next((x for x in data["hosts"] if x.get("id")==parts[1]),None)
            if host is None:return None
            body=f"<h1>Host {html.escape(parts[1])}</h1><pre>{html.escape(json.dumps(host,indent=2,sort_keys=True))}</pre>"
        elif parts and parts[0] in ("services","sessions","activity","alerts","readiness","artifacts","backups","hosts","audit"):
            key=parts[0]; body=f"<h1>{html.escape(key.title())}</h1>"
            if key=="services": body+=self._service_table(data["services"])
            elif key=="alerts": body+="<ul>"+"".join(f"<li class='{html.escape(x.get('severity',''))}'><strong>{html.escape(x.get('severity',''))}</strong> {html.escape(x.get('summary',x.get('message','')))} ({html.escape(x.get('service_id') or x.get('host_id') or '')}) state={html.escape(x.get('state','ACTIVE'))}</li>" for x in data['alerts'])+"</ul>"
            else:
                if key=="hosts": value=data["hosts"]
                elif key=="readiness": value=[{"service_id":x["id"],"release":x["release"],"readiness":x["readiness"]} for x in data["services"]]
                elif key=="artifacts": value=[{"service_id":x["id"],"artifact":x["artifact"]} for x in data["services"] if x["artifact"]]
                elif key=="backups": value=[{"service_id":x["id"],"backup":x["backup"]} for x in data["services"]]
                elif key=="audit": value=self.audit.read() if self.audit else []
                else: value=data.get(key,[])
                body+="<pre>"+html.escape(json.dumps(value,indent=2,sort_keys=True)) + "</pre>"
        else:return None
        nav="<nav><a href='/'>Overview</a><a href='/services'>Services</a><a href='/sessions'>Sessions</a><a href='/activity'>Activity</a><a href='/alerts'>Alerts</a><a href='/readiness'>Readiness</a><a href='/artifacts'>Artifacts</a><a href='/backups'>Backups</a><a href='/hosts'>Hosts</a><a href='/audit'>Audit</a></nav>"
        return "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>"+html.escape(title)+"</title><style>"+CSS+"</style></head><body><main>"+nav+body+"</main></body></html>"
    def _controls(self,item,session):
        csrf=html.escape(session['csrf']); sid=html.escape(item['id']); role=session['role']; forms=[]
        if role in ('operator','administrator'):
            for action,label in (('start','Start'),('stop','Stop'),('restart','Restart'),('backup','Backup'),('qualify','Qualify')):
                forms.append(f"<form method='post' action='/api/v1/admin/services/{sid}/{action}'><input type='hidden' name='csrf' value='{csrf}'><button>{label}</button></form>")
            if item.get('maintenance_jobs'):
                forms.append(f"<form method='post' action='/api/v1/admin/services/{sid}/maintenance'><input type='hidden' name='csrf' value='{csrf}'><input name='job_id' placeholder='registered job'><button>Run maintenance</button></form>")
        if role=='administrator':
            for mode in ('always_on','on_demand'):
                forms.append(f"<form method='post' action='/api/v1/admin/services/{sid}/lifecycle'><input type='hidden' name='csrf' value='{csrf}'><input type='hidden' name='mode' value='{mode}'><button>Set {mode}</button></form>")
            deployment=item.get('deployment') or {}
            if item.get('integration')=='amiexpress-amiga' and deployment.get('candidates'):
                forms.append(f"<form method='post' action='/api/v1/admin/integrations/amiexpress/promote'><input type='hidden' name='csrf' value='{csrf}'><input name='release' placeholder='candidate release'><button>Promote candidate</button></form>")
            if item.get('integration')=='amiexpress-amiga' and deployment.get('previous'):
                forms.append(f"<form method='post' action='/api/v1/admin/integrations/amiexpress/rollback'><input type='hidden' name='csrf' value='{csrf}'><button>Rollback</button></form>")
        return "<h2>Admin actions</h2><div class='cards'>"+''.join(forms)+"</div>"
    def _service_table(self,items):
        rows="".join(f"<tr><td><a href='/service/{html.escape(x['id'])}'>{html.escape(x['title'])}</a></td><td>{html.escape(x['type'])}</td><td>{html.escape(str(x['release'] or 'UNKNOWN'))}</td><td>{html.escape(str(x['policy'] or 'UNKNOWN'))}</td><td><span class='badge'>{html.escape(x['state'])}</span></td><td>{x['active_sessions']}</td><td>{html.escape(x['readiness'])}</td><td>{html.escape(x['host_health'])}</td></tr>" for x in items)
        return "<table><thead><tr><th>Name</th><th>Type</th><th>Release</th><th>Policy</th><th>State</th><th>Callers</th><th>Readiness</th><th>Host</th></tr></thead><tbody>"+rows+"</tbody></table>"
    def _definition(self,x):
        fields=[("Type",x['type']),("Integration",x.get('integration')),("Runtime",x.get('runtime')),("Policy",x.get('policy')),("Recommended",x.get('recommended_policy')),("Lifecycle",x.get('state')),("Health",x.get('health','UNKNOWN')),("Readiness",x.get('readiness')),("Host",x.get('host_health')),("Profile",x.get('profile')),("Artifact",x.get('artifact')),("Backup",x.get('backup')),("Available releases",x.get('available_releases')),("Endpoint",x.get('endpoint'))]
        return "<dl>"+"".join(f"<dt><strong>{html.escape(k)}</strong></dt><dd><pre>{html.escape(json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else str(v))}</pre></dd>" for k,v in fields)+"</dl>"

class Handler(BaseHTTPRequestHandler):
    app=None
    def do_GET(self):
        path=urlparse(self.path).path
        try:
            if path=='/admin/login': self._login_page(); return
            token=self._cookie('ubb_admin');
            if self.app.require_auth and not self.app.authenticate(token): self._unauthorized(); return
            if path=='/admin/logout': self._logout(token); return
            if path=='/api/v1/audit': self._audit(); return
            if path.startswith("/api/"):
                value=self.app.api(path,parse_qs(urlparse(self.path).query))
                if value is None:self.send_error(404); return
                payload=json.dumps(_jsonable(value),sort_keys=True).encode()
                self._send(200,payload,'application/json; charset=utf-8'); return
            page=self.app.page(path,self.app.authenticate(token) if self.app.require_auth else None)
            if page is None:self.send_error(404); return
            payload=page.encode(); self._send(200,payload,'text/html; charset=utf-8'); return
        except Exception: self.send_error(503,"observatory temporarily unavailable")
    def do_POST(self):
        path=urlparse(self.path).path
        if not self.app.require_auth:
            self.send_error(405); return
        if path=='/admin/login':
            form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); user=form.get('username',[''])[0]; password=form.get('password',[''])[0]; token=self.app.login(user,password,self.client_address[0])
            if not token:
                if self.app.audit:self.app.audit.append(user,'unknown','login','admin','denied',remote=self.client_address[0],message='invalid credentials')
                self._send(401,'<h1>Login failed</h1>'); return
            if self.app.audit:self.app.audit.append(user,'unknown','login','admin','success',remote=self.client_address[0])
            secure='; Secure' if getattr(self.app,'secure_cookies',False) else ''
            self._send(303,'',headers={'Location':'/','Set-Cookie':f'ubb_admin={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}' }); return
        token=self._cookie('ubb_admin'); session=self.app.authenticate(token)
        if not session:self._unauthorized(); return
        if path.startswith('/api/v1/admin/'):
            body=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()) if self.headers.get('Content-Length') else {}
            supplied=self.headers.get('X-CSRF-Token') or body.get('csrf',[''])[0]
            if not supplied or not secrets.compare_digest(supplied,session['csrf']):
                parts=[x for x in path.split('/') if x]; action=parts[-1] if parts else 'unknown'; target=parts[-2] if len(parts)>4 else 'admin'
                if self.app.audit:self.app.audit.append(session['username'],session['role'],action,target,'denied',remote=self.client_address[0],message='csrf rejected')
                self._send(403,'CSRF rejected'); return
            self._action(path,session,body); return
        self.send_error(405)
    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)
    def log_message(self,*args): pass
    def _cookie(self,name):
        for bit in self.headers.get('Cookie','').split(';'):
            if bit.strip().startswith(name+'='): return bit.strip().split('=',1)[1]
        return None
    def _send(self,code,body,ctype='text/html; charset=utf-8',headers=None):
        data=body.encode() if isinstance(body,str) else body; self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Cache-Control','no-store'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'");
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def _unauthorized(self): self._send(401,'<h1>Authentication required</h1>')
    def _login_page(self): self._send(200,"<!doctype html><title>UBB admin login</title><h1>Admin login</h1><form method='post' action='/admin/login'><label>User <input name='username' autofocus></label><label>Password <input type='password' name='password'></label><button>Sign in</button></form>")
    def _logout(self,token):
        if token:self.app.sessions.remove(token)
        self._send(303,'',headers={'Location':'/admin/login','Set-Cookie':'ubb_admin=; Max-Age=0; HttpOnly; SameSite=Strict'})
    def _audit(self): self._send(200,json.dumps(self.app.audit.read() if self.app.audit else [],sort_keys=True).encode(),'application/json; charset=utf-8')
    def _action(self,path,session,form=None):
        parts=[x for x in path.split('/') if x]; action=parts[-1]; target=parts[-2] if len(parts)>4 else 'integration'; result='failure'; message=''
        try:
            if not self.app.actions: raise RuntimeError('action service unavailable')
            form=form or {}
            if action=='start': value=self.app.actions.start(target,session['role'])
            elif action=='stop': value=self.app.actions.stop(target,session['role'])
            elif action=='restart': value=self.app.actions.restart(target,session['role'])
            elif action=='maintenance': value=self.app.actions._job(target,form.get('job_id',[''])[0],session['role'])
            elif action=='backup': value=self.app.actions.backup(target,session['role'])
            elif action=='qualify': value=self.app.actions.qualify(form.get('integration',[target])[0],form.get('release',[''])[0],session['role'])
            elif action=='promote': value=self.app.actions.promote(form.get('integration',['amiexpress-amiga'])[0],form.get('release',[''])[0],session['role'])
            elif action=='rollback': value=self.app.actions.rollback(form.get('integration',['amiexpress-amiga'])[0],session['role'])
            elif action=='lifecycle': value=self.app.actions.lifecycle(target,form.get('mode',[''])[0],session['role'])
            else: raise ValueError('unsupported action')
            result='success'; message='action delegated'; self._send(200,json.dumps({'result':result,'value':_jsonable(value)},sort_keys=True),'application/json; charset=utf-8')
        except PermissionError as exc: result='denied'; message=str(exc); self._send(403,json.dumps({'error':message}),'application/json; charset=utf-8')
        except ValueError as exc: message=str(exc); self._send(422,json.dumps({'error':message}),'application/json; charset=utf-8')
        except (NotImplementedError, BackupError) as exc: message=str(exc); self._send(409,json.dumps({'error':message or 'action unavailable'}),'application/json; charset=utf-8')
        except Exception as exc: message=str(exc); self._send(500,json.dumps({'error':'action failed'}),'application/json; charset=utf-8')
        finally:
            if self.app.audit:self.app.audit.append(session['username'],session['role'],action,target,result,source='web',message=message,remote=self.client_address[0])

def main(argv=None):
    p=argparse.ArgumentParser(description="Read-only Ultimate BBS Box dashboard")
    p.add_argument("--bind",default="127.0.0.1"); p.add_argument("--port",type=int,default=8088); p.add_argument("--catalog",default="catalog"); p.add_argument("--archive-root"); p.add_argument("--supervisor-state"); p.add_argument("--router-state"); p.add_argument("--install-root",action="append",default=[]); p.add_argument("--auth-users",default="/etc/ultimate-bbs-box/admin-users.json"); p.add_argument("--audit-path",default="/var/log/ultimate-bbs-box/admin-audit.jsonl")
    a=p.parse_args(argv); roots={x.split("=",1)[0]:x.split("=",1)[1] for x in a.install_root if "=" in x}; registry=load_registry(a.catalog); backup_root=pathlib.Path(a.archive_root).parent/'backups' if a.archive_root else pathlib.Path('/var/lib/ultimate-bbs-box/backups'); obs=Observatory(registry,archive_root=a.archive_root,backup_root=backup_root,supervisor_state=a.supervisor_state,router_state=a.router_state,install_roots=roots); supervisor=Supervisor(registry,a.supervisor_state) if a.supervisor_state else None
    backup=BackupManager(backup_root)
    if supervisor:
        for service in registry.services.values():
            integration=IntegrationRegistry.defaults().get(service.integration_id) if service.integration_id else None; root=roots.get(service.integration_id)
            if integration and root: backup.declare(service.id,root,**getattr(integration,'backup_components',{}))
    def backup_action(service):
        active=len(supervisor.instances[service].sessions) if supervisor and service in supervisor.instances else 0
        return backup.create(service,active_sessions=active).to_dict()
    actions=AdminActionService(supervisor=supervisor,integration_registry=IntegrationRegistry.defaults(),backup=backup_action,install_roots={k:pathlib.Path(v) for k,v in roots.items()},archive_root=a.archive_root); monitor_root=(pathlib.Path(a.supervisor_state).parent if a.supervisor_state else pathlib.Path('/var/lib/ultimate-bbs-box')); Handler.app=DashboardApp(obs,auth_store=AuthStore(a.auth_users),audit=AuditLog(a.audit_path),actions=actions,require_auth=True,monitoring=MonitoringEngine(monitor_root,storage_roots={'state':monitor_root,'backups':backup_root,'archive':pathlib.Path(a.archive_root) if a.archive_root else monitor_root/'archive'})); server=ThreadingHTTPServer((a.bind,a.port),Handler); print(f"dashboard listening on http://{a.bind}:{a.port}"); server.serve_forever()
if __name__=="__main__": main()
