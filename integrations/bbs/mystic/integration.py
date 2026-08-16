"""Mystic/Linux preservation-first reference integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

import ubb_archive
from ubb_integrations.errors import ArtifactRequiredError, InstallError
from ubb_integrations.models import InstallResult, QualificationResult, QualificationStatus


class MysticLinuxIntegration:
    id = "mystic-linux"
    service_id = "mystic-main"
    runtime = "native"
    automation_level = "assisted"
    version = "1.12.A48"
    platform = "linux-x64"
    original_filename = "mys112a48_l64.rar"
    source_url = "https://www.mysticbbs.com/downloads/mys112a48_l64.rar"
    source_name = "Mystic BBS official downloads"
    artifact_id = "mystic-linux-1.12.a48-x64-original"
    expected_sha256 = "fb427b57d9627ef93008c561df807991bdd288b4a1fc1757dfb5bb5434f286a3"
    live_names = ("data", "text", "logs", "doors", "echomail", "files", "localqwk", "msgs", "semaphore", "themes")
    live_files = ("mystic.dat", "mide.ini", "mutil.ini", "mutil.toplist.txt", "nodespy.ini")
    manual_evidence = ("version_screen", "configured_message_base")

    def _args(self, archive_root, artifact_id, local_file=None, source_url=None):
        return argparse.Namespace(
            root=str(archive_root), artifact_id=artifact_id, file=str(local_file) if local_file else None,
            source_url=source_url or self.source_url, source_name=self.source_name,
            original_filename=self.original_filename,
            expected_sha256=self.expected_sha256 if artifact_id == self.artifact_id else None, expected_sha1=None,
            expected_md5=None, max_bytes=256 * 1024 * 1024, timeout=60,
            rights_status="unknown", install_locally=True, redistribute_original=False,
            publish_to_bbs_filebase=False, no_owner_export=False,
            rights_evidence=["No authoritative redistribution grant recorded; preserve/install only pending operator license review."],
            software_family="mystic", version=self.version, platform=self.platform,
            notes="Official stable Mystic/Linux x64 distribution selected after resolving the stale pre-M7 filename.")

    def acquire(self, archive_root, *, local_file=None, source_url=None, artifact_id=None):
        artifact_id = artifact_id or self.artifact_id
        args = self._args(archive_root, artifact_id, local_file, source_url)
        if local_file is not None:
            return ubb_archive.import_artifact(args)
        return ubb_archive.acquire_http(args)

    def verify_artifacts(self, archive_root, artifact_id):
        metadata = ubb_archive.verify_one(pathlib.Path(archive_root).resolve(), artifact_id)
        if metadata["artifact"].get("software_family") != "mystic":
            raise ArtifactRequiredError("artifact is not classified as Mystic software")
        if metadata["artifact"].get("role") != "preservation_original":
            raise ArtifactRequiredError("Mystic install requires a preserved original or an explicitly supported derived source")
        if not metadata["rights"].get("install_locally", False):
            raise ArtifactRequiredError("rights do not permit local installation")
        return metadata

    @staticmethod
    def _safe_member(name):
        value = pathlib.PurePosixPath(name)
        return not value.is_absolute() and ".." not in value.parts

    def _extract(self, source, filename, destination):
        try:
            if tarfile.is_tarfile(source):
                with tarfile.open(source) as archive:
                    members = archive.getmembers()
                    if any(not self._safe_member(item.name) or item.issym() or item.islnk() for item in members):
                        raise InstallError("archive contains unsafe paths or links")
                    archive.extractall(destination, filter="data")
            elif filename.lower().endswith(".zip"):
                with zipfile.ZipFile(source) as archive:
                    if any(not self._safe_member(item.filename) for item in archive.infolist()):
                        raise InstallError("archive contains unsafe paths")
                    archive.extractall(destination)
            elif filename.lower().endswith(".rar"):
                extractor = pathlib.Path("/usr/bin/unrar")
                if not extractor.is_file():
                    raise InstallError("RAR installation requires /usr/bin/unrar; acquisition and verification remain usable")
                completed = subprocess.run([str(extractor), "x", "-idq", "-o+", str(source), f"{destination}/"],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.PIPE, timeout=60, check=False)
                if completed.returncode:
                    raise InstallError(f"RAR extractor exited {completed.returncode}")
            else:
                raise InstallError(f"unsupported Mystic distribution container: {filename}")
        except (tarfile.TarError, zipfile.BadZipFile, OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError(f"cannot extract Mystic distribution: {exc}") from exc

    def install(self, archive_root, artifact_id, install_root):
        archive_root = pathlib.Path(archive_root).resolve()
        install_root = pathlib.Path(install_root).resolve()
        metadata = self.verify_artifacts(archive_root, artifact_id)
        digest = metadata["artifact"]["sha256"]
        source = ubb_archive.object_path(archive_root, digest)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        releases = install_root / "software" / "releases"
        release = releases / digest
        live = install_root / "live"
        releases.mkdir(parents=True, exist_ok=True, mode=0o750)
        live.mkdir(parents=True, exist_ok=True, mode=0o750)
        changed = not release.exists()
        if changed:
            staging = pathlib.Path(tempfile.mkdtemp(prefix=".mystic-release.", dir=releases))
            try:
                self._extract(source, metadata["artifact"]["original_filename"], staging)
                candidates = sorted(p for p in staging.rglob("mis") if p.is_file())
                if not candidates:
                    installers = sorted(p for p in staging.rglob("install") if p.is_file())
                    if installers:
                        with tempfile.TemporaryDirectory(prefix="ubb-mi-") as short_root:
                            payload = pathlib.Path(short_root) / "p"
                            completed = subprocess.run([str(installers[0]), "auto", str(payload) + os.sep], cwd=installers[0].parent,
                                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                       stderr=subprocess.PIPE, timeout=60, check=False)
                            if completed.returncode:
                                raise InstallError(f"Mystic installer exited {completed.returncode}")
                            normalized = staging.with_name(staging.name + ".installed")
                            shutil.move(str(payload), normalized)
                        shutil.rmtree(staging); staging = normalized
                        candidates = sorted(p for p in staging.rglob("mis") if p.is_file())
                if not candidates:
                    raise InstallError("distribution does not contain the Mystic 'mis' executable")
                payload = candidates[0].parent
                if payload != staging:
                    normalized = staging.with_name(staging.name + ".normalized")
                    os.replace(payload, normalized)
                    shutil.rmtree(staging)
                    staging = normalized
                for name in self.live_names:
                    live_dir = live / name
                    live_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
                    bundled = staging / name
                    if bundled.exists() and bundled.is_dir():
                        for item in bundled.iterdir():
                            target = live_dir / item.name
                            if not target.exists():
                                shutil.move(str(item), target)
                        bundled.rmdir()
                    if not bundled.exists():
                        bundled.symlink_to(pathlib.Path("../../../live") / name)
                live_config = live / "config"; live_config.mkdir(parents=True, exist_ok=True, mode=0o750)
                for name in self.live_files:
                    bundled = staging / name; target = live_config / name
                    if bundled.exists() and not target.exists():
                        shutil.move(str(bundled), target)
                    if bundled.exists():
                        bundled.unlink()
                    if target.exists():
                        bundled.symlink_to(pathlib.Path("../../../live/config") / name)
                for path in sorted(staging.rglob("*")):
                    if path.is_symlink():
                        continue
                    path.chmod(0o750 if path.is_dir() or path.stat().st_mode & 0o111 else 0o640)
                (staging / ".ubb-install.json").write_text(json.dumps({"artifact_id": artifact_id, "sha256": digest}, sort_keys=True) + "\n")
                (staging / ".ubb-install.json").chmod(0o640)
                os.replace(staging, release)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        current = install_root / "software" / "current"
        temporary_link = install_root / "software" / ".current.new"
        temporary_link.unlink(missing_ok=True)
        temporary_link.symlink_to(pathlib.Path("releases") / digest)
        os.replace(temporary_link, current)
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise InstallError("preservation object changed during installation")
        return InstallResult(artifact_id, digest, str(release), str(live), changed, self.manual_evidence)

    def configure(self, install_root, evidence=()):
        evidence = tuple(sorted(set(evidence)))
        missing = tuple(item for item in self.manual_evidence if item not in evidence)
        return QualificationResult("first_run_configuration",
                                   QualificationStatus.HUMAN_REQUIRED if missing else QualificationStatus.PASS,
                                   "Run software/current/mis -cfg; living configuration is retained under live/." if missing else "Required operator evidence recorded.",
                                   evidence)

    def qualify(self, archive_root, artifact_id, install_root, *, evidence=(), runtime_ready=None,
                route_open=None, clean_stop=None, live_state_survived=None):
        results = []
        try:
            metadata = self.verify_artifacts(archive_root, artifact_id)
            results.append(QualificationResult("artifact_verified", QualificationStatus.PASS, metadata["artifact"]["sha256"]))
        except Exception as exc:
            results = [QualificationResult("artifact_verified", QualificationStatus.FAIL, str(exc))]
            self._record_qualification(install_root, artifact_id, results)
            return results
        marker = pathlib.Path(install_root) / "software" / "releases" / metadata["artifact"]["sha256"] / ".ubb-install.json"
        results.append(QualificationResult("expected_files", QualificationStatus.PASS if marker.is_file() else QualificationStatus.FAIL,
                                           "verified install marker present" if marker.is_file() else "install marker missing"))
        results.append(self.configure(install_root, evidence))
        for check, value in (("runtime_readiness", runtime_ready), ("route_connectivity", route_open),
                             ("clean_stop", clean_stop), ("live_state_survives_restart", live_state_survived)):
            status = QualificationStatus.PASS if value is True else QualificationStatus.FAIL if value is False else QualificationStatus.SKIP
            results.append(QualificationResult(check, status, "observed" if value is not None else "not exercised in this qualification run"))
        results.append(QualificationResult("login_menu", QualificationStatus.HUMAN_REQUIRED,
                                           "Confirm Mystic login/menu behavior after assisted MIS configuration.", tuple(evidence)))
        self._record_qualification(install_root, artifact_id, results)
        return results

    @staticmethod
    def _record_qualification(install_root, artifact_id, results):
        target = pathlib.Path(install_root) / "qualification"
        target.mkdir(parents=True, exist_ok=True, mode=0o750)
        document = {"integration_id": "mystic-linux", "artifact_id": artifact_id,
                    "recorded_at": ubb_archive.now(), "results": [item.to_dict() for item in results]}
        temporary = target / ".latest.json.tmp"
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, target / "latest.json")
