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
import urllib.request

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
    channel: str = "stable"
    stability: str = "reference"
    purpose: str = "museum_reference"
    source_tag: str | None = None
    source_commit: str | None = None
    github_digest: str | None = None
    published_at: str | None = None
    upstream_updated_at: str | None = None


class AmiExpressAmigaIntegration:
    backup_components = {"include": ("config", "users", "messages", "files_metadata", "uploads", "doors"), "exclude": ("software", "cache", "logs", "tmp"), "consistency": "stopped"}
    id = "amiexpress-amiga"
    service_id = "amiexpress-main"
    runtime = "fs_uae"
    automation_level = "assisted"
    releases = {
        "5.6.1": AmiExpressRelease("5.6.1", "5.6.1", "amiexpress-amiga-5.6.1-original", "Amix561.lha",
            "https://aminet.net/comm/amiex/Amix561.lha", "f49d051222a4a951597d241469dab24adb198c6849cdb111734fdd8c03571f4d", "ee7986a0d89e15e63c066263fb49884af3f0791d", "f4a8d5794bfebaeb359d85d78fca3ae6", 1161960),
        "development-0f344713f30d": AmiExpressRelease(
            "development-0f344713f30d", "dev-build", "amiexpress-dev-0f344713f30d",
            "amiExpress-nightly0f344713f30da7b6a4629643e32b50094cb2bd0b.lha",
            "https://github.com/dmcoles/AmiExpress/releases/download/dev-build/amiExpress-nightly0f344713f30da7b6a4629643e32b50094cb2bd0b.lha",
            "23459a56b086a28f9cad1da59691f0867c2e15f16bc37417723fd10207e42533", None, None, 456145,
            "development", "prerelease", "current_operational", "dev-build",
            "0f344713f30da7b6a4629643e32b50094cb2bd0b", "sha256:23459a56b086a28f9cad1da59691f0867c2e15f16bc37417723fd10207e42533",
            "2023-09-12T10:33:45Z", "2026-08-10T15:34:27Z")
    }
    default_release = "5.6.1"
    current_release_key = "development-0f344713f30d"
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

    def releases_by_channel(self, channel=None):
        return [item for item in self.releases.values() if channel is None or item.channel == channel]

    @staticmethod
    def parse_github_release(document):
        """Parse one GitHub release and reject floating/ambiguous metadata."""
        if document.get("tag_name") != "dev-build" or document.get("draft") or not document.get("prerelease"):
            raise ArtifactRequiredError("GitHub metadata is not the expected published dev-build prerelease")
        assets = [item for item in document.get("assets", []) if str(item.get("name", "")).lower().endswith(".lha")]
        if len(assets) != 1:
            raise ArtifactRequiredError("GitHub dev-build must contain exactly one LHA asset")
        asset = assets[0]; digest = asset.get("digest", "")
        if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
            raise ArtifactRequiredError("GitHub dev-build asset lacks a valid SHA-256 digest")
        name = asset["name"]; commit = name.removeprefix("amiExpress-nightly").removesuffix(".lha")
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit.lower()):
            raise ArtifactRequiredError("dev-build asset does not carry a verifiable 40-character commit identity")
        return {"tag": "dev-build", "source_commit": commit, "filename": name, "source_url": asset.get("browser_download_url"),
                "github_digest": digest, "size": asset.get("size"), "published_at": document.get("published_at"),
                "upstream_updated_at": document.get("updated_at"), "release_url": document.get("html_url"),
                "prerelease": True, "release_id": document.get("id")}

    def check_updates(self, document=None):
        try:
            if document is None:
                request = urllib.request.Request("https://api.github.com/repos/dmcoles/AmiExpress/releases/tags/dev-build",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "UltimateBBSBox-M7.3a"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    document = json.load(response)
            discovered = self.parse_github_release(document)
            current = self.select_release(self.current_release_key)
            if discovered["source_commit"] == current.source_commit and discovered["github_digest"] != current.github_digest:
                return {"status": "DIGEST_MISMATCH", "release": discovered}
            if discovered["source_commit"] == current.source_commit and discovered["github_digest"] == current.github_digest:
                return {"status": "NO_CHANGE", "release": discovered}
            return {"status": "NEW_BUILD_AVAILABLE", "release": discovered}
        except ArtifactRequiredError:
            return {"status": "INVALID_UPSTREAM_METADATA"}
        except (OSError, ValueError, json.JSONDecodeError):
            return {"status": "INVALID_UPSTREAM_METADATA"}

    def _deployment_path(self, install_root):
        return pathlib.Path(install_root).resolve() / "deployment" / "amiexpress-current.json"

    def deployment_status(self, install_root):
        path = self._deployment_path(install_root)
        if not path.is_file():
            return {"current": None, "previous": None, "candidates": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def promote(self, install_root, artifact_id, *, approve_human=False):
        release = self._release_for_artifact(artifact_id)
        if release.channel != "development":
            raise ArtifactRequiredError("only development-channel releases can be promoted as current")
        root = pathlib.Path(install_root).resolve(); qualification = root / "qualification" / f"{artifact_id}.json"
        if not qualification.is_file():
            raise ArtifactRequiredError("release has no qualification record")
        results = json.loads(qualification.read_text(encoding="utf-8")).get("results", [])
        if any(item.get("status") == "FAIL" for item in results):
            raise ArtifactRequiredError("failed release cannot be promoted")
        if not approve_human and any(item.get("status") == "HUMAN_REQUIRED" for item in results):
            raise ArtifactRequiredError("operator approval is required for HUMAN_REQUIRED checks")
        state = self.deployment_status(root); old = state.get("current")
        state["previous"] = old; state["current"] = artifact_id; state.setdefault("candidates", [])
        state["candidates"] = [item for item in state["candidates"] if item != artifact_id]
        path = self._deployment_path(root); path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        temporary = path.with_name(".amiexpress-current.json.tmp"); temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n"); os.replace(temporary, path)
        return state

    def rollback(self, install_root):
        root = pathlib.Path(install_root).resolve(); state = self.deployment_status(root)
        if not state.get("previous"):
            raise ArtifactRequiredError("no previous qualified AmiExpress release is available for rollback")
        state["current"], state["previous"] = state["previous"], state.get("current")
        path = self._deployment_path(root); temporary = path.with_name(".amiexpress-current.json.tmp"); temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n"); os.replace(temporary, path)
        return state

    def _release_for_artifact(self, artifact_id):
        for release in self.releases.values():
            if release.artifact_id == artifact_id:
                return release
        raise ArtifactRequiredError(f"artifact is not a known AmiExpress release: {artifact_id}")

    def _args(self, root, release, local_file=None, source_url=None, private=False):
        development = release.channel == "development"
        return argparse.Namespace(root=str(root), artifact_id=release.artifact_id,
            file=str(local_file) if local_file else None, source_url=source_url or release.source_url,
            source_name="GitHub dmcoles/AmiExpress dev-build" if development else "Aminet comm/amiex", original_filename=release.filename,
            expected_sha256=None if private else release.sha256, expected_sha1=None if private else release.sha1,
            expected_md5=None if private else release.md5, max_bytes=64 * 1024 * 1024, timeout=60,
            rights_status="licensed_private" if private else "preservation_only",
            install_locally=True, redistribute_original=False, publish_to_bbs_filebase=False,
            no_owner_export=False, rights_evidence=[
                "The bundled read_me grants MIT terms for Darren Coles's rewrite, but the same archive includes Escom AG's licensed Installer and historical LightSpeed documentation. The mixed archive is therefore preservation-only until components are independently reviewed; local installation is allowed, redistribution and publication remain denied."],
            software_family="amiexpress", version=release.version, platform="m68k-amigaos",
            notes=("Pinned GitHub dev-build release; tag=dev-build, source_commit=" + str(release.source_commit) + "." if development else "AmiExpress BBS system redeveloped in E; Aminet comm/amiex release 5.6.1."),
            provenance=({"release_channel": release.channel, "stability": release.stability, "purpose": release.purpose,
                         "source_tag": release.source_tag, "source_commit": release.source_commit,
                         "github_digest": release.github_digest, "published_at": release.published_at,
                         "upstream_updated_at": release.upstream_updated_at} if development else {"release_channel": release.channel, "purpose": release.purpose}))

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
        document={"integration_id":"amiexpress-amiga","release":artifact_id,"artifact_id":artifact_id,"recorded_at":ubb_archive.now(),"results":[item.to_dict() for item in results]}
        payload=json.dumps(document,indent=2,sort_keys=True)+"\n"
        temporary=target/".latest.json.tmp"; temporary.write_text(payload); os.replace(temporary,target/"latest.json")
        release_file=target / f"{artifact_id}.json"; release_tmp=target / f".{artifact_id}.json.tmp"; release_tmp.write_text(payload); os.replace(release_tmp, release_file)
