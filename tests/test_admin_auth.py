import json,pathlib,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ubb_admin import AuthStore,SessionStore,AuditLog
class AuthTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.p=pathlib.Path(self.t.name); self.store=AuthStore(self.p/'users.json')
 def tearDown(self):self.t.cleanup()
 def test_hash_sessions_and_rotation(self):
  self.store.add('alice','secret','administrator'); raw=json.loads((self.p/'users.json').read_text()); self.assertNotIn('secret',json.dumps(raw)); self.assertTrue(self.store.authenticate('alice','secret')); self.assertFalse(self.store.authenticate('alice','bad')); sessions=SessionStore(); one=sessions.create('alice','administrator'); two=sessions.create('alice','administrator'); self.assertNotEqual(one,two); self.assertTrue(sessions.get(one)['csrf']); sessions.remove(one); self.assertIsNone(sessions.get(one))
 def test_audit_excludes_credentials_and_is_append_only(self):
  log=AuditLog(self.p/'audit.jsonl'); item=log.append('alice','operator','start','mystic-main','success',message='delegated'); text=(self.p/'audit.jsonl').read_text(); self.assertIn('alice',text); self.assertNotIn('password',text); self.assertEqual(log.read()[0]['request_id'],item['request_id'])
if __name__=='__main__':unittest.main()
