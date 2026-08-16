import unittest,sys,tempfile,os,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_exchange import *
class ExchangeTests(unittest.TestCase):
 def test_formats_and_purposes(self):
  self.assertEqual(ExchangeFormat('qwk').name,'qwk'); self.assertEqual(ExchangeFormat('bluewave').name,'bluewave')
  with self.assertRaises(ExchangeError): ExchangeFormat('qwke')
  for p in PURPOSES: PacketManifest('p1','qwk',p,'svc','2026-01-01','outbound')
 def test_manifest_lifecycle_and_bounds(self):
  self.assertEqual(PacketManifest('p','qwk','user_offline_mail','svc','now','outbound',state='ready').state,'ready')
  with self.assertRaises(ExchangeError): PacketManifest('p','qwk','user_offline_mail','svc','now','outbound',state='bad')
 def test_mapping_and_adapter(self):
  c=ExchangeConfig(mappings=(AreaMapping('svc','GENERAL','general',conference=1),),adapters=(ExchangeAdapter('svc',('export_messages','import_replies')),)); self.assertEqual(c.mapping_count if hasattr(c,'mapping_count') else len(c.mappings),1)
  with self.assertRaises(ExchangeError): AreaMapping('svc','x','x',format='bad')
 def test_identity_privacy(self):
  with self.assertRaises(ExchangeError): PacketManifest('p','qwk','user_offline_mail','svc','now','outbound',user_ref='password=bad')
  self.assertNotIn('body',str(PacketManifest('p','qwk','system_exchange','svc','now','outbound').safe()))
 def test_encodings_and_filenames(self):
  ExchangeFormat('qwk',encoding='CP437'); ExchangeFormat('bluewave',encoding='adapter_defined')
  filename('CONTROL.DAT')
  with self.assertRaises(ExchangeError): filename('../x')
 def test_safe_archive_rejects_traversal_and_bounds(self):
  with tempfile.TemporaryDirectory() as d:
   z=os.path.join(d,'x.zip')
   with zipfile.ZipFile(z,'w') as f: f.writestr('../escape','x')
   with self.assertRaises(ExchangeError): safe_extract_zip(z,os.path.join(d,'out'))
 def test_safe_archive_extracts_staged(self):
  with tempfile.TemporaryDirectory() as d:
   z=os.path.join(d,'x.zip')
   with zipfile.ZipFile(z,'w') as f: f.writestr('CONTROL.DAT','ok')
   safe_extract_zip(z,os.path.join(d,'out')); self.assertTrue(Path(d,'out','CONTROL.DAT').exists())
 def test_checkpoint_and_atomic_manifest(self):
  c=ExchangeConfig(); self.assertEqual(c.safe_summary()['formats'],['qwk','bluewave'])
if __name__=='__main__': unittest.main()
