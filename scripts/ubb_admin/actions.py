from .auth import ROLES
class AdminActionService:
 def __init__(self,supervisor=None,integration_registry=None,backup=None,qualify=None,install_roots=None,archive_root=None): self.supervisor=supervisor; self.integrations=integration_registry; self.backup_api=backup; self.qualify_api=qualify; self.install_roots=install_roots or {}; self.archive_root=archive_root
 def _p(self,r,n):
  if ROLES.get(r,-1)<ROLES[n]: raise PermissionError('insufficient role')
 def start(self,s,r): self._p(r,'operator'); return self.supervisor.start(s,'admin')
 def stop(self,s,r): self._p(r,'operator'); return self.supervisor.stop(s)
 def restart(self,s,r): self._p(r,'operator'); self.supervisor.stop(s); return self.supervisor.start(s,'admin')
 def lifecycle(self,s,m,r):
  self._p(r,'administrator')
  if m not in ('always_on','on_demand'): raise ValueError('invalid lifecycle mode')
  if not hasattr(self.supervisor,'set_lifecycle_mode'): raise NotImplementedError('deployment lifecycle API unavailable')
  return self.supervisor.set_lifecycle_mode(s,m)
 def maintenance(self,s,j,r): self._p(r,'operator'); return self.supervisor.run_maintenance(s,j)
 def _job(self,s,j,r):
  service=self.supervisor.registry.service(s) if hasattr(self.supervisor.registry,'service') else self.supervisor.registry.services[s]
  jobs=service.document.get('maintenance',{}).get('jobs',[])
  if not any(x.get('name')==j for x in jobs): raise ValueError('maintenance job is not registered')
  return self.maintenance(s,j,r)
 def backup(self,s,r):
  self._p(r,'operator')
  if not self.backup_api: raise NotImplementedError('backup API unavailable')
  return self.backup_api(s)
 def qualify(self,i,release,r):
  self._p(r,'operator')
  if self.qualify_api: return self.qualify_api(i,release)
  root=self.install_roots.get(i)
  if not root or not self.archive_root: raise NotImplementedError('qualification API unavailable')
  return self.integrations.get(i).qualify(self.archive_root,release,root)
 def promote(self,i,release,r):
  self._p(r,'administrator')
  if not self.integrations: raise NotImplementedError('integration API unavailable')
  root=self.install_roots.get(i)
  if not root: raise NotImplementedError('integration deployment root unavailable')
  return self.integrations.get(i).promote(root,release)
 def rollback(self,i,r):
  self._p(r,'administrator')
  if not self.integrations: raise NotImplementedError('integration API unavailable')
  root=self.install_roots.get(i)
  if not root: raise NotImplementedError('integration deployment root unavailable')
  return self.integrations.get(i).rollback(root)
