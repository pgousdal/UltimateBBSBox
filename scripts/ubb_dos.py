"""Product-neutral DOS BBS runtime and deployment foundation.

This module describes DOS guests and their isolation boundaries.  It deliberately
does not install or download DOS media, and it does not contain BBS product logic.
"""
from __future__ import annotations

import argparse
import datetime
import json
import platform
import re
import shutil
import hashlib
import os
import subprocess
import tarfile
import tempfile
import zipfile
import threading
from dataclasses import dataclass, field
from pathlib import Path


class DOSConfigError(ValueError):
    pass


class DOSProvisioningError(DOSConfigError):
    """A required preserved DOS input is absent or fails verification."""


@dataclass(frozen=True)
class PinnedDOSInput:
    """Content-addressed input required by the qualified Debian DOS stack."""
    artifact_id: str
    sha256: str
    size: int
    role: str


DOSEMU2_SOURCE = PinnedDOSInput(
    "dosemu2-82770aba3984", "8a08d60590329aa1484f0fa499711793ab3b87bf401d6a6e6eb2f42a93acddfb", 3053938, "source_code")
FDPP_SOURCE = PinnedDOSInput(
    "fdpp-dc776d6a348b", "fd6e4332ab3756acff10511d7a97af8c6eb231861341f8b4194b22011a8dc749", 327763, "source_code")
FREEDOS_M1 = PinnedDOSInput(
    "freedos-1.4-livecd", "2020ff6bb681967fd6eff8f51ad2e5cd5ab4421165948cef4246e4f7fcaf6339", 293950337, "preservation_original")


BACKENDS = ("dosemu2", "dosbox_x", "dosbox_staging", "qemu")
PRODUCTION_OS = "debian"
GUEST_FAMILIES = ("freedos", "msdos", "drdos", "other_dos")
ENCODINGS = ("CP437", "CP850", "ISO-8859-1", "UTF-8", "adapter_defined")
NEWLINES = ("CR", "LF", "CRLF")
CAPABILITIES = ("byte_stream", "modem_signals", "full_modem_emulation")
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_DOS_NAME = re.compile(r"^[A-Za-z0-9_$~!#%&'()@^`{}-]+(?:\.[A-Za-z0-9_$~!#%&'()@^`{}-]+)?$")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


@dataclass(frozen=True)
class MachineProfile:
    cpu: str = "486"
    conventional_kb: int = 640
    xms_kb: int = 16384
    ems_kb: int = 4096
    serial_ports: int = 4
    text_mode: bool = True
    headless: bool = True

    def __post_init__(self):
        if self.cpu not in ("8086", "286", "386", "486", "pentium"):
            raise DOSConfigError("unsupported DOS CPU class")
        if not 128 <= self.conventional_kb <= 640 or self.xms_kb < 0 or self.ems_kb < 0:
            raise DOSConfigError("invalid DOS memory limits")
        if not 1 <= self.serial_ports <= 4:
            raise DOSConfigError("DOS serial port count must be 1..4")


@dataclass(frozen=True)
class DOSProfile:
    profile_id: str
    guest_family: str = "freedos"
    version: str = "14.0"
    machine: MachineProfile = field(default_factory=MachineProfile)
    codepage: str = "CP437"
    timezone_policy: str = "host_local_time"
    config_template: str = ""
    autoexec_template: str = ""
    rights: str = "open"

    def __post_init__(self):
        if not _ID.fullmatch(self.profile_id):
            raise DOSConfigError("invalid DOS profile ID")
        if self.guest_family not in GUEST_FAMILIES:
            raise DOSConfigError("unsupported DOS guest family")
        if self.codepage not in ENCODINGS:
            raise DOSConfigError("unsupported DOS codepage")
        if self.timezone_policy not in ("host_local_time", "host_utc", "fixed_historical"):
            raise DOSConfigError("invalid DOS timezone policy")
        if self.guest_family in ("msdos", "drdos") and self.rights not in ("licensed_private", "unknown"):
            raise DOSConfigError("proprietary DOS profiles require private rights metadata")


def default_profiles() -> dict[str, DOSProfile]:
    return {"freedos-bbs": DOSProfile("freedos-bbs")}


