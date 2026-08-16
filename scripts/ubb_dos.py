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
import threading
from dataclasses import dataclass, field
from pathlib import Path


class DOSConfigError(ValueError):
    pass


BACKENDS = ("dosemu2", "dosbox_x", "dosbox_staging", "qemu")
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
    parser.add_argument("command", choices=("profiles", "validate-profile", "qualification", "runtime-info", "qualify"))
    parser.add_argument("value", nargs="?")
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
    else: print("no production DOS service configured")


if __name__ == "__main__": main()
