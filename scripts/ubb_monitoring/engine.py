"""Derived, bounded health and alert lifecycle evaluation."""
from __future__ import annotations
import json, os, pathlib
from datetime import datetime, timezone
from dataclasses import replace

def _now(value=None): return value or datetime.now(timezone.utc)

def health_summary(snapshot):
    counts={"HEALTHY":0,"DEGRADED":0,"UNHEALTHY":0,"UNKNOWN":0}
    for service in snapshot.services: counts[getattr(service,"health","UNKNOWN")]=counts.get(getattr(service,"health","UNKNOWN"),0)+1
    return counts

class MonitoringEngine:
    schema_version=1
    def __init__(self, state_root=None, *, now=None, retention=200):
        self.root=pathlib.Path(state_root).resolve() if state_root else None; self.now=now or (lambda: datetime.now(timezone.utc)); self.retention=max(10,int(retention))
    def _path(self): return self.root/"observatory"/"alerts.json" if self.root else None
    def _load(self):
        path=self._path()
        if not path: return {}
        try:
            data=json.loads(path.read_text()); return data.get("alerts",{}) if isinstance(data,dict) else {}
        except (OSError,ValueError,TypeError): return {}
    def _save(self, records):
        path=self._path()
        if not path:return
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o750); tmp=path.with_suffix(".tmp")
        payload={"schema_version":self.schema_version,"alerts":records}; tmp.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n"); os.replace(tmp,path)
    def evaluate(self, snapshot):
        now=self.now().isoformat(); old=self._load(); active={}
        for item in snapshot.services:
            if item.health=="UNHEALTHY": active[f"health:{item.id}"]={"severity":"critical","service_id":item.id,"summary":"service health is unhealthy"}
            elif item.health=="DEGRADED": active[f"health:{item.id}"]={"severity":"warning","service_id":item.id,"summary":"service health is degraded"}
            if item.backup is None: active[f"backup:{item.id}"]={"severity":"warning","service_id":item.id,"summary":"no backup evidence recorded"}
            if item.readiness in ("NOT_READY","BLOCKED"): active[f"qualification:{item.id}"]={"severity":"warning","service_id":item.id,"summary":f"qualification is {item.readiness}"}
        for host in snapshot.hosts:
            if host.get("health")=="UNKNOWN": active[f"host:{host.get('id')}"]={"severity":"warning","host_id":host.get("id"),"summary":"remote host has no current telemetry"}
        records={}
        for key, condition in active.items():
            prior=old.get(key,{})
            records[key]={**condition,"alert_id":key,"state":"ACTIVE","first_seen":prior.get("first_seen",now),"last_seen":now,"occurrence_count":int(prior.get("occurrence_count",0))+1,"cleared_at":None}
        for key, prior in old.items():
            if key not in active:
                if prior.get("state")=="ACTIVE": prior={**prior,"state":"CLEARED","cleared_at":now}
                records[key]=prior
        cleared=[(k,v) for k,v in records.items() if v.get("state")=="CLEARED"]
        if len(cleared)>self.retention:
            for key,_ in sorted(cleared,key=lambda x:x[1].get("cleared_at") or "")[:-self.retention]: records.pop(key,None)
        self._save(records)
        return tuple(records.values())
    def alerts(self, snapshot, *, active=None, severity=None, service=None):
        values=list(self.evaluate(snapshot));
        if active is True: values=[x for x in values if x.get("state")=="ACTIVE"]
        if active is False: values=[x for x in values if x.get("state")=="CLEARED"]
        if severity: values=[x for x in values if x.get("severity")==severity]
        if service: values=[x for x in values if x.get("service_id")==service]
        return tuple(sorted(values,key=lambda x:(x.get("severity",""),x.get("alert_id",""))))