@dataclass(frozen=True)
class TerminalProfile:
    codepage: str = "CP437"
    columns: int = 80
    rows: int = 25
    newline: str = "CRLF"
    baud: int | None = 19200
    binary_safe: bool = True

    def __post_init__(self):
        if self.codepage not in ENCODINGS or self.newline not in NEWLINES:
            raise DOSConfigError("invalid terminal encoding/newline policy")
        if self.columns < 1 or self.rows < 1 or (self.baud is not None and self.baud <= 0):
            raise DOSConfigError("invalid terminal dimensions or baud")


@dataclass(frozen=True)
class COMPort:
    name: str
    kind: str = "pty"
    endpoint: str = ""
    baud: int = 19200
    flow_control: str = "none"
    capability: str = "byte_stream"

    def __post_init__(self):
        if self.name not in {f"COM{i}" for i in range(1, 5)}:
            raise DOSConfigError("DOS COM port must be COM1..COM4")
        if self.kind not in ("pty", "tcp", "physical_serial", "modem"):
            raise DOSConfigError("unsupported COM endpoint kind")
        if self.capability not in CAPABILITIES or self.baud <= 0 or not self.endpoint:
            raise DOSConfigError("invalid COM endpoint")
        if self.kind == "physical_serial" and not self.endpoint.startswith("/dev/"):
            raise DOSConfigError("physical serial endpoint must be an explicit /dev path")


@dataclass(frozen=True)
class DriveMapping:
    letter: str
    root: Path
    writable: bool = False
    purpose: str = "data"

    def __post_init__(self):
        if not re.fullmatch(r"[A-Z]", self.letter) or not self.root.is_absolute() or self.root == Path("/"):
            raise DOSConfigError("drive mapping requires a safe absolute root")
        if ".." in self.root.parts:
            raise DOSConfigError("drive mapping may not contain parent traversal")


def validate_drive_root(mapping: DriveMapping, allowed_root: Path) -> Path:
    """Resolve a mapping and require it to stay below an explicit deployment root."""
    allowed = allowed_root.resolve()
    resolved = mapping.root.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise DOSConfigError("DOS drive mapping escapes its deployment root") from exc
    return resolved


@dataclass(frozen=True)
class DOSDeployment:
    service_id: str
    profile: DOSProfile
    golden_root: Path
    working_root: Path
    drives: tuple[DriveMapping, ...] = ()
    com_ports: tuple[COMPort, ...] = ()
    node_count: int = 1
    guest_network: bool = False
    lifecycle: str = "on_demand"

    def __post_init__(self):
        if not _ID.fullmatch(self.service_id) or not self.golden_root.is_absolute() or not self.working_root.is_absolute():
            raise DOSConfigError("invalid DOS deployment identity/root")
        if self.golden_root == self.working_root or self.node_count < 1:
            raise DOSConfigError("working DOS state must be separate from golden state")
        if self.lifecycle not in ("always_on", "on_demand", "scheduled"):
            raise DOSConfigError("invalid DOS lifecycle")
        names = [p.name for p in self.com_ports]
        if len(names) != len(set(names)):
            raise DOSConfigError("duplicate DOS COM assignment")
        letters = [d.letter for d in self.drives]
        if len(letters) != len(set(letters)):
            raise DOSConfigError("duplicate DOS drive mapping")

    def materialize_plan(self) -> dict:
        return {"service_id": self.service_id, "profile": self.profile.profile_id,
                "golden_root": str(self.golden_root), "working_root": str(self.working_root),
                "drives": [{"letter": d.letter, "root": str(d.root), "writable": d.writable} for d in self.drives],
                "com_ports": [p.name for p in self.com_ports], "node_count": self.node_count,
                "guest_network": self.guest_network, "lifecycle": self.lifecycle}


def validate_dos_filename(name: str) -> str:
    if not name or "/" in name or "\\" in name or not _DOS_NAME.fullmatch(name):
        raise DOSConfigError("invalid DOS 8.3 filename")
    stem = name.split(".", 1)[0].upper()
    if stem in _RESERVED:
        raise DOSConfigError("DOS device name is not a filename")
    if len(stem) > 8 or ("." in name and len(name.split(".", 1)[1]) > 3):
        raise DOSConfigError("filename is not 8.3 compatible")
    return name.upper()


