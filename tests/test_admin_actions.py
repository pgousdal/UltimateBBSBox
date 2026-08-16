import pathlib, tempfile, unittest, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ubb_admin.actions import AdminActionService
class Registry:
 def __init__(self): self.services={'demo':type('S',(),{'document':{'maintenance':{'jobs':[{'name':'job'}]}}})()}
 def service(self,x): return self.services[x]
class Sup:
 def __init__(self): self.registry=Registry(); self.calls=[]
 def start(self,s,r): self.calls.append(('start',s)); return {'state':'running'}
 def stop(self,s): self.calls.append(('stop',s)); return {'state':'stopped'}
 def run_maintenance(self,s,j): self.calls.append(('maintenance',s,j)); return {'ok':True}
 def set_lifecycle_mode(self,s,m): self.calls.append(('lifecycle',s,m)); return {'mode':m}
class ActionsTests(unittest.TestCase):
 def setUp(self): self.s=Sup(); self.a=AdminActionService(self.s)
 def test_role_matrix_and_registered_jobs(self):
  self.assertRaises(PermissionError,lambda:self.a.start('demo','viewer')); self.assertEqual(self.a.start('demo','operator')['state'],'running'); self.assertEqual(self.a._job('demo','job','operator')['ok'],True); self.assertRaises(ValueError,lambda:self.a._job('demo','arbitrary','operator')); self.assertRaises(PermissionError,lambda:self.a.lifecycle('demo','always_on','operator')); self.assertEqual(self.a.lifecycle('demo','always_on','administrator')['mode'],'always_on')
if __name__=='__main__':unittest.main()
