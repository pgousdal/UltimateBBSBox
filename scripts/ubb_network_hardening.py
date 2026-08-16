"""Consolidated, read-only M6 inventory and readiness checks."""
from __future__ import annotations
import hashlib, ipaddress
from dataclasses import dataclass
from pathlib import Path
from ubb_registry.loader import load_registry

class NetworkHardeningError(ValueError): pass
READINESS=('READY','READY_WITH_HUMAN_REQUIREMENTS','DEGRADED','NOT_READY','BLOCKED')
@dataclass(frozen=True)
class Listener:
    service:str; protocol:str; host:str; port:int; exposure:str='private'; tls:bool=False
    def key(self): return (self.protocol,self.host,self.port)
@dataclass
class NetworkInventory:
    services:tuple[dict,...]; listeners:tuple[Listener,...]; dependencies:dict; qualification:dict
    @classmethod
    def from_catalog(cls,root='catalog'):
        reg=load_registry(root); items=[]; listeners=[]
        for sid,s in sorted(reg.services.items()):
            ep=reg.endpoints[s.endpoint_id]; doc=s.document
            items.append({'id':sid,'type':s.type,'title':doc['service']['title'],'lifecycle':doc['lifecycle']['mode'],'exposure':'private' if not doc['exposure'].get('main_menu') else 'overlay'})
            if ep.document.get('port'):
                listeners.append(Listener(sid,ep.type,ep.document.get('host','*'),ep.document['port'],'private',ep.document.get('protocol') in ('smtp',)))
        deps={'mail-edge':['dns-core','mail-core','edge-1'],'nntp-core':['dns-core','edge-1'],'irc-core':['dns-core','edge-1'],'ftn-mailer':['dns-core','edge-1'],'offline-exchange':[],'dns-core':[],'ntp-core':[]}
        deps={k:v for k,v in deps.items() if k in {x['id'] for x in items}}
        qual={x['id']:{'state':'READY_WITH_HUMAN_REQUIREMENTS','human_required':['real daemon/peer qualification']} for x in items}
        return cls(tuple(items),tuple(listeners),deps,qual)
    def validate(self):
        seen={}
        for listener in self.listeners:
            if listener.key() in seen: raise NetworkHardeningError(f'listener collision: {listener.service} and {seen[listener.key()]}')
            seen[listener.key()]=listener.service
        self._check_cycles(); return True
    def _check_cycles(self):
        visiting=set(); done=set()
        def visit(n):
            if n in visiting: raise NetworkHardeningError('dependency cycle')
            if n in done:return
            visiting.add(n)
            for d in self.dependencies.get(n,[]):
                if d in self.dependencies: visit(d)
            visiting.remove(n); done.add(n)
        for n in self.dependencies: visit(n)
    def summary(self): return {'service_count':len(self.services),'listener_count':len(self.listeners),'readiness':self.qualification,'public_listeners':sum(x.exposure=='edge_public' for x in self.listeners)}
    def digest(self): return hashlib.sha256(repr((self.services,self.listeners,self.dependencies)).encode()).hexdigest()
def secret_inventory():
    return [{'id':'tls-mail','service':'mail-edge','purpose':'SMTP TLS','required':False,'configured':False},{'id':'tls-irc','service':'irc-core','purpose':'public IRC TLS','required':False,'configured':False},{'id':'ftn-peer','service':'ftn-mailer','purpose':'BinkP peer passwords','required':False,'configured':False}]
def firewall_intent(): return {'default_policy':'deny','established_related':'allow','overlay':'allow_trusted','public_listeners':'explicit_only','open_resolver':False,'public_ntp':False,'open_relay':False,'anonymous_ftn':False}
