"""Typed, deterministic Internet-mail intent for M6.3.

This module renders configuration intent; it never sends mail or edits a live MTA.
"""
from __future__ import annotations
import ipaddress, re, os, tempfile
from dataclasses import dataclass, field

class MailConfigError(ValueError): pass
_LABEL=re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LOCAL=re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
def domain(v):
    v=str(v).lower().rstrip('.')
    if not v or len(v)>253 or any(not _LABEL.fullmatch(x) for x in v.split('.')): raise MailConfigError('invalid mail domain')
    return v
def addr(v):
    try: return str(ipaddress.ip_address(v))
    except ValueError as e: raise MailConfigError('invalid public address') from e
def email(v):
    if not isinstance(v,str) or v.count('@')!=1: raise MailConfigError('invalid recipient')
    local, d=v.rsplit('@',1)
    if not local or len(local)>64 or not _LOCAL.fullmatch(local): raise MailConfigError('invalid local part')
    return local+'@'+domain(d)
def external_ref(v):
    if not isinstance(v,str) or not v.startswith('/') or '\n' in v or '\r' in v: raise MailConfigError('secret must be external path reference')
    return v

@dataclass(frozen=True)
class MailDomain:
    name:str; route:str='local'; enabled:bool=True
    def __post_init__(self):
        object.__setattr__(self,'name',domain(self.name))
        if self.route not in ('local',) and (not isinstance(self.route,str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*',self.route)): raise MailConfigError('invalid domain route')

@dataclass(frozen=True)
class Recipient:
    address:str; service:str; local_identity:str; enabled:bool=True
    def __post_init__(self):
        object.__setattr__(self,'address',email(self.address))
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*',self.service): raise MailConfigError('invalid recipient service')
        if not self.local_identity or not _LOCAL.fullmatch(self.local_identity): raise MailConfigError('invalid local identity')

@dataclass(frozen=True)
class Adapter:
    service:str; mode:str; capabilities:tuple[str,...]=()
    def __post_init__(self):
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*',self.service): raise MailConfigError('invalid adapter service')
        if self.mode not in ('native_smtp','mailbox_bridge','batch_exchange','scheduled_exchange'): raise MailConfigError('invalid adapter mode')
        allowed={'inbound_delivery','outbound_collection','native_smtp','batch_import','batch_export','scheduled_exchange','address_mapping'}
        if any(x not in allowed for x in self.capabilities): raise MailConfigError('invalid adapter capability')

@dataclass(frozen=True)
class MailConfig:
    domains:tuple[MailDomain,...]=()
    recipients:tuple[Recipient,...]=()
    aliases:tuple[tuple[str,str],...]=()
    edge_ips:tuple[str,...]=()
    outbound_mode:str='direct_mx'
    smarthost:str|None=None
    smarthost_secret_ref:str|None=None
    dkim_selector:str='ubb'
    dkim_key_ref:str|None=None
    dkim_domains:tuple[str,...]=()
    dmarc_policy:str='none'
    tls_cert_ref:str|None=None
    tls_key_ref:str|None=None
    submission_enabled:bool=False
    trusted_relay_networks:tuple[str,...]=()
    catch_all:bool=False
    max_message_size:int=25*1024*1024
    def __post_init__(self):
        names=[x.name for x in self.domains]
        if len(names)!=len(set(names)): raise MailConfigError('duplicate mail domain')
        if self.outbound_mode not in ('direct_mx','smarthost'): raise MailConfigError('invalid outbound mode')
        if self.outbound_mode=='smarthost' and (not self.smarthost or not self.smarthost_secret_ref): raise MailConfigError('smarthost requires host and external secret')
        if self.outbound_mode=='direct_mx' and self.smarthost_secret_ref: raise MailConfigError('unused smarthost secret')
        if self.smarthost_secret_ref: external_ref(self.smarthost_secret_ref)
        if self.dmarc_policy not in ('none','quarantine','reject'): raise MailConfigError('invalid DMARC policy')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}',self.dkim_selector): raise MailConfigError('invalid DKIM selector')
        for x in self.edge_ips: addr(x)
        for x in self.dkim_domains: domain(x)
        if self.dkim_key_ref: external_ref(self.dkim_key_ref)
        if self.tls_cert_ref: external_ref(self.tls_cert_ref)
        if self.tls_key_ref: external_ref(self.tls_key_ref)
        for n in self.trusted_relay_networks:
            try: ipaddress.ip_network(n,strict=False)
            except ValueError as e: raise MailConfigError('invalid relay network') from e
        if self.max_message_size<=0: raise MailConfigError('invalid message size')
        addresses=[x.address for x in self.recipients]
        if len(addresses)!=len(set(addresses)): raise MailConfigError('duplicate recipient')
        amap={a for a,_ in self.aliases};
        if len(amap)!=len(self.aliases): raise MailConfigError('duplicate alias')
        for a,b in self.aliases:
            a=email(a); b=email(b)
            if a==b or b in {x[0] for x in self.aliases}: raise MailConfigError('alias loop')
    def mx_records(self, host='mail.example.invalid'):
        host=domain(host); return tuple(f'{d.name} MX 10 {host}.' for d in sorted(self.domains,key=lambda x:x.name) if d.enabled)
    def spf_record(self, host='mail.example.invalid'):
        if not self.edge_ips: raise MailConfigError('SPF requires configured edge IP')
        parts=['v=spf1']+[('ip4:'+x if ':' not in x else 'ip6:'+x) for x in self.edge_ips]
        if self.smarthost: parts.append('include:'+domain(self.smarthost))
        return ' '.join(parts)+' -all'
    def dmarc_record(self, d): return f'_dmarc.{domain(d)} TXT "v=DMARC1; p={self.dmarc_policy}"'
    def render(self):
        lines=['myhostname = mail.example.invalid','smtpd_tls_security_level = may','smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination',f'message_size_limit = {self.max_message_size}']
        lines.append('inet_interfaces = all'); lines.append('smtpd_tls_cert_file = '+(self.tls_cert_ref or '/external/tls/cert'))
        return '\n'.join(lines)+'\n'
    def recipient_map(self):
        return '\n'.join(f'{x.address} {x.service}:{x.local_identity}' for x in sorted(self.recipients,key=lambda x:x.address) if x.enabled)+'\n'
    def public_dns(self, host='mail.example.invalid'):
        return self.mx_records(host)+tuple(self.dmarc_record(d.name) for d in self.domains if d.enabled)

def write_atomic(path, content):
    target=os.path.abspath(os.fspath(path)); os.makedirs(os.path.dirname(target),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.ubb-mail-',dir=os.path.dirname(target),text=True)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
