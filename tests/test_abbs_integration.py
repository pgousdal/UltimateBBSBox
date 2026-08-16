import hashlib
import io
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]

import ubb_archive as archive  # noqa: E402
from integrations.bbs.abbs.integration import ABBSAmigaIntegration, ABBSRelease  # noqa: E402
from ubb_integrations import ArtifactRequiredError, InstallError, IntegrationRegistry, QualificationStatus, prohibited_downloads  # noqa: E402
from ubb_integrations.amiga import copy_working_image, resolve_assets  # noqa: E402
from ubb_registry import load_registry  # noqa: E402
from ubb_router import MemoryConnector, RouteRequest, Router, TerminalCapabilities  # noqa: E402
from ubb_runtime import RuntimeManager  # noqa: E402
from ubb_supervisor import FakeClock, FakeDriver, Supervisor  # noqa: E402


class ABBSIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=pathlib.Path(self.temp.name)
        self.archive=self.base/"archive"; archive.init_archive(self.archive)
        self.install=self.base/"abbs"; self.distribution=self.base/"ABBS-fixture.lha"
        with tarfile.open(self.distribution,"w") as bundle:
            for name,data in (("ABBS/ABBS",b"synthetic executable"),("ABBS/Docs/Install ABBS",b"synthetic instructions")):
                info=tarfile.TarInfo(name); info.size=len(data); bundle.addfile(info,io.BytesIO(data))
        digest=hashlib.sha256(self.distribution.read_bytes()).hexdigest()
        self.integration=ABBSAmigaIntegration()
        release=ABBSRelease("fixture","3.2","abbs-fixture","ABBS-fixture.lha","https://example.invalid/ABBS-fixture.lha",digest,"","",self.distribution.stat().st_size)
        self.integration.releases={"fixture":release}; self.integration.default_release="fixture"; self.integration.artifact_id="abbs-fixture"

    def tearDown(self): self.temp.cleanup()
    def acquire(self, private=False): return self.integration.acquire(self.archive,local_file=self.distribution,release="fixture",licensed_private=private)
    def assets(self):
        kick=self.base/"private-kick.rom"; hdf=self.base/"private-os.hdf"; kick.write_bytes(b"licensed rom"); hdf.write_bytes(b"licensed os")
        return {"kickstart":kick,"amigaos_base_hdf":hdf}

    def test_discovery_family_release_and_unknown(self):
        self.assertIsInstance(IntegrationRegistry.defaults().get("abbs-amiga"),ABBSAmigaIntegration)
        self.assertEqual(ABBSAmigaIntegration().select_release().version,"3.2")
        with self.assertRaises(ArtifactRequiredError): ABBSAmigaIntegration().select_release("invented")

    def test_production_chain_uses_generic_fs_uae(self):
        registry=load_registry(ROOT/"catalog"); resolved=registry.resolve("abbs-main")
        self.assertEqual(resolved["endpoint"]["id"],"abbs-serial-bridge"); self.assertEqual(resolved["integration"]["runtime"],"fs_uae")
        runtime,config=RuntimeManager(registry,self.base/"runtime").configuration("abbs-main")
        self.assertEqual(runtime,"fs_uae"); self.assertEqual(config["stream"]["type"],"tcp"); self.assertEqual(config["readiness"]["type"],"tcp_port")

    def test_m1_acquisition_hash_immutability_and_rights(self):
        value=self.acquire(); obj=archive.object_path(self.archive,value["artifact"]["sha256"]); original=obj.read_bytes()
        self.assertEqual(value["artifact"]["sha256"],hashlib.sha256(self.distribution.read_bytes()).hexdigest())
        self.assertEqual(obj.stat().st_mode & 0o777,0o444); self.assertFalse(value["rights"]["redistribute_original"]); self.assertFalse(value["rights"]["publish_to_bbs_filebase"])
        self.integration.prepare(self.archive,"abbs-fixture",self.install)
        self.assertEqual(obj.read_bytes(),original)

    def test_derived_lineage_and_resumable_prepare(self):
        self.acquire(); first=self.integration.prepare(self.archive,"abbs-fixture",self.install); second=self.integration.prepare(self.archive,"abbs-fixture",self.install)
        self.assertEqual(first,second); self.assertEqual(first["artifact"]["role"],"derived_install_media")
        self.assertEqual(first["preservation"]["lineage"]["parents"][0]["artifact_id"],"abbs-fixture")

    def test_private_artifact_supported_but_not_published(self):
        value=self.acquire(private=True); self.assertEqual(value["rights"]["status"],"licensed_private"); self.assertFalse(value["rights"]["publish_to_bbs_filebase"])

    def test_missing_and_user_supplied_prerequisites(self):
        with self.assertRaisesRegex(InstallError,"kickstart"): resolve_assets({},self.integration.prerequisites)
        assets=self.assets(); assets.pop("amigaos_base_hdf")
        with self.assertRaisesRegex(InstallError,"amigaos_base_hdf"): resolve_assets(assets,self.integration.prerequisites)
        resolved=resolve_assets(self.assets(),self.integration.prerequisites); self.assertTrue(all(p.is_relative_to(self.base) for p in resolved.values()))

    def test_assisted_install_golden_working_and_live_preservation(self):
        self.acquire(); assets=self.assets(); result=self.integration.install(self.archive,"abbs-fixture",self.install,assets=assets,evidence=self.integration.manual_evidence)
        self.assertTrue(result.changed); golden=pathlib.Path(result.release_path); working=pathlib.Path(result.live_path)
        working.write_bytes(b"living changes"); again=self.integration.install(self.archive,"abbs-fixture",self.install,assets=assets,evidence=self.integration.manual_evidence)
        self.assertFalse(again.changed); self.assertEqual(working.read_bytes(),b"living changes"); self.assertNotEqual(working.read_bytes(),golden.read_bytes())
        self.assertFalse(any(p.name.startswith("private-") for p in (ROOT/"integrations").rglob("*")))

    def test_manual_evidence_and_qualification(self):
        self.acquire(); self.integration.prepare(self.archive,"abbs-fixture",self.install)
        self.assertEqual(self.integration.configure(self.install).status,QualificationStatus.HUMAN_REQUIRED)
        self.assertEqual(self.integration.configure(self.install,self.integration.manual_evidence).status,QualificationStatus.PASS)
        results=self.integration.qualify(self.archive,"abbs-fixture",self.install,evidence=self.integration.manual_evidence,amiga_boot=True)
        states={x.check:x.status for x in results}; self.assertEqual(states["artifact_integrity"],QualificationStatus.PASS); self.assertEqual(states["amiga_boot"],QualificationStatus.PASS); self.assertEqual(states["login_menu"],QualificationStatus.HUMAN_REQUIRED)

    def test_corruption_fails_qualification(self):
        value=self.acquire(); self.integration.prepare(self.archive,"abbs-fixture",self.install); obj=archive.object_path(self.archive,value["artifact"]["sha256"]); obj.chmod(0o644); obj.write_bytes(b"bad")
        self.assertEqual(self.integration.qualify(self.archive,"abbs-fixture",self.install)[0].status,QualificationStatus.FAIL)

    def test_working_copy_helper_never_overwrites(self):
        golden=self.base/"golden"; working=self.base/"live/work.hdf"; golden.write_bytes(b"base")
        self.assertTrue(copy_working_image(golden,working)); working.write_bytes(b"live"); self.assertFalse(copy_working_image(golden,working)); self.assertEqual(working.read_bytes(),b"live")

    def test_m3_modes_maintenance_and_m4_hold_cleanup(self):
        catalog=self.base/"catalog"; shutil.copytree(ROOT/"catalog",catalog); registry=load_registry(catalog); driver=FakeDriver(); clock=FakeClock()
        supervisor=Supervisor(registry,self.base/"state",driver_resolver=lambda _s:driver,clock=clock)
        supervisor.reconcile(); self.assertEqual(supervisor.status("abbs-main")["state"],"stopped")
        session=supervisor.acquire_session("abbs-main"); self.assertEqual(supervisor.status("abbs-main")["state"],"running"); supervisor.release_session("abbs-main",session)
        service=catalog/"services/abbs-main.yml"; service.write_text(service.read_text().replace("mode: on_demand","mode: always_on")); always=load_registry(catalog)
        sup2=Supervisor(always,self.base/"always",driver_resolver=lambda _s:FakeDriver(),clock=FakeClock()); sup2.reconcile(); self.assertEqual(sup2.status("abbs-main")["state"],"running")
        router=Router(registry,supervisor,self.base/"router",connectors={"tcp":MemoryConnector()}); handle=router.open_session(RouteRequest("abbs-main",terminal=TerminalCapabilities(encoding="amiga-8bit",display="ansi",width=80,height=25)))
        self.assertEqual(supervisor.status("abbs-main")["active_session_count"],1); handle.close(); self.assertEqual(supervisor.status("abbs-main")["active_session_count"],0)
        failing=Router(registry,supervisor,self.base/"fail",connectors={"tcp":MemoryConnector(error=OSError("no bridge"))})
        with self.assertRaises(OSError): failing.open_session(RouteRequest("abbs-main"))
        self.assertEqual(supervisor.status("abbs-main")["active_session_count"],0)

    def test_downloader_guard_and_no_core_product_branch(self):
        bad=self.base/"integrations/bbs/abbs"; bad.mkdir(parents=True); (bad/"download.yml").write_text("- get_url:\n    url: https://bad.invalid/abbs.lha\n")
        self.assertEqual(prohibited_downloads(self.base),["integrations/bbs/abbs/download.yml"])
        core=[ROOT/"scripts/ubb_archive.py",ROOT/"scripts/ubb_registry",ROOT/"scripts/ubb_supervisor",ROOT/"scripts/ubb_router",ROOT/"scripts/ubb_runtime"]
        for item in core:
            paths=[item] if item.is_file() else item.rglob("*.py")
            self.assertFalse(any("abbs" in p.read_text(encoding="utf-8").lower() for p in paths))

    def test_amiexpress_shape_reuses_generic_helpers(self):
        from ubb_integrations.amiga import AmigaProfile, write_fs_uae_config
        assets=self.assets(); working=self.base/"ae.hdf"; working.write_bytes(b"fixture")
        config=write_fs_uae_config(self.base/"ae.fs-uae",AmigaProfile("A1200","68020","AGA",2,8,"127.0.0.1",6500),kickstart=assets["kickstart"],working_hdf=working)
        self.assertIn("serial_port = tcp://127.0.0.1:6500/wait",config.read_text())


if __name__ == "__main__": unittest.main()
