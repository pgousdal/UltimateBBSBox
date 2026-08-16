import unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from ubb_edge import EdgeConfig, EdgeConfigError, Ingress, OverlayNode, PrivateSite, PublicIdentity, Route

class EdgeOverlayTests(unittest.TestCase):
 def base(self, **kw):
  d=dict(sites=(PrivateSite('home-main','home-1',('192.168.1.0/24',),('mystic-main','abbs-main')),), public_identities=(PublicIdentity('mystic.example.invalid','mystic-main'),), ingress=(Ingress('mystic-telnet','tcp',2323,'mystic-main',23,public_address='203.0.113.10'),), routes=(Route('edge-1','192.168.1.0/24'),))
  d.update(kw); return EdgeConfig(**d)
 def test_headscale_default_and_control_plane_model(self):
  c=self.base(); self.assertEqual(c.provider,'headscale'); self.assertEqual(c.support_level,'recommended'); self.assertFalse(c.derp_enabled); self.assertFalse(c.routes[0].approved)
 def test_alternative_providers_validate(self):
  for p in ('tailscale','wireguard','zerotier','nebula'): self.assertEqual(self.base(provider=p).support_level,'supported')
  with self.assertRaises(EdgeConfigError): self.base(provider='vpn-magic')
 def test_edge_site_identity_and_ingress_protocols(self):
  c=self.base(ingress=(Ingress('u','udp',5300,'mystic-main',53),Ingress('h','http',8080,'mystic-main',80,hostname='museum.example.invalid'),Ingress('s','https',8443,'mystic-main',443,hostname='admin.example.invalid')))
  self.assertEqual(len(c.ingress),3); self.assertEqual(c.edge_node.role,'edge')
 def test_telnet_hostname_cannot_disambiguate(self):
  with self.assertRaises(EdgeConfigError): Ingress('bad','tcp',23,'mystic-main',23,hostname='mystic.example.invalid')
  self.base(ingress=(Ingress('a','tcp',23,'mystic-main',23,public_address='203.0.113.10'), Ingress('b','tcp',23,'abbs-main',23,public_address='203.0.113.11')))
  self.base(ingress=(Ingress('a','tcp',2323,'mystic-main',23), Ingress('b','tcp',2324,'abbs-main',23)))
 def test_conflicts_and_validation(self):
  with self.assertRaises(EdgeConfigError): self.base(ingress=(Ingress('a','tcp',23,'mystic-main',23),Ingress('b','tcp',23,'abbs-main',23)))
  with self.assertRaises(EdgeConfigError): self.base(ingress=(Ingress('a','tcp',70000,'mystic-main',23),))
  with self.assertRaises(EdgeConfigError): self.base(public_identities=(PublicIdentity('../bad','mystic-main'),))
  with self.assertRaises(EdgeConfigError): self.base(secret_refs=('overlay-private-key',))
 def test_routes_exit_nodes_disabled(self):
  with self.assertRaises(EdgeConfigError): Route('edge-1','0.0.0.0/0',exit_node=True)
 def test_secrets_are_references_only_and_json_safe(self):
  data=self.base(secret_refs=('/etc/ubb/key',)).to_dict(); self.assertEqual(data['secret_refs'],['/etc/ubb/key']); self.assertNotIn('private_key',str(data))
 def test_provider_support_is_not_runtime_qualification(self):
  self.assertEqual(self.base(provider='nebula').support_level,'supported')
  self.assertIn('support_level',self.base().to_dict())
if __name__=='__main__': unittest.main()
