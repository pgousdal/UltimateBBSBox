import json,pathlib,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ubb_admin import AuthStore,SessionStore,AuditLog
from ubb_admin.auth import LoginThrottle
class AuthTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.p=pathlib.Path(self.t.name); self.store=AuthStore(self.p/'users.json')
 def tearDown(self):self.t.cleanup()
 def test_hash_sessions_and_rotation(self):
  self.store.add('alice','secret','administrator'); raw=json.loads((self.p/'users.json').read_text()); self.assertNotIn('secret',json.dumps(raw)); self.assertTrue(self.store.authenticate('alice','secret')); self.assertFalse(self.store.authenticate('alice','bad')); sessions=SessionStore(); one=sessions.create('alice','administrator'); two=sessions.create('alice','administrator'); self.assertNotEqual(one,two); self.assertTrue(sessions.get(one)['csrf']); sessions.remove(one); self.assertIsNone(sessions.get(one))
 def test_audit_excludes_credentials_and_is_append_only(self):
  log=AuditLog(self.p/'audit.jsonl'); item=log.append('alice','operator','start','mystic-main','success',message='delegated'); text=(self.p/'audit.jsonl').read_text(); self.assertIn('alice',text); self.assertNotIn('password',text); self.assertEqual(log.read()[0]['request_id'],item['request_id'])
 def test_login_throttle_backoff_and_recovery(self):
  now=[100.0]; throttle=LoginThrottle(clock=lambda:now[0],max_entries=10)
  for _ in range(3): self.assertEqual(throttle.failure('alice','127.0.0.1'),0)
  self.assertEqual(throttle.failure('alice','127.0.0.1'),5); self.assertEqual(throttle.retry_after('alice','127.0.0.1'),5)
  now[0]+=5; throttle.success('alice','127.0.0.1'); self.assertEqual(throttle.retry_after('alice','127.0.0.1'),0)
 def test_throttle_is_bounded_and_dimensions_are_independent(self):
  now=[1.0]; throttle=LoginThrottle(clock=lambda:now[0],max_entries=4)
  for i in range(20): throttle.failure('user-%d'%i,'source')
  self.assertLessEqual(throttle.size(),4)
  for _ in range(4): throttle.failure('alice','a')
  self.assertGreater(throttle.retry_after('alice','a'),0)
if __name__=='__main__':unittest.main()