class NodeAllocator:
    """Thread-safe, idempotent multinode allocation with stale recovery."""
    def __init__(self, capacity: int):
        if capacity < 1: raise DOSConfigError("node capacity must be positive")
        self.capacity = capacity; self._allocated: dict[int, str] = {}; self._lock = threading.RLock()

    def allocate(self, session_id: str) -> int:
        with self._lock:
            for node, owner in self._allocated.items():
                if owner == session_id: return node
            for node in range(1, self.capacity + 1):
                if node not in self._allocated:
                    self._allocated[node] = session_id; return node
        raise DOSConfigError("DOS node capacity exhausted")

    def release(self, node: int, session_id: str | None = None) -> bool:
        with self._lock:
            if node not in self._allocated or (session_id is not None and self._allocated[node] != session_id): return False
            del self._allocated[node]; return True

    def recover_stale(self, active_sessions: set[str]) -> int:
        with self._lock:
            stale = [n for n, owner in self._allocated.items() if owner not in active_sessions]
            for node in stale: del self._allocated[node]
            return len(stale)

    def status(self) -> dict: 
        with self._lock: return {"capacity": self.capacity, "active": len(self._allocated), "nodes": dict(self._allocated)}


def qualification(deployment: DOSDeployment, *, backend_available: bool = False, guest_available: bool = False) -> dict:
    checks = [{"name": "profile", "status": "PASS"}, {"name": "isolation", "status": "PASS"},
              {"name": "backend", "status": "PASS" if backend_available else "HUMAN_REQUIRED"},
              {"name": "guest_boot", "status": "PASS" if guest_available else "HUMAN_REQUIRED"}]
    return {"service_id": deployment.service_id, "qualification": checks,
            "status": "PASS" if all(x["status"] == "PASS" for x in checks) else "HUMAN_REQUIRED"}


def backend_evidence(backend: str = "dosemu2") -> dict:
    """Report installed backend evidence without installing or downloading anything."""
    executable = shutil.which(backend)
    return {"backend": backend, "executable": executable, "available": bool(executable),
            "version": None, "source": "PATH" if executable else None,
            "host": {"os": platform.platform(), "architecture": platform.machine()}}


def debian_provisioning_plan(*, target_os: str = PRODUCTION_OS, release: str | None = None,
                             package_available: bool = False, package_version: str | None = None,
                             source_commit: str | None = None, source_sha256: str | None = None) -> dict:
    """Return a Debian-first plan; never selects an Ubuntu PPA implicitly."""
    if target_os.lower() != PRODUCTION_OS:
        raise DOSConfigError("DOS runtime production provisioning requires Debian")
    if package_available and not package_version:
        raise DOSConfigError("a Debian package plan requires an exact package version")
    if not package_available and bool(source_commit) != bool(source_sha256):
        raise DOSConfigError("source fallback requires an immutable commit and SHA-256")
    if source_commit and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise DOSConfigError("source fallback must use a full immutable commit")
    method = "apt" if package_available else ("pinned_source" if source_commit else "blocked")
    return {"production_os": PRODUCTION_OS, "release": release, "method": method,
            "package": "dosemu2" if package_available else None, "version": package_version,
            "source_commit": source_commit, "source_sha256": source_sha256,
            "install_prefix": f"/opt/ultimate-bbs-box/dosemu2/{source_commit[:12]}" if source_commit else None,
            "ubuntu_ppa": False, "reason": "Debian package first; immutable source fallback only"}


def freedos_release_metadata(*, version: str = "1.4", artifact: str | None = None,
                             sha256: str | None = None, source_url: str | None = None) -> dict:
    """Require observed artifact identity; never invent a filename or checksum."""
    if version != "1.4":
        raise DOSConfigError("M9.1b reference guest is FreeDOS 1.4")
    state = "VERIFIED" if artifact and sha256 and source_url else "HUMAN_REQUIRED"
    return {"version": version, "artifact": artifact, "sha256": sha256, "source_url": source_url,
            "state": state, "preservation": "M1_REQUIRED"}


