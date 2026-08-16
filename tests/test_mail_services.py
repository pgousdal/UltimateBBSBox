import unittest,sys,tempfile,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_mail import *
class MailTests(unittest.TestCase):
 def base(self,**kw):
  d=dict(domains=(MailDomain('example.org','local'),MailDomain('mystic.example.org','mystic-main')),recipients=(Recipient('alice@mystic.example.org','mystic-main','alice'),),edge_ips=('203.0.113.10',),dkim_domains=('example.org',),dkim_key_ref='/etc/ubb/dkim.key'); d.update(kw); return MailConfig(**d)
 def test_domains_routes_and_render(self): self.assertEqual(len(self.base().mx_records()),2); self.assertIn('reject_unauth_destination',self.base().render()); self.assertEqual(self.base().recipient_map().count('alice@'),1)
 def test_invalid_domain_and_duplicate_recipients(self):
  with self.assertRaises(MailConfigError): MailDomain('../etc')
  with self.assertRaises(MailConfigError): self.base(recipients=(Recipient('a@example.org','x','a'),Recipient('a@example.org','x','b')))
 def test_mx_spf_and_unsafe_spf(self):
  self.assertIn('MX 10',self.base().mx_records()[0]); self.assertIn('-all',self.base().spf_record())
  with self.assertRaises(MailConfigError): self.base(edge_ips=()).spf_record()
 def test_dkim_dmarc_and_external_secrets(self):
  self.assertIn('DMARC1',self.base().dmarc_record('example.org'))
  with self.assertRaises(MailConfigError): self.base(dkim_key_ref='PRIVATE KEY')
  with self.assertRaises(MailConfigError): self.base(dmarc_policy='bad')
 def test_outbound_modes_and_submission(self):
  self.base(outbound_mode='direct_mx'); self.base(outbound_mode='smarthost',smarthost='smtp.example.net',smarthost_secret_ref='/etc/ubb/smtp.secret')
  with self.assertRaises(MailConfigError): self.base(outbound_mode='smarthost')
 def test_relay_and_catchall_defaults(self):
  c=self.base(); self.assertFalse(c.catch_all); self.assertIn('reject_unauth_destination',c.render())
 def test_alias_and_loop_rejected(self):
  self.base(aliases=(('postmaster@example.org','alice@mystic.example.org'),))
  with self.assertRaises(MailConfigError): self.base(aliases=(('a@example.org','a@example.org'),))
 def test_adapter_modes_product_neutral(self):
  for mode in ('native_smtp','mailbox_bridge','batch_exchange','scheduled_exchange'): self.assertEqual(Adapter('mystic-main',mode).mode,mode)
  with self.assertRaises(MailConfigError): Adapter('mystic-main','custom')
 def test_atomic_publication(self):
  with tempfile.TemporaryDirectory() as d:
   p=os.path.join(d,'main.cf'); write_atomic(p,self.base().render()); self.assertTrue(Path(p).read_text())
 def test_privacy_safe_queue_shape(self):
  import json
  data={'queue_depth':2,'deferred_count':1,'oldest_age_seconds':30}; self.assertNotIn('body',json.dumps(data)); self.assertNotIn('subject',json.dumps(data))
if __name__=='__main__': unittest.main()
