"""Reusable, product-neutral helpers for assisted Amiga integrations."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import pathlib
import shutil

from .errors import InstallError


@dataclass(frozen=True)
class AmigaAsset:
    name: str
    classification: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class AmigaProfile:
    model: str
    cpu: str
    chipset: str
    chip_memory_mb: int
    fast_memory_mb: int
    serial_host: str
    serial_port: int


def resolve_assets(assets: dict[str, str | pathlib.Path], requirements: tuple[AmigaAsset, ...]) -> dict[str, pathlib.Path]:
    """Resolve private assets in-place; never copy them into the integration tree."""
    resolved: dict[str, pathlib.Path] = {}
    for requirement in requirements:
        value = assets.get(requirement.name)
        if value is None:
            if requirement.required:
                raise InstallError(f"missing required {requirement.name}: {requirement.description} ({requirement.classification})")
            continue
        path = pathlib.Path(value).expanduser().resolve()
        if not path.is_file() or path.is_symlink():
            raise InstallError(f"invalid {requirement.name} asset: expected a regular, non-symlink file")
        resolved[requirement.name] = path
    return resolved


def copy_working_image(golden: pathlib.Path, working: pathlib.Path) -> bool:
    """Create a runtime working image once; never converge over living state."""
    golden = golden.resolve(); working = working.resolve()
    if not golden.is_file() or golden.is_symlink():
        raise InstallError("qualified golden image is missing or unsafe")
    working.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    if working.exists():
        return False
    temporary = working.with_name(f".{working.name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(golden, temporary, follow_symlinks=False)
        os.chmod(temporary, 0o640)
        os.replace(temporary, working)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_fs_uae_config(path: pathlib.Path, profile: AmigaProfile, *, kickstart: pathlib.Path,
                        working_hdf: pathlib.Path) -> pathlib.Path:
    """Write deterministic FS-UAE metadata; FS-UAE execution remains in M5."""
    path = path.resolve(); path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    values = {
        "amiga_model": profile.model,
        "chip_memory": str(profile.chip_memory_mb * 1024),
        "fast_memory": str(profile.fast_memory_mb * 1024),
        "hard_drive_0": str(working_hdf.resolve()),
        "kickstart_file": str(kickstart.resolve()),
        "serial_port": f"tcp://{profile.serial_host}:{profile.serial_port}/wait",
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text("\n".join(f"{key} = {values[key]}" for key in sorted(values)) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640); os.replace(temporary, path)
    return path