def verify_preserved_input(archive_root: str | Path, expected: PinnedDOSInput,
                           *, artifact_id: str | None = None) -> dict:
    """Verify an immutable M1 archive object before a DOS build can consume it.

    This deliberately accepts no URL and performs no acquisition.  Acquisition is
    an M1 operation; provisioning is only allowed to consume an existing object.
    """
    try:
        from ubb_archive import load_metadata, object_path, require_archive
    except ImportError as exc:  # pragma: no cover - only occurs in broken installs
        raise DOSProvisioningError("preservation archive support is unavailable") from exc
    root = Path(archive_root).expanduser().resolve()
    require_archive(root)
    aid = artifact_id or expected.artifact_id
    metadata = load_metadata(root, aid)
    artifact = metadata["artifact"]
    if artifact["sha256"].lower() != expected.sha256:
        raise DOSProvisioningError(f"{aid}: metadata digest is not the pinned digest")
    if expected.size and int(artifact["size"]) != expected.size:
        raise DOSProvisioningError(f"{aid}: metadata size is not the pinned size")
    allowed_roles = {expected.role}
    if expected.role == "source_code":
        # M1's immutable upstream import is normally classified as the
        # preservation_original; source_code is the role consumed by builds.
        allowed_roles.add("preservation_original")
    if artifact["role"] not in allowed_roles:
        raise DOSProvisioningError(f"{aid}: preservation role is not {expected.role}")
    path = object_path(root, expected.sha256)
    if not path.is_file() or path.is_symlink():
        raise DOSProvisioningError(f"{aid}: immutable object is missing or is a symlink")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if digest.hexdigest() != expected.sha256 or (expected.size and size != expected.size):
        raise DOSProvisioningError(f"{aid}: object bytes do not match the pinned identity")
    return {"artifact_id": aid, "path": str(path), "sha256": digest.hexdigest(),
            "size": size, "role": artifact["role"],
            "rights": metadata["rights"], "source": metadata["provenance"]}


def provisioning_manifest(archive_root: str | Path, runtime_root: str | Path,
                          *, dosemu_artifact_id: str | None = None,
                          fdpp_artifact_id: str | None = None) -> dict:
    """Return the verified, deterministic input manifest for Debian provisioning.

    Runtime/build paths are intentionally outside the archive.  Calling this twice
    is read-only and therefore safe for idempotent provisioning orchestration.
    """
    inputs = {
        "dosemu2": verify_preserved_input(archive_root, DOSEMU2_SOURCE,
                                           artifact_id=dosemu_artifact_id),
        "fdpp": verify_preserved_input(archive_root, FDPP_SOURCE,
                                       artifact_id=fdpp_artifact_id),
        "freedos": verify_preserved_input(archive_root, FREEDOS_M1),
    }
    runtime = Path(runtime_root).expanduser().resolve()
    archive = Path(archive_root).expanduser().resolve()
    if runtime == archive or archive in runtime.parents:
        raise DOSProvisioningError("runtime/build state must be outside the preservation archive")
    return {"format": "ubb-dos-provisioning-v1", "production_os": PRODUCTION_OS,
            "dosemu2_commit": "82770aba398485117c56523a1a5c261f6e37ca64",
            "fdpp_commit": "dc776d6a348bff023c71f250a13813b4fee8f517",
            "runtime_root": str(runtime), "inputs": inputs,
            "idempotence": "content-addressed-inputs-and-keyed-runtime"}


DEBIAN_BUILD_PACKAGES = (
    "autoconf", "automake", "bison", "clang", "flex", "gawk", "gettext",
    "gcc-multilib", "g++-multilib", "libc6-dev-i386",
    "libasound2-dev", "libelf-dev", "libgpm-dev", "libjson-c-dev",
    "libslang2-dev", "libslirp-dev", "libtool", "libudev-dev", "libsdl2-dev",
    "meson", "nasm", "ninja-build", "pkg-config", "python3-ply", "zlib1g-dev",
)


def _safe_extract_tar(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source, "r:*") as archive:
        members = archive.getmembers()
        root = destination.resolve()
        for member in members:
            target = (root / member.name).resolve()
            if root != target and root not in target.parents:
                raise DOSProvisioningError("source archive contains path traversal")
            if member.issym() or member.islnk():
                link = (root / member.name).resolve()
                if root not in link.parents:
                    raise DOSProvisioningError("source archive contains unsafe link")
        archive.extractall(root)
    children = [item for item in destination.iterdir()]
    if len(children) != 1 or not children[0].is_dir():
        raise DOSProvisioningError("source archive must contain one top-level directory")
    return children[0]


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _patch_fdpp_meson(source: Path) -> None:
    """Apply the documented Meson 1.7 compatibility fix in disposable state."""
    path = source / "subprojects" / "libfdpp" / "meson.build"
    if not path.is_file():
        raise DOSProvisioningError("FDPP source layout is missing libfdpp/meson.build")
    text = path.read_text(encoding="utf-8")
    patched = re.sub(r"^\s*depends: tgbin,\s*$\n?", "", text, flags=re.MULTILINE)
    if patched != text:
        path.write_text(patched, encoding="utf-8")


