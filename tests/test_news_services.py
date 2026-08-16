import unittest,sys,tempfile,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_news import *
class NewsTests(unittest.TestCase):
 def base(self,**kw):
  d=dict(groups=(NewsGroup('comp.ubb.general','General',post_policy='trusted_network'),),adapters=(NewsAdapter('mystic-main','bidirectional'),)); d.update(kw); return NewsConfig(**d)
 def test_private_default_and_modes(self):
  self.assertEqual(self.base().mode,'private_only'); self.base(mode='public_read'); self.base(mode='public_read_write',tls_cert_ref='/etc/tls/cert')
  with self.assertRaises(NewsConfigError): NewsConfig(mode='public_read_write')
 def test_group_validation_and_policy(self):
  self.assertTrue(self.base().groups[0].description)
  with self.assertRaises(NewsConfigError): NewsGroup('../etc')
  with self.assertRaises(NewsConfigError): self.base(groups=(NewsGroup('x'),NewsGroup('x')))
 def test_retention_bounded_and_override(self):
  self.base(retention=Retention(7,100,10000));
  with self.assertRaises(NewsConfigError): Retention(0)
 def test_ports_tls_and_external_refs(self):
  self.base(nntps_port=563,tls_cert_ref='/etc/tls/cert',tls_key_ref='/etc/tls/key')
  with self.assertRaises(NewsConfigError): self.base(tls_key_ref='INLINE KEY')
 def test_adapter_modes_and_checkpoint(self):
  for mode in ('inbound_to_bbs','outbound_from_bbs','bidirectional','scheduled_exchange','native_nntp'): NewsAdapter('x',mode)
  NewsAdapter('x','scheduled_exchange',checkpoint_ref='/var/lib/ubb/checkpoint')
 def test_mapping_and_loop_safe_identity(self):
  c=NewsConfig(groups=(NewsGroup('bbs.mystic.general',bbs_service='mystic-main',bbs_area='GENERAL'),)); self.assertIn('bbs.mystic.general',c.groups_render())
  with self.assertRaises(NewsConfigError): NewsConfig(groups=(NewsGroup('a',bbs_service='x',bbs_area='A'),NewsGroup('b',bbs_service='x',bbs_area='A')))
 def test_feed_secret_and_no_default_feed(self):
  self.assertEqual(self.base().feeds,()); NewsFeed('peer.example.org',('comp.ubb.*',),secret_ref='/etc/ubb/feed.key')
  with self.assertRaises(NewsConfigError): NewsFeed('peer.example.org',('x',),secret_ref='token')
 def test_deterministic_render_and_atomic(self):
  c=self.base(); self.assertEqual(c.render(),c.render())
  with tempfile.TemporaryDirectory() as d:
   p=os.path.join(d,'news.conf'); write_atomic(p,c.render()); self.assertTrue(Path(p).read_text())
 def test_safe_observability_has_no_content(self):
  import json; raw=json.dumps(self.base().to_safe_dict()); self.assertNotIn('body',raw); self.assertNotIn('subject',raw)
if __name__=='__main__': unittest.main()
