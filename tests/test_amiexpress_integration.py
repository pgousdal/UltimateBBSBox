import hashlib
import io
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/"scripts"),str(ROOT)]
import ubb_archive as archive  # noqa: E402
from integrations.bbs.abbs.integration import ABBSAmigaIntegration  # noqa: E402
from integrations.bbs.amiexpress.integration import AmiExpressAmigaIntegration, AmiExpressRelease  # noqa: E402
from ubb_integrations import ArtifactRequiredError, InstallError, IntegrationRegistry, QualificationStatus, prohibited_downloads  # noqa: E402
from ubb_integrations.amiga import copy_working_image, resolve_assets, runtime_profile, write_fs_uae_config  # noqa: E402
from ubb_integrations.profiles import PROFILES, get_profile, validate_profiles  # noqa: E402
from ubb_registry import load_registry  # noqa: E402
from ubb_router import MemoryConnector, RouteRequest, Router, TerminalCapabilities  # noqa: E402
from ubb_runtime import RuntimeManager  # noqa: E402
from ubb_supervisor import FakeClock, FakeDriver, Supervisor  # noqa: E402


class AmiExpressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=pathlib.Path(self.temp.name); self.archive=self.base/"archive"; archive.init_archive(self.archive)
        self.install=self.base/"amix"; self.source=self.base/"Amix-fixture.lha"
        with tarfile.open(self.source,"w") as bundle:
            for name,data in (("AmiExpress/Express",b"amix"),("AmiExpress/read_me.txt",b"MIT rewrite fixture")):
                info=tarfile.TarInfo(name); info.size=len(data); bundle.addfile(info,io.BytesIO(data))
        digest=hashlib.sha256(self.source.read_bytes()).hexdigest(); size=self.source.stat().st_size
        self.integration=AmiExpressAmigaIntegration(); self.integration.releases={"fixture":AmiExpressRelease("fixture","5.6.1","amix-fixture","Amix-fixture.lha","https://example.invalid/Amix-fixture.lha",digest,None,None,size)}; self.integration.default_release="fixture"
    def tearDown(self): self.temp.cleanup()
    def acquire(self,private=False): return self.integration.acquire(self.archive,local_file=self.source,release="fixture",licensed_private=private)
    def assets(self):
        kick=self.base/"kick.rom"; osimg=self.base/"os.hdf"; kick.write_bytes(b"private"); osimg.write_bytes(b"os"); return {"kickstart":kick,"amigaos_base_hdf":osimg}

    def test_profiles_and_validation(self):
        self.assertEqual(set(PROFILES),{"amiga-a500-k13","amiga-a1200-os31"}); self.assertEqual(get_profile("amiga-a500-k13").cpu,"68000"); self.assertEqual(get_profile("amiga-a1200-os31").kickstart,"3.1")
        with self.assertRaises(Exception): get_profile("unknown")
        with self.assertRaises(Exception): validate_profiles(("amiga-a1200-os31",),"amiga-a500-k13")
        self.assertFalse(any("abbs" in repr(p).lower() or "amiexpress" in repr(p).lower() for p in PROFILES.values()))

    def test_profile_assets_and_fsuae_config(self):
        with self.assertRaisesRegex(InstallError,"kickstart"): resolve_assets({},self.integration.prerequisites)
        resolved=resolve_assets(self.assets(),self.integration.prerequisites); image=self.base/"work.hdf"; image.write_bytes(b"hdf")
        cfg=write_fs_uae_config(self.base/"profile.fs-uae",runtime_profile(self.integration.profile,serial_port=6403),kickstart=resolved["kickstart"],working_hdf=image)
        self.assertIn("amiga_model = A1200",cfg.read_text()); self.assertIn("serial_port = tcp://127.0.0.1:6403/wait",cfg.read_text())

    def test_discovery_and_production_chain(self):
        self.assertEqual(IntegrationRegistry.defaults().get("amiexpress-amiga").runtime,"fs_uae")
        resolved=load_registry(ROOT/"catalog").resolve("amiexpress-main"); self.assertEqual(resolved["integration"]["id"],"amiexpress-amiga"); self.assertEqual(resolved["endpoint"]["port"],6403)
        runtime,config=RuntimeManager(load_registry(ROOT/"catalog"),self.base/"runtime").configuration("amiexpress-main"); self.assertEqual((runtime,config["stream"]["type"]),("fs_uae","tcp"))

    def test_abbs_migration_identity_and_supported_profile_unchanged(self):
        abbs=ABBSAmigaIntegration(); release=abbs.select_release("3.2-999")
        self.assertEqual(release.sha256,"5e9fd4cbf871a2bbd4579a3f9b35a0cd2187676cab8886b16adbfe8b038380e4")
        self.assertEqual(abbs.supported_profiles,("amiga-a1200-os31",)); self.assertEqual(abbs.default_profile,"amiga-a1200-os31")

    def test_family_release_unknown_and_m1_integrity(self):
        self.assertEqual(self.integration.select_release().version,"5.6.1")
        with self.assertRaises(ArtifactRequiredError): self.integration.select_release("nope")
        value=self.acquire(); obj=archive.object_path(self.archive,value["artifact"]["sha256"]); original=obj.read_bytes(); self.assertEqual(obj.stat().st_mode&0o777,0o444); self.integration.prepare(self.archive,value["id"],self.install); self.assertEqual(obj.read_bytes(),original)

    def test_private_rights_derived_and_idempotent_living_state(self):
        value=self.acquire(private=True); self.assertEqual(value["rights"]["status"],"licensed_private"); self.assertFalse(value["rights"]["redistribute_original"]); child=self.integration.prepare(self.archive,value["id"],self.install); self.assertEqual(child["preservation"]["lineage"]["parents"][0]["artifact_id"],value["id"])
        result=self.integration.install(self.archive,value["id"],self.install,assets=self.assets(),evidence=self.integration.manual_evidence); working=pathlib.Path(result.live_path); working.write_bytes(b"living"); again=self.integration.install(self.archive,value["id"],self.install,assets=self.assets(),evidence=self.integration.manual_evidence); self.assertFalse(again.changed); self.assertEqual(working.read_bytes(),b"living")

    def test_assisted_qualification_and_corruption(self):
        value=self.acquire(); self.integration.prepare(self.archive,value["id"],self.install); self.assertEqual(self.integration.configure(self.install).status,QualificationStatus.HUMAN_REQUIRED); results=self.integration.qualify(self.archive,value["id"],self.install); self.assertEqual({x.check:x.status for x in results}["login_menu"],QualificationStatus.HUMAN_REQUIRED)
        obj=archive.object_path(self.archive,value["artifact"]["sha256"]); obj.chmod(0o644); obj.write_bytes(b"bad"); self.assertEqual(self.integration.qualify(self.archive,value["id"],self.install)[0].status,QualificationStatus.FAIL)

    def test_lifecycle_route_and_failed_cleanup(self):
        registry=load_registry(ROOT/"catalog"); supervisor=Supervisor(registry,self.base/"state",driver_resolver=lambda _s:FakeDriver(),clock=FakeClock()); supervisor.reconcile(); handle=Router(registry,supervisor,self.base/"router",connectors={"tcp":MemoryConnector()}).open_session(RouteRequest("amiexpress-main",terminal=TerminalCapabilities(encoding="amiga-8bit",display="ansi",width=80,height=25))); self.assertEqual(supervisor.status("amiexpress-main")["active_session_count"],1); handle.close(); self.assertEqual(supervisor.status("amiexpress-main")["active_session_count"],0)
        with self.assertRaises(OSError): Router(registry,supervisor,self.base/"fail",connectors={"tcp":MemoryConnector(error=OSError("bridge"))}).open_session(RouteRequest("amiexpress-main")); self.assertEqual(supervisor.status("amiexpress-main")["active_session_count"],0)

    def test_guard_and_generic_core_are_product_free(self):
        self.assertEqual(prohibited_downloads(ROOT),[])
        for item in (ROOT/"scripts/ubb_archive.py",ROOT/"scripts/ubb_registry",ROOT/"scripts/ubb_supervisor",ROOT/"scripts/ubb_router",ROOT/"scripts/ubb_runtime"):
            paths=[item] if item.is_file() else item.rglob("*.py"); self.assertFalse(any("amiexpress" in p.read_text(encoding="utf8").lower() or "abbs" in p.read_text(encoding="utf8").lower() for p in paths))


if __name__=="__main__": unittest.main()
