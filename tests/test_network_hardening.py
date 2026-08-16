import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_network_hardening import *
class HardeningTests(unittest.TestCase):
 def test_inventory_contains_all_network_services(self):
  i=NetworkInventory.from_catalog(); ids={x['id'] for x in i.services}
  self.assertTrue({'dns-core','ntp-core','mail-edge','mail-core','nntp-core','irc-core','ftn-mailer','offline-exchange'}<=ids)
 def test_readiness_preserves_human_required(self):
  i=NetworkInventory.from_catalog(); self.assertTrue(all(x['state']=='READY_WITH_HUMAN_REQUIREMENTS' for x in i.qualification.values()))
 def test_dependency_graph_and_cycle_detection(self):
  i=NetworkInventory.from_catalog(); self.assertTrue(i.validate()); i.dependencies={'a':['b'],'b':['a']}
  with self.assertRaises(NetworkHardeningError): i.validate()
 def test_listener_inventory_and_collision(self):
  i=NetworkInventory.from_catalog(); self.assertTrue(any(x.port==25 for x in i.listeners)); self.assertTrue(i.validate())
  i.listeners=i.listeners+(Listener('x','tcp','127.0.0.1',25),)
  with self.assertRaises(NetworkHardeningError): i.validate()
 def test_tcp_udp_distinction(self):
  a=Listener('a','tcp','h',53); b=Listener('b','udp','h',53); self.assertNotEqual(a.key(),b.key())
 def test_secret_inventory_and_firewall(self):
  self.assertNotIn('value',str(secret_inventory())); self.assertEqual(firewall_intent()['default_policy'],'deny'); self.assertFalse(firewall_intent()['open_relay'])
 def test_digest_is_deterministic_and_drift_readonly(self):
  a=NetworkInventory.from_catalog(); b=NetworkInventory.from_catalog(); self.assertEqual(a.digest(),b.digest())
 def test_public_exposure_requires_explicit_model(self):
  i=NetworkInventory.from_catalog(); self.assertEqual(i.summary()['public_listeners'],0)
if __name__=='__main__': unittest.main()
