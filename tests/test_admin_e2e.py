import http.client, json, tempfile, threading, unittest, sys
from pathlib import Path
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ubb_admin import AuthStore, AuditLog
from ubb_dashboard import DashboardApp, Handler


class FakeActions:
    def __init__(self): self.calls=[]; self.errors={}; self.results={}
    def _ok(self, name, *args): self.calls.append((name,)+args); return {"action":name}
    def _gate(self, name, args, administrator=False):
        role=args[-1]
        if role not in (("administrator",) if administrator else ("operator", "administrator")): raise PermissionError("insufficient role")
        if name in self.errors: raise self.errors[name]
        if name in self.results: self.calls.append((name,)+args); return self.results[name]
        return self._ok(name,*args)
    def start(self,*a): return self._gate("start",a)
    def stop(self,*a): return self._gate("stop",a)
    def restart(self,*a): return self._gate("restart",a)
    def lifecycle(self,*a):
        if len(a)>1 and a[1] not in ("always_on", "on_demand"): raise ValueError("invalid lifecycle mode")
        return self._gate("lifecycle",a,True)
    def _job(self,*a):
        if len(a)>1 and a[1] != "job": raise ValueError("maintenance job is not registered")
        return self._gate("maintenance",a)
    def backup(self,*a): return self._gate("backup",a)
    def qualify(self,*a): return self._gate("qualify",a)
    def promote(self,*a): return self._gate("promote",a,True)
    def rollback(self,*a): return self._gate("rollback",a,True)


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

    def _session(self, user, password):
        cookie=self.login(user,password); return cookie, self.app.sessions.get(cookie.split("=",1)[1])

    def test_viewer_action_matrix_is_denied(self):
        cookie, session=self._session("viewer","v")
        actions=("start","stop","restart","maintenance","backup","qualify","lifecycle")
        bodies={"maintenance":"csrf=%s&job_id=job"%session["csrf"],"lifecycle":"csrf=%s&mode=always_on"%session["csrf"]}
        for action in actions:
            path="/api/v1/admin/services/demo/"+action
            self.assertEqual(self.req("POST",path,bodies.get(action,"csrf="+session["csrf"]),cookie=cookie)[0],403,action)

    def test_operator_and_administrator_action_matrix(self):
        operator, osession=self._session("operator","o"); admin, asession=self._session("admin","a")
        normal=("start","stop","restart","maintenance","backup","qualify")
        for action in normal:
            body="csrf="+osession["csrf"] + ("&job_id=job" if action=="maintenance" else "")
            self.assertEqual(self.req("POST","/api/v1/admin/services/demo/"+action,body,cookie=operator)[0],200,action)
        self.assertEqual(self.req("POST","/api/v1/admin/services/demo/lifecycle","csrf="+osession["csrf"]+"&mode=always_on",cookie=operator)[0],403)
        for action, body in (("lifecycle","csrf=%s&mode=always_on"%asession["csrf"]),("promote","csrf=%s&release=r"%asession["csrf"]),("rollback","csrf="+asession["csrf"])):
            path="/api/v1/admin/services/demo/"+action if action=="lifecycle" else "/api/v1/admin/integrations/amiexpress/"+action
            self.assertEqual(self.req("POST",path,body,cookie=admin)[0],200,action)

    def test_csrf_wrong_session_missing_and_get_are_safe(self):
        op, osession=self._session("operator","o"); other, _=self._session("admin","a")
        path="/api/v1/admin/services/demo/backup"
        for body, cookie in (("",op),("csrf=bad",op),("csrf="+osession["csrf"],other)):
            self.assertEqual(self.req("POST",path,body,cookie=cookie)[0],403)
        self.assertEqual(self.req("GET",path,cookie=op)[0],404)
        self.assertFalse(self.actions.calls)

    def test_dashboard_visibility_and_applicability(self):
        viewer=self.login("viewer","v"); operator=self.login("operator","o"); admin=self.login("admin","a")
        for cookie in (viewer,operator,admin): self.assertEqual(self.req("GET","/service/demo",cookie=cookie)[0],200)
        self.assertNotIn(b"Start",self.req("GET","/service/demo",cookie=viewer)[2])
        operator_body=self.req("GET","/service/demo",cookie=operator)[2]
        self.assertIn(b"Run maintenance",operator_body); self.assertNotIn(b"Set always_on",operator_body); self.assertNotIn(b"Promote candidate",operator_body)
        admin_body=self.req("GET","/service/demo",cookie=admin)[2]
        self.assertIn(b"Set always_on",admin_body); self.assertNotIn(b"Promote candidate",admin_body); self.assertNotIn(b"Rollback",admin_body)

    def test_read_api_auth_and_security_headers(self):
        self.assertEqual(self.req("GET","/api/v1/status")[0],401)
        cookie, session=self._session("viewer","v")
        status, headers, body=self.req("GET","/api/v1/status",cookie=cookie)
        self.assertEqual(status,200); self.assertIn("no-store",headers["Cache-Control"]); self.assertIn("nosniff",headers["X-Content-Type-Options"]); self.assertIn("frame-ancestors",headers["Content-Security-Policy"]); self.assertIn(b"services",body)
        login_headers=self.req("POST","/admin/login","username=operator&password=o")[1]
        self.assertIn("HttpOnly",login_headers["Set-Cookie"]); self.assertIn("SameSite=Strict",login_headers["Set-Cookie"]); self.assertIn("Max-Age=28800",login_headers["Set-Cookie"])

    def test_invalid_inputs_are_safe_and_audited(self):
        cookie, session=self._session("operator","o")
        for path, body in (("/api/v1/admin/services/demo/lifecycle","csrf=%s&mode=bogus"%session["csrf"]),("/api/v1/admin/services/demo/maintenance","csrf=%s&job_id=rm+-rf+%%2F"%session["csrf"])):
            self.assertIn(self.req("POST",path,body,cookie=cookie)[0],(404,422))
        self.assertNotIn(b"Traceback",self.req("POST","/api/v1/admin/services/demo/lifecycle","csrf=%s&mode=bogus"%session["csrf"],cookie=cookie)[2])

    def test_audit_page_is_read_only(self):
        cookie=self.login("viewer","v")
        self.assertEqual(self.req("GET","/admin/logout",cookie=cookie)[0],303)
        self.assertIn(self.req("GET","/api/v1/audit")[0],(401,))
        self.assertEqual(self.req("DELETE","/api/v1/audit",cookie=self.login("viewer","v"))[0],405)

    def test_backup_success_conflict_and_failure_are_independent(self):
        cookie, session=self._session("operator","o"); path="/api/v1/admin/services/demo/backup"; body="csrf="+session["csrf"]
        self.assertEqual(self.req("POST",path,body,cookie=cookie)[0],200)
        self.actions.errors["backup"]=RuntimeError("active callers prevent stopped backup")
        self.assertEqual(self.req("POST",path,body,cookie=cookie)[0],500)
        self.actions.errors["backup"]=ValueError("backup staging failed")
        self.assertEqual(self.req("POST",path,body,cookie=cookie)[0],422)
        results=[x["result"] for x in self.audit.read() if x["action"]=="backup"]
        self.assertEqual(results.count("success"),1); self.assertEqual(results.count("failure"),2)

    def test_qualification_and_release_actions_are_independently_audited(self):
        cookie, session=self._session("operator","o"); body="csrf=%s&integration=demo&release=fixture"%session["csrf"]
        self.assertEqual(self.req("POST","/api/v1/admin/services/demo/qualify",body,cookie=cookie)[0],200)
        self.actions.results["qualify"]={"result":"HUMAN_REQUIRED"}
        status,_,payload=self.req("POST","/api/v1/admin/services/demo/qualify",body,cookie=cookie)
        self.assertEqual(status,200); self.assertIn(b"HUMAN_REQUIRED",payload)
        self.actions.errors["qualify"]=ValueError("qualification failed")
        self.assertEqual(self.req("POST","/api/v1/admin/services/demo/qualify",body,cookie=cookie)[0],422)
        self.assertTrue(any(x["action"]=="qualify" and x["result"]=="failure" for x in self.audit.read()))

    def test_amiexpress_promote_and_rollback_roles_and_failures(self):
        admin, session=self._session("admin","a"); operator, osession=self._session("operator","o")
        promote="/api/v1/admin/integrations/amiexpress/promote"; rollback="/api/v1/admin/integrations/amiexpress/rollback"
        self.assertEqual(self.req("POST",promote,"csrf=%s&release=candidate"%session["csrf"],cookie=admin)[0],200)
        self.assertEqual(self.req("POST",promote,"csrf=%s&release=candidate"%osession["csrf"],cookie=operator)[0],403)
        self.actions.errors["promote"]=RuntimeError("candidate is not qualified")
        self.assertEqual(self.req("POST",promote,"csrf=%s&release=candidate"%session["csrf"],cookie=admin)[0],500)
        self.assertEqual(self.req("POST",rollback,"csrf="+session["csrf"],cookie=admin)[0],200)
        self.actions.errors["rollback"]=RuntimeError("no previous qualified release")
        self.assertEqual(self.req("POST",rollback,"csrf="+session["csrf"],cookie=admin)[0],500)

    def test_concurrent_start_and_backup_requests_are_audited(self):
        cookie, session=self._session("operator","o"); barrier=threading.Barrier(2); results=[]
        def call(path):
            barrier.wait(); results.append(self.req("POST",path,"csrf="+session["csrf"],cookie=cookie)[0])
        threads=[threading.Thread(target=call,args=("/api/v1/admin/services/demo/start",)),threading.Thread(target=call,args=("/api/v1/admin/services/demo/start",))]
        [t.start() for t in threads]; [t.join() for t in threads]; self.assertEqual(sorted(results),[200,200]); starts=[x for x in self.audit.read() if x["action"]=="start"]; self.assertEqual(len(starts),2); self.assertEqual(len({x["request_id"] for x in starts}),2)
        results=[]; threads=[threading.Thread(target=call,args=("/api/v1/admin/services/demo/backup",)),threading.Thread(target=call,args=("/api/v1/admin/services/demo/backup",))]
        [t.start() for t in threads]; [t.join() for t in threads]; self.assertEqual(sorted(results),[200,200]); backups=[x for x in self.audit.read() if x["action"]=="backup"]; self.assertEqual(len(backups),2); self.assertEqual(len({x["request_id"] for x in backups}),2)

    def test_concurrent_audit_lines_are_complete_json(self):
        barrier = threading.Barrier(16)
        errors = []

        def append(index):
            try:
                barrier.wait()
                self.audit.append("operator", "operator", "start", "demo", "success", request_id=f"request-{index}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=append, args=(index,)) for index in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        records = self.audit.read(limit=32)
        self.assertEqual(len(records), 16)
        self.assertEqual({record["request_id"] for record in records}, {f"request-{i}" for i in range(16)})

    def test_systemd_boundary_is_unprivileged_and_archive_read_only(self):
        unit=(Path(__file__).resolve().parents[1]/"systemd/ubb-dashboard.service").read_text()
        self.assertIn("User=ubb-dashboard",unit); self.assertIn("Group=ubb-dashboard",unit); self.assertIn("127.0.0.1",unit); self.assertIn("NoNewPrivileges=true",unit); self.assertIn("PrivateTmp=true",unit); self.assertIn("ProtectSystem=strict",unit); self.assertIn("ReadOnlyPaths=/srv/ultimate-bbs-box/archive",unit); self.assertNotIn("sudo",unit.lower()); self.assertNotIn("chmod 777",unit.lower())


if __name__ == "__main__": unittest.main()