def provision_runtime(archive_root: str | Path, runtime_root: str | Path,
                      build_root: str | Path, *, install_dependencies: bool = False) -> dict:
    """Build the pinned DOSEMU2/FDPP pair from verified M1 source objects.

    The function is deliberately Debian-only and content-addressed.  Existing
    keyed build/install directories are reused after their manifest verifies,
    making a second invocation idempotent.  It never downloads or writes below
    the preservation archive.
    """
    if platform.system() != "Linux" or not Path("/etc/debian_version").is_file():
        raise DOSProvisioningError("DOS runtime provisioning requires Debian Linux")
    archive = Path(archive_root).expanduser().resolve()
    runtime = Path(runtime_root).expanduser().resolve()
    build = Path(build_root).expanduser().resolve()
    manifest = provisioning_manifest(archive, runtime)
    if archive == runtime or archive in runtime.parents or archive == build or archive in build.parents:
        raise DOSProvisioningError("build/runtime state must be outside the preservation archive")
    if install_dependencies:
        if os.geteuid() != 0:
            raise DOSProvisioningError("install_dependencies requires root")
        subprocess.run(["apt-get", "update"], check=True)
        subprocess.run(["apt-get", "install", "-y", *DEBIAN_BUILD_PACKAGES], check=True)
    runtime.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    prefix = runtime / "82770aba3984"
    marker = prefix / "ubb-provisioning.json"
    if marker.is_file() and marker.read_text(encoding="utf-8") == json.dumps(manifest, indent=2, sort_keys=True) + "\n":
        return manifest | {"status": "already-present", "prefix": str(prefix)}
    dosemu_tar = Path(manifest["inputs"]["dosemu2"]["path"])
    fdpp_tar = Path(manifest["inputs"]["fdpp"]["path"])
    dosemu_src = _safe_extract_tar(dosemu_tar, build / "dosemu2-82770aba3984")
    fdpp_src = _safe_extract_tar(fdpp_tar, build / "fdpp-dc776d6a348b")
    env = os.environ.copy()
    env["PREFIX"] = str(prefix)
    fdpp_build = fdpp_src / "build"
    _patch_fdpp_meson(fdpp_src)
    fdpp_env = env.copy()
    fdpp_env["PKG_CONFIG_LIBDIR"] = "/usr/lib/i386-linux-gnu/pkgconfig:/usr/share/pkgconfig"
    fdpp_env["LDFLAGS"] = "-m32 -L/usr/lib/i386-linux-gnu"
    native = build / "fdpp-native.ini"
    native.write_text("[binaries]\nc = 'gcc'\ncpp = 'g++'\n\n[built-in options]\nc_args = ['-m32']\ncpp_args = ['-m32']\nc_link_args = ['-m32', '-L/usr/lib/i386-linux-gnu']\ncpp_link_args = ['-m32', '-L/usr/lib/i386-linux-gnu']\n", encoding="utf-8")
    _run(["meson", "setup", str(fdpp_build), "--prefix", str(prefix), "--native-file", str(native)], fdpp_src, fdpp_env)
    _run(["ninja", "-C", str(fdpp_build), "install"], fdpp_src, fdpp_env)
    _run(["./autogen.sh"], dosemu_src, env)
    _run(["./default-configure", f"--prefix={prefix}", "--disable-dj64", "--disable-searpc"], dosemu_src, env)
    _run(["make", "-j2"], dosemu_src, env)
    _run(["make", "install"], dosemu_src, env)
    prefix.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest | {"status": "built", "prefix": str(prefix)}


