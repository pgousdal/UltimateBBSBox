import json,pathlib,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ubb_backup import BackupManager,BackupError
class BackupTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.b=pathlib.Path(self.t.name); self.live=self.b/'live'; self.live.mkdir(); (self.live/'users').mkdir(); (self.live/'users'/'db').write_text('u'); (self.live/'software').mkdir(); (self.live/'software'/'bin').write_text('exclude'); (self.live/'cache').mkdir(); (self.live/'cache'/'x').write_text('exclude'); self.m=BackupManager(self.b/'backups'); self.m.declare('mystic-main',self.live)
 def tearDown(self):self.t.cleanup()
 def test_create_manifest_verify_and_restore_plan(self):
  x=self.m.create('mystic-main',release='r'); self.assertEqual(x.target_id,'mystic-main'); self.assertEqual(self.m.verify(x.backup_id)['verification'],'PASS'); plan=self.m.restore_plan(x.backup_id,'mystic-main',self.b/'restore'); self.assertTrue(plan.preserves_software); result=self.m.restore(x.backup_id,'mystic-main',self.b/'restore'); self.assertTrue(result['software_preserved']); self.assertEqual((self.b/'restore/users/db').read_text(),'u'); self.assertFalse((self.b/'restore/software').exists())
 def test_tamper_path_and_active_conflict(self):
  with self.assertRaises(BackupError):self.m.create('mystic-main',active_sessions=1)
  x=self.m.create('mystic-main'); (self.b/'backups'/x.backup_id/'payload.tar').write_bytes(b'bad'); self.assertRaises(BackupError,lambda:self.m.verify(x.backup_id))
 def test_symlink_rejected(self):
  (self.live/'escape').symlink_to('/etc/passwd'); self.assertRaises(BackupError,lambda:self.m.create('mystic-main'))
if __name__=='__main__':unittest.main()
