import subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HousekeepingTests(unittest.TestCase):
 def test_dashboard_canonical_entrypoint_help(self):
  p=subprocess.run(['python3','scripts/ubb-dashboard.py','--help'],cwd=ROOT,text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_m6_milestones_complete(self):
  text=(ROOT/'docs/MILESTONES.md').read_text()
  for n in range(1,9): self.assertRegex(text,rf'M6\.{n}[^\n]*COMPLETE')
 def test_network_services_reconciled(self):
  text=(ROOT/'docs/NETWORK-SERVICES.md').read_text()
  self.assertNotIn('not part of\nthis delivery',text)
  self.assertIn('NETWORK-HARDENING.md',text)
 def test_governance_files_exist(self):
  self.assertTrue((ROOT/'SECURITY.md').exists()); self.assertTrue((ROOT/'CONTRIBUTING.md').exists())
 def test_strict_target_is_declared(self):
  self.assertIn('check-strict', (ROOT/'Makefile').read_text()); self.assertIn('make check-strict',(ROOT/'.github/workflows/check.yml').read_text())
if __name__=='__main__': unittest.main()
