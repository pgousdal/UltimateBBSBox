"""Derived, bounded health and alert lifecycle evaluation."""
from __future__ import annotations
import json, os, pathlib, re, shutil
from datetime import datetime, timezone
from dataclasses import replace

def _now(value=None): return value or datetime.now(timezone.utc)

def health_summary(snapshot):
    counts={"HEALTHY":0,"DEGRADED":0,"UNHEALTHY":0,"UNKNOWN":0}
    for service in snapshot.services: counts[getattr(service,"health","UNKNOWN")]=counts.get(getattr(service,"health","UNKNOWN"),0)+1
    return counts

class MonitoringEngine:
    schema_version=1
    def __init__(self, state_root=None, *, now=None, retention=200, storage_roots=None, warning_free_percent=15, critical_free_percent=5, warning_free_bytes=10*1024**3, critical_free_bytes=2*1024**3, max_future_skew_seconds=300):
        self.root=pathlib.Path(state_root).resolve() if state_root else None; self.now=now or (lambda: datetime.now(timezone.utc)); self.retention=max(10,int(retention)); self.storage_roots=storage_roots or {}; self.thresholds=(warning_free_percent,critical_free_percent,warning_free_bytes,critical_free_bytes); self.max_future_skew_seconds=max_future_skew_seconds
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
    def storage(self):
        warning_pct,critical_pct,warning_bytes,critical_bytes=self.thresholds; result=[]
        for logical,path in sorted(self.storage_roots.items()):
            try:
                total,used,free=shutil.disk_usage(path); pct=(free/total*100) if total else 0
                health="CRITICAL" if pct<=critical_pct or free<=critical_bytes else ("WARNING" if pct<=warning_pct or free<=warning_bytes else "HEALTHY")
                result.append({"id":logical,"total_bytes":total,"used_bytes":used,"free_bytes":free,"free_percent":round(pct,3),"health":health,"observed_at":self.now().isoformat()})
            except OSError as exc: result.append({"id":logical,"health":"UNKNOWN","reason":type(exc).__name__})
        return tuple(result)
    def heartbeat_ingest(self, record):
        allowed={"schema_version","host_id","observed_at","received_at","health","source","summary","metrics"}; metrics_allowed={"load_1m","disk_free_bytes","uptime_seconds","service_count","running_service_count"}
        if not isinstance(record,dict) or set(record)-allowed or record.get("schema_version")!=1: raise ValueError("invalid heartbeat schema")
        host=str(record.get("host_id",""));
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}",host): raise ValueError("invalid host id")
        if record.get("health") not in ("HEALTHY","DEGRADED","UNHEALTHY"): raise ValueError("invalid heartbeat health")
        metrics=record.get("metrics") or {}
        if not isinstance(metrics,dict) or set(metrics)-metrics_allowed: raise ValueError("invalid heartbeat metrics")
        observed=datetime.fromisoformat(record["observed_at"].replace("Z","+00:00")); now=self.now()
        if observed > now.replace(tzinfo=observed.tzinfo)+__import__('datetime').timedelta(seconds=self.max_future_skew_seconds): raise ValueError("heartbeat is from the future")
        path=self.root/"observatory"/"heartbeats"/f"{host}.json" if self.root else None
        if path:
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o750); tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(record,sort_keys=True)+"\n"); os.replace(tmp,path)
        return record
    def heartbeat(self,host):
        if not self.root:return None
        try:return json.loads((self.root/"observatory"/"heartbeats"/f"{host}.json").read_text())
        except (OSError,ValueError):return None
