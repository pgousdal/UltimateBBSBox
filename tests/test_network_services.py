import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_network import DNSConfig,NTPConfig,NetworkConfigError,write_atomic
class NetworkTests(unittest.TestCase):
 def test_dns_records_validation_and_determinism(self):
  c=DNSConfig(records=({'name':'mystic','type':'A','value':'127.0.0.2'},{'name':'alias','type':'CNAME','value':'mystic.ubb.internal'},{'name':'v6','type':'AAAA','value':'::1'})); self.assertEqual(c.render(),DNSConfig(records=tuple(reversed(c.records))).render()); self.assertIn('local-data',c.render())
  with self.assertRaises(NetworkConfigError): DNSConfig(internal_domain='../etc/passwd')
  with self.assertRaises(NetworkConfigError): DNSConfig(records=({'name':'x','type':'A','value':'1.1.1.1'},{'name':'x','type':'A','value':'1.1.1.2'}))
 def test_dns_private_recursion_defaults(self):
  c=DNSConfig(); self.assertEqual(c.listen,('127.0.0.1',)); self.assertTrue(c.recursion); self.assertIn('refuse',c.render())
 def test_ntp_modes_and_network_validation(self):
  self.assertNotIn('allow',NTPConfig().render()); self.assertIn('allow',NTPConfig(mode='client_and_server').render())
  with self.assertRaises(NetworkConfigError): NTPConfig(trusted_networks=('not-network',))
 def test_generated_config_atomic_write(self):
  import tempfile,os
  with tempfile.TemporaryDirectory() as d:
   p=os.path.join(d,'unbound.conf'); write_atomic(p,DNSConfig().render())
   with open(p,encoding='utf-8') as stream: self.assertIn('interface:',stream.read())
 def test_udp_registry_endpoints_and_hidden_services(self):
  from ubb_registry.loader import load_registry
  r=load_registry(Path(__file__).resolve().parents[1]/'catalog'); self.assertEqual(r.endpoints['dns-core'].type,'udp'); self.assertEqual(r.endpoints['ntp-core'].document['port'],123); self.assertFalse(r.services['dns-core'].document['exposure']['main_menu'])
if __name__=='__main__': unittest.main()
