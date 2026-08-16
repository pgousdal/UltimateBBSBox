"""Preservation-first AmiExpress family integration using generic Amiga helpers."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile

import ubb_archive
from ubb_integrations.amiga import copy_working_image, resolve_assets, runtime_profile, write_fs_uae_config
from ubb_integrations.errors import ArtifactRequiredError, InstallError
from ubb_integrations.models import InstallResult, QualificationResult, QualificationStatus
from ubb_integrations.profiles import get_profile, validate_profiles


@dataclass(frozen=True)
class AmiExpressRelease:
    key: str
    version: str
    artifact_id: str
    filename: str
    source_url: str
    sha256: str | None = None
    sha1: str | None = None
    md5: str | None = None
    size: int | None = None


class AmiExpressAmigaIntegration:
    id = "amiexpress-amiga"
    service_id = "amiexpress-main"
    runtime = "fs_uae"
    automation_level = "assisted"
    releases = {
        "5.6.1": AmiExpressRelease("5.6.1", "5.6.1", "amiexpress-amiga-5.6.1-original", "Amix561.lha",
            "https://aminet.net/comm/amiex/Amix561.lha")
    }
    default_release = "5.6.1"
    supported_profiles = ("amiga-a1200-os31",)
    default_profile = "amiga-a1200-os31"
    manual_evidence = ("amiexpress_installed", "base_configuration_completed", "golden_image_qualified")

    @property
    def profile(self):
        validate_profiles(self.supported_profiles, self.default_profile)
        return get_profile(self.default_profile)

    @property
    def prerequisites(self):
        return self.profile.assets

    @property
    def artifact_id(self):
        return self.select_release().artifact_id

    def select_release(self, key=None):
        try:
            return self.releases[key or self.default_release]
        except KeyError as exc:
            raise ArtifactRequiredError(f"unknown AmiExpress release: {key}") from exc

    def _release_for_artifact(self, artifact_id):
        for release in self.releases.values():
            if release.artifact_id == artifact_id:
                return release
        raise ArtifactRequiredError(f"artifact is not a known AmiExpress release: {artifact_id}")

    def _args(self, root, release, local_file=None, source_url=None, private=False):
        return argparse.Namespace(root=str(root), artifact_id=release.artifact_id,
            file=str(local_file) if local_file else None, source_url=source_url or release.source_url,
            source_name="Aminet comm/amiex", original_filename=release.filename,
            expected_sha256=None if private else release.sha256, expected_sha1=None if private else release.sha1,
            expected_md5=None if private else release.md5, max_bytes=64 * 1024 * 1024, timeout=60,
            rights_status="licensed_private" if private else "preservation_only",
            install_locally=True, redistribute_original=False, publish_to_bbs_filebase=False,
            no_owner_export=False, rights_evidence=[
                "The bundled read_me grants MIT terms for Darren Coles's rewrite, but the same archive includes Escom AG's licensed Installer and historical LightSpeed documentation. The mixed archive is therefore preservation-only until components are independently reviewed; local installation is allowed, redistribution and publication remain denied."],
            software_family="amiexpress", version=release.version, platform="m68k-amigaos",
            notes="AmiExpress BBS system redeveloped in E; Aminet comm/amiex release 5.6.1.")

    def acquire(self, archive_root, *, local_file=None, source_url=None, artifact_id=None, release=None, licensed_private=False):
        selected = self.select_release(release) if artifact_id is None else self._release_for_artifact(artifact_id)
        args = self._args(archive_root, selected, local_file, source_url, licensed_private)
        return ubb_archive.import_artifact(args) if local_file else ubb_archive.acquire_http(args)

    def verify_artifacts(self, archive_root, artifact_id):
        release = self._release_for_artifact(artifact_id)
        metadata = ubb_archive.verify_one(pathlib.Path(archive_root).resolve(), artifact_id)
        artifact = metadata["artifact"]
        if artifact.get("software_family") != "amiexpress" or artifact.get("role") != "preservation_original":
            raise ArtifactRequiredError("AmiExpress requires a classified preservation original")
        if not metadata["rights"].get("install_locally"):
            raise ArtifactRequiredError("rights do not permit local installation")
        if metadata["rights"].get("redistribute_original") or metadata["rights"].get("publish_to_bbs_filebase"):
            raise ArtifactRequiredError("AmiExpress redistribution/publication is denied without explicit evidence")
        if release.sha256 and artifact["sha256"] != release.sha256 and metadata["rights"]["status"] != "licensed_private":
            raise ArtifactRequiredError("artifact does not match the selected AmiExpress release")
        return metadata

    @staticmethod
    def _extract(source, destination):
        if tarfile.is_tarfile(source):
            with tarfile.open(source) as archive:
                members = archive.getmembers()
                if any(pathlib.PurePosixPath(m.name).is_absolute() or ".." in pathlib.PurePosixPath(m.name).parts or m.issym() or m.islnk() for m in members):
                    raise InstallError("archive contains unsafe paths or links")
                archive.extractall(destination, filter="data")
                return
        lha = shutil.which("lha")
        if not lha:
            raise InstallError("preparation requires the lha extractor")
        result = subprocess.run([lha, "x", str(source)], cwd=destination, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60, check=False)
        if result.returncode:
            raise InstallError(f"lha extractor exited {result.returncode}")

    def prepare(self, archive_root, artifact_id, install_root, derived_artifact_id=None):
        root = pathlib.Path(archive_root).resolve(); install_root = pathlib.Path(install_root).resolve()
        metadata = self.verify_artifacts(root, artifact_id)
        source = ubb_archive.object_path(root, metadata["artifact"]["sha256"])
        derived_id = derived_artifact_id or f"{artifact_id}-install-tree"
        try:
            return ubb_archive.verify_one(root, derived_id)
        except (FileNotFoundError, ubb_archive.ArchiveError):
            pass
        workspace = install_root / "installation" / metadata["artifact"]["sha256"]
        workspace.mkdir(parents=True, exist_ok=True, mode=0o750)
        with tempfile.TemporaryDirectory(prefix="ubb-amiexpress-") as temp:
            extracted = pathlib.Path(temp) / "tree"; extracted.mkdir()
            before = hashlib.sha256(source.read_bytes()).hexdigest(); self._extract(source, extracted)
            bundle = pathlib.Path(temp) / "amiexpress-install-tree.tar"
            with tarfile.open(bundle, "w") as archive:
                for item in sorted(extracted.rglob("*")):
                    info = archive.gettarinfo(str(item), item.relative_to(extracted).as_posix()); info.mtime = 0; info.uid = info.gid = 0; info.uname = info.gname = ""
                    if item.is_file():
                        with item.open("rb") as handle: archive.addfile(info, handle)
                    elif item.is_dir(): archive.addfile(info)
            shutil.copytree(extracted, workspace, dirs_exist_ok=True)
            args = self._args(root, self._release_for_artifact(artifact_id)); args.parent=[artifact_id]
            args.file=str(bundle); args.artifact_id=derived_id; args.original_filename="amiexpress-install-tree.tar"
            args.role="derived_install_media"; args.action="extract AmiExpress archive into deterministic installation tree"; args.tool="lha/tar"; args.notes="Host preparation only; Workbench installation remains assisted."
            args.expected_sha256=args.expected_sha1=args.expected_md5=None
            result = ubb_archive.derive(args)
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                raise InstallError("preservation object changed during preparation")
            return result

    def install(self, archive_root, artifact_id, install_root, *, assets=None, evidence=()):
        install_root = pathlib.Path(install_root).resolve(); metadata = self.verify_artifacts(archive_root, artifact_id)
        self.prepare(archive_root, artifact_id, install_root)
        resolved = resolve_assets(assets or {}, self.prerequisites)
        golden = install_root / "golden" / "amiexpress.hdf"; working = install_root / "live" / "amiexpress-working.hdf"
        golden.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        if "golden_image_qualified" in evidence and not golden.exists():
            shutil.copyfile(resolved["amigaos_base_hdf"], golden, follow_symlinks=False); golden.chmod(0o440)
        changed = copy_working_image(golden, working) if golden.exists() else False
        if golden.exists():
            write_fs_uae_config(install_root / "runtime" / "amiexpress.fs-uae", runtime_profile(self.profile, serial_port=6403), kickstart=resolved["kickstart"], working_hdf=working)
        return InstallResult(artifact_id, metadata["artifact"]["sha256"], str(golden), str(working), changed, self.manual_evidence)

    def configure(self, install_root, evidence=()):
        missing = tuple(item for item in self.manual_evidence if item not in set(evidence))
        return QualificationResult("assisted_amiexpress_install", QualificationStatus.HUMAN_REQUIRED if missing else QualificationStatus.PASS,
            "Install the prepared tree in Workbench, complete base AmiExpress configuration, remove private data, and approve a golden image.", tuple(evidence))

    def qualify(self, archive_root, artifact_id, install_root, *, evidence=(), **observations):
        results=[]
        try:
            metadata=self.verify_artifacts(archive_root, artifact_id); results.append(QualificationResult("artifact_integrity", QualificationStatus.PASS, metadata["artifact"]["sha256"]))
            derived=ubb_archive.verify_one(pathlib.Path(archive_root).resolve(), f"{artifact_id}-install-tree")
            parents=derived.get("preservation", {}).get("lineage", {}).get("parents", [])
            results.append(QualificationResult("derived_lineage", QualificationStatus.PASS if any(p["artifact_id"]==artifact_id for p in parents) else QualificationStatus.FAIL, "derived installation tree names its immutable parent"))
        except Exception as exc:
            results=[QualificationResult("artifact_integrity", QualificationStatus.FAIL, str(exc))]; self._record(install_root, artifact_id, results); return results
        results.append(self.configure(install_root, evidence))
        for check in ("amiga_boot", "amiexpress_start", "meaningful_readiness", "route_connectivity", "terminal_roundtrip", "login_menu", "clean_stop", "clean_restart", "living_state_survives", "on_demand", "always_on", "scheduled_maintenance"):
            value=observations.get(check); status=QualificationStatus.PASS if value is True else QualificationStatus.FAIL if value is False else QualificationStatus.HUMAN_REQUIRED
            results.append(QualificationResult(check,status,"observed" if value is not None else "requires licensed assets and operator observation"))
        self._record(install_root, artifact_id, results); return results

    @staticmethod
    def _record(install_root, artifact_id, results):
        target=pathlib.Path(install_root)/"qualification"; target.mkdir(parents=True, exist_ok=True, mode=0o750)
        document={"integration_id":"amiexpress-amiga","release":"5.6.1","artifact_id":artifact_id,"recorded_at":ubb_archive.now(),"results":[item.to_dict() for item in results]}
        temporary=target/".latest.json.tmp"; temporary.write_text(json.dumps(document,indent=2,sort_keys=True)+"\n"); os.replace(temporary,target/"latest.json")
