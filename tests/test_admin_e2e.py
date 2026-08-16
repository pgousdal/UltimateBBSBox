import http.client, json, tempfile, threading, unittest, sys
from pathlib import Path
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ubb_admin import AuthStore, AuditLog
from ubb_dashboard import DashboardApp, Handler


class FakeActions:
    def __init__(self): self.calls=[]
    def _ok(self, name, *args): self.calls.append((name,)+args); return {"action":name}
    def start(self,*a): return self._ok("start",*a)
    def stop(self,*a): return self._ok("stop",*a)
    def restart(self,*a): return self._ok("restart",*a)
    def lifecycle(self,*a):
        if a[-1] != "administrator": raise PermissionError("insufficient role")
        return self._ok("lifecycle",*a)
    def _job(self,*a): return self._ok("maintenance",*a)
    def backup(self,*a): return self._ok("backup",*a)
    def qualify(self,*a): return self._ok("qualify",*a)
    def promote(self,*a): return self._ok("promote",*a)
    def rollback(self,*a): return self._ok("rollback",*a)


class AdminE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        users=root/"users.json"; self.auth=AuthStore(users)
        self.auth.add("viewer","v","viewer"); self.auth.add("operator","o","operator"); self.auth.add("admin","a","administrator")
        item={"id":"demo","title":"Demo","type":"bbs","integration":"demo","runtime":"fake","endpoint":{},"policy":"on_demand","recommended_policy":"always_on","state":"stopped","active_sessions":0,"maintenance":False,"readiness":"READY","release":"1","profile":None,"artifact":None,"deployment":None,"available_releases":[],"backup":None,"host_health":"LOCAL","attention":False,"maintenance_jobs":["job"]}
        self.obs=SimpleNamespace(snapshot=lambda: SimpleNamespace(to_dict=lambda:{"services":[item],"sessions":[],"activity":[],"alerts":[],"hosts":[],"degraded_sources":[]}))
        self.actions=FakeActions(); self.audit=AuditLog(root/"audit.jsonl")
        self.app=DashboardApp(self.obs,auth_store=self.auth,audit=self.audit,actions=self.actions,require_auth=True)
        Handler.app=self.app; self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler); self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start(); self.host,self.port=self.server.server_address
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()
    def req(self,method,path,body=None,cookie=None):
        c=http.client.HTTPConnection(self.host,self.port); headers={}
        if cookie: headers["Cookie"]=cookie
        if body is not None: headers["Content-Type"]="application/x-www-form-urlencoded"
        c.request(method,path,body=body,headers=headers); r=c.getresponse(); data=r.read(); return r.status,dict(r.getheaders()),data
    def login(self,user,password):
        status,headers,_=self.req("POST","/admin/login",f"username={user}&password={password}"); self.assertEqual(status,303); return headers["Set-Cookie"].split(";",1)[0]
    def test_auth_roles_csrf_and_audit_end_to_end(self):
        status,_,_=self.req("GET","/"); self.assertEqual(status,401)
        viewer=self.login("viewer","v"); status,_,body=self.req("GET","/service/demo",cookie=viewer); self.assertEqual(status,200); self.assertNotIn(b"Start",body)
        operator=self.login("operator","o"); status,_,body=self.req("GET","/service/demo",cookie=operator); self.assertEqual(status,200); self.assertIn(b"Start",body); self.assertNotIn(b"Set always_on",body)
        admin=self.login("admin","a"); status,_,body=self.req("GET","/service/demo",cookie=admin); self.assertIn(b"Set always_on",body)
        self.assertEqual(self.req("POST","/api/v1/admin/services/demo/start","",cookie=operator)[0],403)
        csrf=self.app.sessions.get(operator.split("=",1)[1])["csrf"]
        status,_,_=self.req("POST","/api/v1/admin/services/demo/start",f"csrf={csrf}",cookie=operator); self.assertEqual(status,200)
        self.assertEqual(self.req("GET","/api/v1/admin/services/demo/start",cookie=operator)[0],404)
        status,_,_=self.req("POST","/api/v1/admin/services/demo/maintenance",f"csrf={csrf}&job_id=job",cookie=operator); self.assertEqual(status,200)
        status,_,_=self.req("POST","/api/v1/admin/services/demo/backup",f"csrf={csrf}",cookie=operator); self.assertEqual(status,200)
        status,_,_=self.req("POST","/api/v1/admin/services/demo/lifecycle",f"csrf={csrf}&mode=always_on",cookie=operator); self.assertEqual(status,403)
        acsrf=self.app.sessions.get(admin.split("=",1)[1])["csrf"]
        status,_,_=self.req("POST","/api/v1/admin/services/demo/lifecycle",f"csrf={acsrf}&mode=always_on",cookie=admin); self.assertEqual(status,200)
        audit=self.audit.read(); self.assertTrue(any(x["action"]=="backup" and x["result"]=="success" for x in audit)); self.assertTrue(any(x["message"]=="csrf rejected" for x in audit))
        raw=json.dumps(audit); self.assertNotIn(csrf,raw); self.assertNotIn(acsrf,raw); self.assertNotIn(operator,raw)


if __name__ == "__main__": unittest.main()
