"""Read-only aggregation of M1-M7 authoritative state."""
from __future__ import annotations
import json, pathlib, socket, shutil
from datetime import datetime, timezone
from .models import ActivityEvent, Alert, ObservatorySnapshot, ServiceSummary

def _read_json(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError): return None

class Observatory:
    def __init__(self, registry, *, archive_root=None, supervisor_state=None, router_state=None,
                 install_roots=None, now=None):
        self.registry=registry; self.archive_root=pathlib.Path(archive_root).resolve() if archive_root else None
        self.supervisor_state=pathlib.Path(supervisor_state).resolve() if supervisor_state else None
        self.router_state=pathlib.Path(router_state).resolve() if router_state else None
        self.install_roots={k:pathlib.Path(v).resolve() for k,v in (install_roots or {}).items()}
        self.now=now or (lambda: datetime.now(timezone.utc))
        self.degraded=[]

    def _instance(self, service_id):
        if not self.supervisor_state: return None
        value=_read_json(self.supervisor_state/"instances"/f"{service_id}.json")
        if value is None and (self.supervisor_state/"instances"/f"{service_id}.json").exists(): self.degraded.append("supervisor")
        return value

    def _qualification(self, integration_id, artifact_id):
        root=self.install_roots.get(integration_id)
        if not root: return "UNKNOWN", None
        candidates=[root/"qualification"/f"{artifact_id}.json", root/"qualification"/"latest.json"]
        doc=next((x for x in (_read_json(p) for p in candidates) if x is not None), None)
        if not doc: return "UNKNOWN", None
        statuses=[x.get("status") for x in doc.get("results", [])]
        if "FAIL" in statuses: state="NOT_READY"
        elif "BLOCKED" in statuses: state="BLOCKED"
        elif "HUMAN_REQUIRED" in statuses: state="READY_WITH_HUMAN_REQUIREMENTS"
        elif statuses and all(x in ("PASS", "SKIP") for x in statuses): state="READY"
        else: state="UNKNOWN"
        return state, doc

    def _artifact(self, integration_doc):
        if not self.archive_root: return None
        for item in integration_doc.get("artifacts", []):
            aid=item.get("artifact_id"); meta=_read_json(self.archive_root/"metadata"/f"{aid}.json")
            if meta:
                return {"id":aid, "filename":meta.get("artifact",{}).get("original_filename"),
                        "sha256":meta.get("artifact",{}).get("sha256"), "verified":meta.get("preservation",{}).get("status")=="READY",
                        "rights":meta.get("rights",{}).get("status"), "source":meta.get("provenance",{}).get("source_url")}
        return None

    def _backup(self, integration_id):
        root=self.install_roots.get(integration_id)
        if not root: return None
        paths=list(root.glob("backup*/backup-manifest.json"))+list(root.glob("backups/*/backup-manifest.json"))
        paths=sorted(paths,key=lambda p:p.stat().st_mtime if p.exists() else 0,reverse=True)
        if not paths: return None
        doc=_read_json(paths[0]); return {"status":"verified" if doc else "UNKNOWN", "manifest":str(paths[0]), "created_at":doc.get("created_at") if doc else None, "coverage":len(doc.get("files",[])) if doc else None}

    def services(self):
        result=[]
        for service in self.registry.list_services():
            resolved=self.registry.resolve(service.id); integ=resolved.get("integration") or {}; endpoint=resolved["endpoint"]
            instance=self._instance(service.id) or {}
            integration_id=service.integration_id; root=self.install_roots.get(integration_id) if integration_id else None
            artifact=self._artifact(integ)
            release=(integ.get("release") or integ.get("version") or service.document.get("service",{}).get("version"))
            readiness, qualification=self._qualification(integration_id, artifact["id"] if artifact else "") if integration_id else ("UNKNOWN",None)
            deployment=_read_json(root/"deployment"/"amiexpress-current.json") if root else None
            backup=self._backup(integration_id) if integration_id else None
            lifecycle=service.document.get("lifecycle",{}); state=instance.get("state","unknown")
            maintenance=state=="maintenance" or bool(instance.get("maintenance_results")) and state in ("running","ready")
            releases=[]
            try:
                from ubb_integrations.registry import IntegrationRegistry
                trusted=IntegrationRegistry.defaults().get(integration_id) if integration_id else None
                for rel in getattr(trusted, "releases", {}).values():
                    releases.append({"key":rel.key,"version":rel.version,"artifact_id":rel.artifact_id,"sha256":rel.sha256})
            except Exception: pass
            result.append(ServiceSummary(service.id,service.title,service.type,integration_id,integ.get("runtime"),endpoint,
                lifecycle.get("mode"),integ.get("recommended_lifecycle"),state,int(instance.get("active_session_count",0)),maintenance,
                readiness,release,integ.get("profile") or integ.get("default_profile"),artifact,deployment,
                tuple(releases), backup, "UNKNOWN" if endpoint.get("location")=="remote" else "LOCAL", False))
        return tuple(sorted(result,key=lambda x:x.id))

    def sessions(self):
        if not self.router_state: return ()
        path=self.router_state/"sessions.json"
        data=_read_json(path)
        if data is None:
            path=self.router_state/"events.jsonl"
            if not path.exists(): return ()
            active={}
            try:
                for raw in path.read_text(encoding="utf-8").splitlines():
                    item=json.loads(raw); sid=item.get("session_id")
                    if sid: active[sid]=item
            except (OSError, json.JSONDecodeError): self.degraded.append("router")
            data=list(active.values())
        return tuple({k:v for k,v in item.items() if k not in ("password","credentials","content","terminal_content")} for item in data)

    def activity(self, limit=100):
        events=[]
        sources=(("supervisor", self.supervisor_state/"events.jsonl" if self.supervisor_state else None),
                 ("router", self.router_state/"events.jsonl" if self.router_state else None))
        for source,path in sources:
            if not path or not path.exists(): continue
            try:
                lines=path.read_text(encoding="utf-8").splitlines()[-max(limit*3,100):]
                for raw in lines:
                    item=json.loads(raw); service=item.get("service") or item.get("target_service")
                    old=item.get("old_state"); new=item.get("new_state"); et=item.get("event_type") or (f"service_{new}" if new else "event")
                    msg=f"{et} -> {service}" if service else et
                    events.append(ActivityEvent(item.get("timestamp", ""),source,et,"info",msg,service,
                        {k:v for k,v in item.items() if k not in ("timestamp","service","target_service","origin_service","error","password","credentials","content","terminal_content")}))
            except (OSError, json.JSONDecodeError): self.degraded.append(source)
        return tuple(sorted(events,key=lambda x:(x.timestamp,x.source,x.event_type,x.service_id or ""),reverse=True)[:limit])

    def alerts(self, services=None):
        services=services or self.services(); result=[]
        for item in services:
            if item.state=="failed": result.append(Alert(f"failed:{item.id}","critical",item.id,"service is failed"))
            if item.policy=="always_on" and item.state not in ("running","ready","maintenance","unknown"):
                result.append(Alert(f"always-on:{item.id}","critical",item.id,"always_on service is not running"))
            if item.readiness in ("NOT_READY","BLOCKED"):
                result.append(Alert(f"readiness:{item.id}","warning",item.id,f"qualification is {item.readiness}"))
            if item.artifact and not item.artifact.get("verified"):
                result.append(Alert(f"artifact:{item.id}","critical",item.id,"preservation artifact is not verified"))
            if item.backup is None:
                result.append(Alert(f"backup:{item.id}","warning",item.id,"no backup evidence recorded"))
            if item.deployment and item.deployment.get("candidate"):
                result.append(Alert(f"update:{item.id}","info",item.id,"candidate deployment is available",{"candidate":item.deployment["candidate"]}))
        return tuple(sorted(result,key=lambda x:( {"critical":0,"warning":1,"info":2}.get(x.severity,3),x.id)))

    def hosts(self):
        return ({"id":"local","location":"local","health":"LOCAL","services":[x.id for x in self.services() if x.host_health=="LOCAL"]},)

    def snapshot(self, activity_limit=100):
        services=self.services(); return ObservatorySnapshot(services,self.sessions(),self.activity(activity_limit),self.alerts(services),self.hosts(),tuple(sorted(set(self.degraded))))
