from .auth import ROLES
class AdminActionService:
 def __init__(self,supervisor=None,integration_registry=None): self.supervisor=supervisor; self.integrations=integration_registry
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