def materialize_freedos(archive_root: str | Path, working_root: str | Path) -> dict:
    """Derive a disposable FreeDOS ISO/tree without modifying the M1 object."""
    verified = verify_preserved_input(archive_root, FREEDOS_M1)
    work = Path(working_root).expanduser().resolve()
    archive = Path(archive_root).expanduser().resolve()
    if archive == work or archive in work.parents:
        raise DOSProvisioningError("FreeDOS working state must be outside the archive")
    work.mkdir(parents=True, exist_ok=True)
    iso = work / "FD14LIVE.iso"
    if iso.is_file():
        digest = hashlib.sha256(iso.read_bytes()).hexdigest()
        return {"status": "already-present", "iso": str(iso), "sha256": digest,
                "source": verified["artifact_id"]}
    with zipfile.ZipFile(verified["path"]) as bundle:
        candidates = [item for item in bundle.infolist()
                      if not item.is_dir() and item.filename.lower().endswith(".iso")]
        if len(candidates) != 1:
            raise DOSProvisioningError("FreeDOS archive must contain exactly one ISO")
        item = candidates[0]
        if item.file_size > 512 * 1024 * 1024:
            raise DOSProvisioningError("FreeDOS ISO exceeds materialization limit")
        with bundle.open(item) as source, iso.open("xb") as target:
            shutil.copyfileobj(source, target)
    return {"status": "materialized", "iso": str(iso),
            "sha256": hashlib.sha256(iso.read_bytes()).hexdigest(),
            "source": verified["artifact_id"]}


def boot_marker_ready(output: bytes | str, marker: str = "UBB_DOS_READY") -> bool:
    """Require an explicit guest-produced marker; process liveness is insufficient."""
    if isinstance(output, bytes):
        output = output.decode("ascii", errors="replace")
    return marker in output.splitlines()


def qualification_evidence(check_id: str, state: str, *, reason: str, backend: dict | None = None,
                           profile: str = "freedos-bbs", evidence: dict | None = None) -> dict:
    if state not in ("PASS", "FAIL", "HUMAN_REQUIRED", "SKIP"):
        raise DOSConfigError("invalid qualification state")
    return {"check_id": check_id, "state": state,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "backend": backend or backend_evidence(), "profile": profile,
            "reason": reason, "evidence": evidence or {}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect product-neutral DOS runtime profiles")
    parser.add_argument("command", choices=("profiles", "validate-profile", "qualification", "runtime-info", "qualify", "provision-manifest", "provision"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("--archive-root")
    parser.add_argument("--runtime-root")
    parser.add_argument("--build-root")
    parser.add_argument("--install-dependencies", action="store_true")
    args = parser.parse_args(argv)
    profiles = default_profiles()
    if args.command == "profiles": print(json.dumps({k: v.guest_family for k, v in profiles.items()}, sort_keys=True))
    elif args.command == "validate-profile":
        if args.value not in profiles: raise SystemExit("unknown DOS profile")
        print("valid")
    elif args.command == "runtime-info": print(json.dumps(backend_evidence(), sort_keys=True))
    elif args.command == "qualify":
        evidence = [qualification_evidence("dosemu2-installed", "PASS" if backend_evidence()["available"] else "HUMAN_REQUIRED",
                                           reason="DOSEMU2 executable discovery; no installation performed"),
                    qualification_evidence("freedos-media", "HUMAN_REQUIRED",
                                           reason="No approved M1-preserved FreeDOS artifact is available")]
        print(json.dumps(evidence, indent=2, sort_keys=True))
    elif args.command == "provision-manifest":
        if not args.archive_root or not args.runtime_root:
            raise SystemExit("provision-manifest requires --archive-root and --runtime-root")
        try:
            print(json.dumps(provisioning_manifest(args.archive_root, args.runtime_root), indent=2, sort_keys=True))
        except DOSProvisioningError as exc:
            raise SystemExit(f"provisioning refused: {exc}")
    elif args.command == "provision":
        if not args.archive_root or not args.runtime_root or not args.build_root:
            raise SystemExit("provision requires --archive-root, --runtime-root, and --build-root")
        try:
            print(json.dumps(provision_runtime(args.archive_root, args.runtime_root, args.build_root,
                                               install_dependencies=args.install_dependencies), indent=2, sort_keys=True))
        except (DOSProvisioningError, subprocess.CalledProcessError) as exc:
            raise SystemExit(f"provisioning failed: {exc}")
    else: print("no production DOS service configured")


if __name__ == "__main__": main()
