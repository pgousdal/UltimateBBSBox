import unittest,sys,tempfile,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_irc import *
class IRCTests(unittest.TestCase):
 def base(self,**kw):
  d=dict(channels=(IRCChannel('#ubb',history='none'),),bridges=(IRCBridge('mystic-main','#ubb','CHAT',mode='bidirectional'),)); d.update(kw); return IRCConfig(**d)
 def test_private_default_and_public_requires_tls(self):
  self.assertEqual(self.base().mode,'private_only'); self.base(mode='public',tls_cert_ref='/etc/tls/cert',tls_key_ref='/etc/tls/key')
  with self.assertRaises(IRCConfigError): self.base(mode='public')
 def test_tls_plain_ports_and_external_keys(self):
  c=self.base(tls_cert_ref='/etc/tls/cert',tls_key_ref='/etc/tls/key',listen_plain=False); self.assertEqual(c.tls_port,6697)
  with self.assertRaises(IRCConfigError): self.base(tls_key_ref='inline')
 def test_identity_validation(self):
  self.base(server_name='irc.example.invalid',network_name='UBB-Network')
  with self.assertRaises(IRCConfigError): self.base(server_name='bad name')
 def test_channel_policies_and_history(self):
  c=self.base(channels=(IRCChannel('#public',visibility='public'),IRCChannel('#private',visibility='private',invite_only=True,moderated=True,history='bounded',max_users=20))); self.assertEqual(len(c.channels),2)
  with self.assertRaises(IRCConfigError): IRCChannel('bad')
 def test_bridge_modes_identity_and_visibility(self):
  for mode in ('inbound_to_bbs','outbound_from_bbs','bidirectional','scheduled_bridge','native_irc'): IRCBridge('x','#x','CHAT',mode=mode)
  with self.assertRaises(IRCConfigError): self.base(bridges=(IRCBridge('x','#x','CHAT',visibility='public'),))
  self.base(mode='public',tls_cert_ref='/c',bridges=(IRCBridge('x','#x','CHAT',visibility='public'),))
 def test_duplicate_mappings_and_secrets(self):
  with self.assertRaises(IRCConfigError): self.base(channels=(IRCChannel('#x'),IRCChannel('#x')))
  with self.assertRaises(IRCConfigError): IRCBridge('x','#x','CHAT',checkpoint_ref='inline')
 def test_atomic_render(self):
  c=self.base(); self.assertEqual(c.render(),c.render())
  with tempfile.TemporaryDirectory() as d:
   p=os.path.join(d,'inspircd.conf'); write_atomic(p,c.render()); self.assertTrue(Path(p).read_text())
 def test_privacy_safe_metrics(self):
  import json; raw=json.dumps(self.base().to_safe_dict()); self.assertNotIn('message',raw); self.assertNotIn('password',raw)
if __name__=='__main__': unittest.main()
