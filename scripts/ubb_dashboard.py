"""Small read-only HTTP presentation layer for the M8.1 observatory."""
from __future__ import annotations
import argparse, html, json, pathlib, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from ubb_registry.loader import load_registry
from ubb_observatory import Observatory

CSS="""body{font:15px system-ui,sans-serif;background:#10141b;color:#e9edf2;margin:0}main{max-width:1200px;margin:auto;padding:1.5rem}nav a{color:#9bd1ff;margin-right:1rem}.cards{display:flex;gap:1rem;flex-wrap:wrap}.card,table{background:#19212c;border:1px solid #334255;border-radius:6px;padding:1rem}.card{min-width:8rem}table{width:100%;border-collapse:collapse;padding:0}th,td{text-align:left;padding:.55rem;border-bottom:1px solid #334255}th{color:#b9c7d8}.badge{padding:.15rem .4rem;border-radius:3px;border:1px solid #718096}.critical{color:#ff9c9c}.warning{color:#ffd27d}.info{color:#9bd1ff}.muted{color:#a8b3c2}a{color:#9bd1ff}a:focus,button:focus{outline:2px solid #fff}code{font-family:monospace}h1,h2{margin-top:1.2rem}ul{padding-left:1.2rem}"""

def _jsonable(value):
    if hasattr(value,"to_dict"): return value.to_dict()
    if isinstance(value,tuple): return [_jsonable(x) for x in value]
    if isinstance(value,list): return [_jsonable(x) for x in value]
    if isinstance(value,dict): return {k:_jsonable(v) for k,v in value.items()}
    return value

