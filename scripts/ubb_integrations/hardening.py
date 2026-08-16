"""Product-neutral Tier-1 evidence, readiness, and live-state recovery helpers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import shutil


class EvidenceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Evidence:
    integration: str
    release: str
    check: str
    status: EvidenceStatus
    detail: str
    artifact_sha256: str | None = None
    profile: str | None = None
    evidence_type: str = "synthetic"
    reference: str | None = None
    human_note: str | None = None

    def to_dict(self):
        value = {"integration": self.integration, "release": self.release, "check": self.check,
                 "status": self.status.value, "detail": self.detail, "evidence_type": self.evidence_type}
        for key, item in (("artifact_sha256", self.artifact_sha256), ("profile", self.profile),
                          ("evidence_reference", self.reference), ("human_note", self.human_note)):
            if item is not None:
                value[key] = item
        return value


def readiness_summary(evidence: list[dict] | tuple[dict, ...], *, integration: str, release: str):
    """Aggregate evidence without equating a passing test suite with readiness."""
    statuses = [item.get("status") for item in evidence]
    if not statuses:
        status = "BLOCKED"
    elif "FAIL" in statuses or "BLOCKED" in statuses:
        status = "NOT_READY"
    elif "HUMAN_REQUIRED" in statuses:
        status = "READY_WITH_HUMAN_REQUIREMENTS"
    elif "PASS" in statuses:
        status = "READY"
    else:
        status = "NOT_READY"
    return {"integration": integration, "release": release, "readiness": status,
            "checks": len(evidence), "human_required": statuses.count("HUMAN_REQUIRED"),
            "failed": statuses.count("FAIL") + statuses.count("BLOCKED"), "evidence": list(evidence)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_immutable(path: Path, expected_sha256: str) -> None:
    if not path.is_file() or sha256(path) != expected_sha256:
        raise ValueError(f"preserved object invariant failed: {path}")


def backup_live_state(live_root: Path, destination: Path, *, integration: str, release: str,
                      exclude_names=("software", "objects")) -> dict:
    """Copy only mutable state and emit a verifiable manifest; never copy preserved objects."""
    live_root = live_root.resolve(); destination = destination.resolve()
    if not live_root.is_dir():
        raise ValueError(f"live state directory is missing: {live_root}")
    destination.mkdir(parents=True, exist_ok=False, mode=0o750)
    files = []
    for source in sorted(live_root.rglob("*")):
        if source.is_symlink():
            raise ValueError(f"symlinks are not valid live-state backup inputs: {source}")
        if not source.is_file() or any(part in exclude_names for part in source.relative_to(live_root).parts):
            continue
        relative = source.relative_to(live_root)
        target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        shutil.copyfile(source, target, follow_symlinks=False)
        files.append({"path": relative.as_posix(), "size": source.stat().st_size, "sha256": sha256(source)})
    manifest = {"format": "ubb-live-backup-v1", "integration": integration, "release": release,
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "source": str(live_root), "files": files}
    (destination / "backup-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def restore_live_state(backup_root: Path, target_root: Path, *, verified_artifact: bool) -> dict:
    """Restore mutable state only after the caller verifies the software artifact."""
    if not verified_artifact:
        raise ValueError("restore requires a verified preservation artifact")
    backup_root = backup_root.resolve(); target_root = target_root.resolve()
    manifest_path = backup_root / "backup-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("backup manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); restored = []
    for item in manifest.get("files", []):
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe backup path: {item['path']}")
        source = backup_root / relative
        if not source.is_file() or sha256(source) != item["sha256"]:
            raise ValueError(f"backup checksum failed: {item['path']}")
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750); shutil.copyfile(source, target, follow_symlinks=False); restored.append(item["path"])
    return {"integration": manifest.get("integration"), "release": manifest.get("release"), "restored": restored}


def golden_working_invariant(golden: Path, working: Path, golden_sha256: str) -> None:
    assert_immutable(golden, golden_sha256)
    if golden.resolve() == working.resolve():
        raise ValueError("golden and working images must be separate")
