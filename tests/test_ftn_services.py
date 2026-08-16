import unittest,sys,tempfile,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_ftn import *
class FTNTests(unittest.TestCase):
 def net(self,**kw):
  d=dict(network_id='fsxnet',display_name='fsxNet',local_addresses=('2:211/16','2:211/16.1'),peers=(FTNPeer('up','2:211/1','node.example',password_ref='/etc/ftn.key'),),areas=(FTNArea('FSX_GEN','fsxnet','echomail','mystic-main','GENERAL'),)); d.update(kw); return FTNNetwork(**d)
 def test_addresses_and_networks(self):
  self.assertEqual(ftn_address('2:211/16.1'),'2:211/16.1'); self.assertEqual(ftn_address('2:211/16'),'2:211/16')
  with self.assertRaises(FTNConfigError): ftn_address('bad')
  c=FTNConfig((self.net(),FTNNetwork('local','Local',('1:1/1',)))); self.assertEqual(len(c.networks),2)
 def test_peer_secret_and_transport(self):
  self.assertEqual(self.net().peers[0].port,24554)
  with self.assertRaises(FTNConfigError): FTNPeer('x','2:1/1','h',password_ref='inline')
 def test_spool_areas_and_mapping(self):
  self.assertEqual(self.net().areas[0].kind,'echomail')
  with self.assertRaises(FTNConfigError): FTNArea('bad tag','x')
  with self.assertRaises(FTNConfigError): self.net(areas=(FTNArea('A','x'),FTNArea('A','x')))
 def test_public_listener_requires_peers(self):
  self.net(public_listener=True,bind_host='0.0.0.0')
  with self.assertRaises(FTNConfigError): FTNNetwork('x','x',('1:1/1',),public_listener=True,bind_host='0.0.0.0')
 def test_adapters_and_policies(self):
  for m in ('always_listening','interval','scheduled','manual'): FTNAdapter('x',('import_echomail',),m)
  with self.assertRaises(FTNConfigError): FTNAdapter('x',('bad',))
 def test_encoding_and_archive_allowlist(self):
  self.net(encoding='CP437',archive_method='zip')
  with self.assertRaises(FTNConfigError): self.net(encoding='utf16')
  with self.assertRaises(FTNConfigError): self.net(archive_method='shell-command')
 def test_deterministic_atomic_configs(self):
  c=FTNConfig((self.net(),)); self.assertEqual(c.render_binkd(),c.render_binkd())
  with tempfile.TemporaryDirectory() as d:
   p=os.path.join(d,'binkd.conf'); write_atomic(p,c.render_binkd()); self.assertTrue(Path(p).read_text())
 def test_safe_summary(self): self.assertNotIn('password',str(FTNConfig((self.net(),)).safe_summary()))
if __name__=='__main__': unittest.main()
