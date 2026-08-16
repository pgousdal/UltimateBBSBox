"""Small canonical machine profiles shared by Amiga integrations."""
from __future__ import annotations

from dataclasses import dataclass
from .amiga import AmigaAsset
from .errors import IntegrationError


@dataclass(frozen=True)
class CanonicalAmigaProfile:
    id: str
    machine: str
    cpu: str
    chipset: str
    kickstart: str
    operating_system: str
    chip_memory_mb: int
    fast_memory_mb: int
    hard_disk_mb: int
    fs_uae_model: str
    assets: tuple[AmigaAsset, ...]


PROFILES = {
    "amiga-a500-k13": CanonicalAmigaProfile(
        "amiga-a500-k13", "Amiga 500", "68000", "OCS", "1.3", "Workbench/AmigaOS 1.3", 1, 2, 20,
        "A500", (AmigaAsset("kickstart", "licensed_private", "user-supplied Kickstart 1.3 ROM"),
         AmigaAsset("amigaos_base_hdf", "licensed_private", "user-supplied Workbench/AmigaOS 1.3 base image"))),
    "amiga-a1200-os31": CanonicalAmigaProfile(
        "amiga-a1200-os31", "Amiga 1200", "68020", "AGA", "3.1", "AmigaOS/Workbench 3.1", 2, 8, 100,
        "A1200", (AmigaAsset("kickstart", "licensed_private", "user-supplied Kickstart 3.1 ROM"),
         AmigaAsset("amigaos_base_hdf", "licensed_private", "user-supplied AmigaOS 3.1 base image"))),
}


def get_profile(profile_id: str) -> CanonicalAmigaProfile:
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise IntegrationError(f"unknown canonical Amiga profile: {profile_id}") from exc


def validate_profiles(supported: tuple[str, ...], default: str) -> None:
    if not supported:
        raise IntegrationError("an Amiga release must declare at least one supported profile")
    for item in supported:
        get_profile(item)
    if default not in supported:
        raise IntegrationError(f"default profile {default} is not in supported profiles")
