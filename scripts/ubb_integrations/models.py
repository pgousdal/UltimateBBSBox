"""Small, runtime-neutral integration contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class QualificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    SKIP = "SKIP"


@dataclass(frozen=True)
class QualificationResult:
    check: str
    status: QualificationStatus
    detail: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "status": self.status.value,
                "detail": self.detail, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class InstallResult:
    artifact_id: str
    artifact_sha256: str
    release_path: str
    live_path: str
    changed: bool
    manual_evidence_required: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_id": self.artifact_id, "artifact_sha256": self.artifact_sha256,
                "release_path": self.release_path, "live_path": self.live_path,
                "changed": self.changed,
                "manual_evidence_required": list(self.manual_evidence_required)}


class MuseumIntegration(Protocol):
    id: str
    runtime: str
    automation_level: str

    def acquire(self, archive_root, *, local_file=None, source_url=None, artifact_id=None): ...
    def verify_artifacts(self, archive_root, artifact_id): ...
    def install(self, archive_root, artifact_id, install_root): ...
    def configure(self, install_root, evidence=()): ...
    def qualify(self, archive_root, artifact_id, install_root, **context): ...

