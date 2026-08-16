"""Repository guard against preservation-bypassing product acquisition."""
from __future__ import annotations

import pathlib
import re

from .errors import IntegrationError

DIRECT_DOWNLOAD = re.compile(r"(?im)^\s*(?:-\s*)?(?:ansible\.builtin\.)?get_url\s*:|\b(?:wget|curl)\s+(?:-[^\s]+\s+)*(?:https?|ftp)://|\b(?:requests\.(?:get| Session)|urllib\.request\.urlopen)\s*\(|\bgit\s+clone\s+(?:https?|git@)")


def prohibited_downloads(root) -> list[str]:
    root = pathlib.Path(root)
    findings = []
    integration_roots = [root / "integrations", root / "roles" / "mystic_bbs"]
    for base in integration_roots:
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in (".py", ".yml", ".yaml", ".sh")):
            text = path.read_text(encoding="utf-8")
            if path.name in {"guard.py"} or "# ubb: metadata-only" in text or "# ubb: manual-example" in text: continue
            if "api.github.com" in text and "releases/tags" in text: continue
            if DIRECT_DOWNLOAD.search(text):
                findings.append(str(path.relative_to(root)))
    return findings


def assert_preservation_first(root) -> None:
    findings = prohibited_downloads(root)
    if findings:
        raise IntegrationError("direct product downloader found: " + ", ".join(findings))