class DashboardApp:
    def __init__(self, observatory): self.observatory=observatory
    def snapshot(self): return self.observatory.snapshot()
    def api(self,path):
        snap=self.snapshot(); data=snap.to_dict(); parts=[x for x in path.split("/") if x]
        if parts==["api","v1","status"]:
            services=data["services"]; return {"services":len(services),"running":sum(x["state"] in ("running","ready","maintenance") for x in services),"active_callers":sum(x["active_sessions"] for x in services),"maintenance":sum(x["maintenance"] for x in services),"failed":sum(x["state"]=="failed" for x in services),"alerts":len(data["alerts"])}
        if len(parts)>=3 and parts[:3]==["api","v1","services"]:
            if len(parts)==3:return data["services"]
            for item in data["services"]:
                if item["id"]==parts[3]: return item
            return None
        mapping={"sessions":"sessions","activity":"activity","alerts":"alerts","readiness":None,"artifacts":None,"backups":None,"hosts":"hosts"}
        if len(parts)==3 and parts[:2]==["api","v1"] and parts[2] in mapping:
            key=parts[2]
            if key=="readiness": return [{"service_id":x["id"],"release":x["release"],"readiness":x["readiness"]} for x in data["services"]]
            if key=="artifacts": return [{"service_id":x["id"],"artifact":x["artifact"]} for x in data["services"] if x["artifact"]]
            if key=="backups": return [{"service_id":x["id"],"backup":x["backup"]} for x in data["services"]]
            return data[key]
        return None
    def page(self,path):
        snap=self.snapshot(); data=snap.to_dict(); parts=[x for x in path.split("/") if x]
        title="Ultimate BBS Box Observatory"; body=""
        if path=="/" or path=="":
            s=data["services"]; body=f"<h1>{title}</h1><div class='cards'>"+"".join(f"<div class='card'><strong>{html.escape(k)}</strong><br><big>{v}</big></div>" for k,v in (("Services",len(s)),("Running",sum(x['state'] in ('running','ready','maintenance') for x in s)),("Active callers",sum(x['active_sessions'] for x in s)),("Maintenance",sum(x['maintenance'] for x in s)),("Failed",sum(x['state']=='failed' for x in s)),("Alerts",len(data['alerts']))))+"</div>"
            body+="<h2>Services</h2>"+self._service_table(s)
        elif len(parts)==2 and parts[0]=="service":
            item=next((x for x in data["services"] if x["id"]==parts[1]),None)
            if item is None:return None
            body=f"<h1>{html.escape(item['title'])}</h1><p><code>{html.escape(item['id'])}</code></p>"+self._definition(item)
        elif parts and parts[0] in ("services","sessions","activity","alerts","readiness","artifacts","backups","hosts"):
            key=parts[0]; body=f"<h1>{html.escape(key.title())}</h1>"
            if key=="services": body+=self._service_table(data["services"])
            elif key=="alerts": body+="<ul>"+"".join(f"<li class='{html.escape(x['severity'])}'><strong>{html.escape(x['severity'])}</strong> {html.escape(x['message'])} ({html.escape(x.get('service_id') or '')})</li>" for x in data['alerts'])+"</ul>"
            else:
                if key=="hosts": value=data["hosts"]
                elif key=="readiness": value=[{"service_id":x["id"],"release":x["release"],"readiness":x["readiness"]} for x in data["services"]]
                elif key=="artifacts": value=[{"service_id":x["id"],"artifact":x["artifact"]} for x in data["services"] if x["artifact"]]
                elif key=="backups": value=[{"service_id":x["id"],"backup":x["backup"]} for x in data["services"]]
                else: value=data.get(key,[])
                body+="<pre>"+html.escape(json.dumps(value,indent=2,sort_keys=True)) + "</pre>"
        else:return None
        nav="<nav><a href='/'>Overview</a><a href='/services'>Services</a><a href='/sessions'>Sessions</a><a href='/activity'>Activity</a><a href='/alerts'>Alerts</a><a href='/readiness'>Readiness</a><a href='/artifacts'>Artifacts</a><a href='/backups'>Backups</a><a href='/hosts'>Hosts</a></nav>"
        return "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>"+html.escape(title)+"</title><style>"+CSS+"</style></head><body><main>"+nav+body+"</main></body></html>"
    def _service_table(self,items):
        rows="".join(f"<tr><td><a href='/service/{html.escape(x['id'])}'>{html.escape(x['title'])}</a></td><td>{html.escape(x['type'])}</td><td>{html.escape(str(x['release'] or 'UNKNOWN'))}</td><td>{html.escape(str(x['policy'] or 'UNKNOWN'))}</td><td><span class='badge'>{html.escape(x['state'])}</span></td><td>{x['active_sessions']}</td><td>{html.escape(x['readiness'])}</td><td>{html.escape(x['host_health'])}</td></tr>" for x in items)
        return "<table><thead><tr><th>Name</th><th>Type</th><th>Release</th><th>Policy</th><th>State</th><th>Callers</th><th>Readiness</th><th>Host</th></tr></thead><tbody>"+rows+"</tbody></table>"
    def _definition(self,x):
        fields=[("Type",x['type']),("Integration",x.get('integration')),("Runtime",x.get('runtime')),("Policy",x.get('policy')),("Recommended",x.get('recommended_policy')),("State",x.get('state')),("Readiness",x.get('readiness')),("Profile",x.get('profile')),("Artifact",x.get('artifact')),("Backup",x.get('backup')),("Available releases",x.get('available_releases')),("Endpoint",x.get('endpoint'))]
        return "<dl>"+"".join(f"<dt><strong>{html.escape(k)}</strong></dt><dd><pre>{html.escape(json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else str(v))}</pre></dd>" for k,v in fields)+"</dl>"

class Handler(BaseHTTPRequestHandler):
    app=None
    def do_GET(self):
        path=urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                value=self.app.api(path)
                if value is None:self.send_error(404); return
                payload=json.dumps(_jsonable(value),sort_keys=True).encode()
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload); return
            page=self.app.page(path)
            if page is None:self.send_error(404); return
            payload=page.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Security-Policy","default-src 'self'; style-src 'unsafe-inline'"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
        except Exception: self.send_error(503,"observatory temporarily unavailable")
    def do_POST(self): self.send_error(405)
    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)
    def log_message(self,*args): pass

def main(argv=None):
    p=argparse.ArgumentParser(description="Read-only Ultimate BBS Box dashboard")
    p.add_argument("--bind",default="127.0.0.1"); p.add_argument("--port",type=int,default=8088); p.add_argument("--catalog",default="catalog"); p.add_argument("--archive-root"); p.add_argument("--supervisor-state"); p.add_argument("--router-state"); p.add_argument("--install-root",action="append",default=[])
    a=p.parse_args(argv); roots={x.split("=",1)[0]:x.split("=",1)[1] for x in a.install_root if "=" in x}; obs=Observatory(load_registry(a.catalog),archive_root=a.archive_root,supervisor_state=a.supervisor_state,router_state=a.router_state,install_roots=roots); Handler.app=DashboardApp(obs); server=ThreadingHTTPServer((a.bind,a.port),Handler); print(f"dashboard listening on http://{a.bind}:{a.port}"); server.serve_forever()
if __name__=="__main__": main()
