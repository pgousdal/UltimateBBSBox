import hashlib,json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from ubb_deployment import DeploymentManager,DeploymentError
class DeploymentTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); b=Path(self.t.name); self.archive=b/'archive'; digest=hashlib.sha256(b'preserved').hexdigest(); (self.archive/'objects'/'sha256'/digest[:2]).mkdir(parents=True); (self.archive/'metadata').mkdir(); self.deploy=b/'services'; self.payload=b'preserved'; (self.archive/'objects'/'sha256'/digest[:2]/digest).write_bytes(self.payload); self.artifact='fixture'; (self.archive/'metadata'/'fixture.json').write_text(json.dumps({'artifact':{'sha256':digest},'rights':{'install_locally':True},'provenance':{'source_url':'https://example.invalid'}})); self.m=DeploymentManager(self.archive,self.deploy)
 def tearDown(self): self.t.cleanup()
 def test_materialize_manifest_isolated_and_provenance(self):
  a=self.m.materialize('mystic-main','mystic-linux',self.artifact,self.deploy/'mystic-main'); b=self.m.materialize('abbs-main','abbs-amiga',self.artifact,self.deploy/'abbs-main'); name=a.artifact_sha256; self.assertEqual(a.artifact_sha256,b.artifact_sha256); (self.deploy/'mystic-main/assets'/name).write_bytes(b'changed'); self.assertNotEqual((self.deploy/'abbs-main/assets'/name).read_bytes(),b'changed'); self.assertTrue(self.m.verify('abbs-main')); self.assertEqual(self.m.provenance('mystic-main')['artifact']['artifact']['sha256'],a.artifact_sha256)
 def test_rights_missing_source_and_path_rejected(self):
  doc=json.loads((self.archive/'metadata/fixture.json').read_text()); doc['rights']['install_locally']=False; (self.archive/'metadata/fixture.json').write_text(json.dumps(doc));
  with self.assertRaises(DeploymentError): self.m.materialize('x','x',self.artifact,self.deploy/'x')
  with self.assertRaises(DeploymentError): self.m.materialize('x','x',self.artifact,self.archive/'bad')
 def test_shared_state_requires_identity_and_tamper_fails(self):
  with self.assertRaises(DeploymentError): self.m.materialize('x','x',self.artifact,self.deploy/'x',state_scope='shared')
  self.m.materialize('x','x',self.artifact,self.deploy/'x'); (self.deploy/'x/assets'/hashlib.sha256(self.payload).hexdigest()).write_bytes(b'tampered')
  with self.assertRaises(DeploymentError): self.m.verify('x')
if __name__=='__main__': unittest.main()
