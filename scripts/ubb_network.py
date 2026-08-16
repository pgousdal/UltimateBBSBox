"""Typed, deterministic DNS/NTP configuration rendering for M6.1."""
from __future__ import annotations
import ipaddress,re,os,tempfile
from dataclasses import dataclass

class NetworkConfigError(ValueError): pass
LABEL=re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
def domain(value):
    value=value.lower().rstrip('.')
    if not value or len(value)>253 or any(not LABEL.fullmatch(x) for x in value.split('.')): raise NetworkConfigError('invalid DNS domain')
    return value
def address(value):
    try:return str(ipaddress.ip_address(value))
    except ValueError as exc: raise NetworkConfigError('invalid IP address') from exc
def network(value):
    try:return str(ipaddress.ip_network(value,strict=False))
    except ValueError as exc: raise NetworkConfigError('invalid trusted network') from exc

@dataclass(frozen=True)
class DNSConfig:
    internal_domain:str='ubb.internal'; listen:tuple[str,...]=('127.0.0.1',); trusted_networks:tuple[str,...]=('127.0.0.0/8',); recursion:bool=True; upstreams:tuple[str,...]=(); records:tuple[dict,...]=()
    def __post_init__(self):
        object.__setattr__(self,'internal_domain',domain(self.internal_domain)); object.__setattr__(self,'listen',tuple(address(x) for x in self.listen)); object.__setattr__(self,'trusted_networks',tuple(network(x) for x in self.trusted_networks)); names=set()
        for r in self.records:
            name=domain(r['name']); typ=r['type']; value=r['value']; key=(name,typ)
            if key in names: raise NetworkConfigError('duplicate DNS record')
            names.add(key)
            if typ in ('A','AAAA'): address(value)
            elif typ=='CNAME': domain(value)
            else: raise NetworkConfigError('unsupported DNS record type')
    def render(self):
        lines=['server:','  interface: '+', '.join(self.listen)]
        for cidr in self.trusted_networks: lines.append('  access-control: '+cidr+' allow')
        lines += ['  access-control: 0.0.0.0/0 refuse','  access-control: ::/0 refuse','  do-ip4: yes','  do-ip6: yes']
        if not self.recursion: lines.append('  do-not-query-localhost: no')
        for r in sorted(self.records,key=lambda x:(x['name'],x['type'],x['value'])): lines.append(f"local-data: \"{domain(r['name'])} {r['type']} {r['value']}\"")
        return '\n'.join(lines)+'\n'

def write_atomic(path, content):
    """Atomically publish generated daemon configuration."""
    target=os.path.abspath(os.fspath(path)); parent=os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.ubb-network-', dir=parent, text=True)
    try:
        with os.fdopen(fd,'w', encoding='utf-8') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

@dataclass(frozen=True)
class NTPConfig:
    mode:str='client_only'; trusted_networks:tuple[str,...]=('127.0.0.0/8',); upstreams:tuple[str,...]=('pool.ntp.org',)
    def __post_init__(self):
        if self.mode not in ('client_only','client_and_server'): raise NetworkConfigError('invalid NTP mode')
        object.__setattr__(self,'trusted_networks',tuple(network(x) for x in self.trusted_networks))
    def render(self):
        lines=['pool '+x+' iburst' for x in self.upstreams]
        if self.mode=='client_and_server': lines += ['allow '+x for x in self.trusted_networks]
        return '\n'.join(lines)+'\n'
