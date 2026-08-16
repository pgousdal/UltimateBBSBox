"""Dependency-light preservation archive for Ultimate BBS Box."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from typing import BinaryIO, Iterable

DEFAULT_ROOT = pathlib.Path("/srv/ultimate-bbs-box/archive")
DEFAULT_MAX_BYTES = 1024 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
HASH_RE = {"sha256": re.compile(r"^[0-9a-fA-F]{64}$"), "sha1": re.compile(r"^[0-9a-fA-F]{40}$"), "md5": re.compile(r"^[0-9a-fA-F]{32}$")}
ROLES = ("preservation_original", "source_code", "documentation", "install_source", "derived_install_media", "bbs_distribution", "reconstructed", "derived")
RIGHTS = ("unknown", "public_domain", "open_source", "freeware", "shareware", "freeware_redistributable", "shareware_redistributable", "commercial", "licensed", "licensed_private", "preservation_only", "restricted")


class ArchiveError(Exception):
    """Expected archive or user-input failure."""


class DuplicateArtifact(ArchiveError):
    pass


class VerificationError(ArchiveError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def validate_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise ArchiveError("artifact id must match ^[a-z0-9][a-z0-9._-]*$")
    return value


def safe_filename(value: str) -> str:
    value = value.replace("\\", "/").rsplit("/", 1)[-1].strip().replace("\x00", "")
    if value in ("", ".", "..") or pathlib.PurePath(value).name != value:
        raise ArchiveError("unsafe or empty original filename")
    cleaned = re.sub(r"[^A-Za-z0-9._+() -]", "_", value)
    if cleaned in ("", ".", ".."):
        raise ArchiveError("unsafe original filename")
    return cleaned[:255]


def sanitized_url(value: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ArchiveError("source URL scheme must be http or https")
    if not parsed.hostname:
        raise ArchiveError("source URL requires a host")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if parsed.port:
        host += f":{parsed.port}"
    clean = urllib.parse.urlunsplit((parsed.scheme.lower(), host, parsed.path, parsed.query, ""))
    return value, clean


def root_path(value: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(value).expanduser().resolve()


def init_archive(root: pathlib.Path) -> None:
    for relative in ("objects/sha256", "metadata", "quarantine", "derived", "exports", "state/locks"):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
        with contextlib.suppress(PermissionError):
            path.chmod(0o750)
    marker = root / "state" / "archive-v1.json"
    if not marker.exists():
        atomic_json(marker, {"format": "ubb-preservation-archive", "version": 1})


def require_archive(root: pathlib.Path) -> None:
    if not (root / "state" / "archive-v1.json").is_file():
        raise ArchiveError(f"not an initialized archive: {root}")


def fsync_dir(path: pathlib.Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: pathlib.Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def metadata_path(root: pathlib.Path, artifact_id: str) -> pathlib.Path:
    return root / "metadata" / f"{validate_id(artifact_id)}.json"


def load_metadata(root: pathlib.Path, artifact_id: str) -> dict:
    path = metadata_path(root, artifact_id)
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise ArchiveError(f"unknown artifact: {artifact_id}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"invalid metadata for {artifact_id}: {exc}") from exc
    validate_metadata(value)
    return value


def validate_metadata(value: dict) -> None:
    try:
        if value["kind"] != "artifact" or value["schema_version"] != 1:
            raise ValueError("unsupported kind or schema version")
        validate_id(value["id"])
        artifact = value["artifact"]
        if not HASH_RE["sha256"].fullmatch(artifact["sha256"]):
            raise ValueError("invalid sha256")
        if artifact["size"] < 0 or artifact["role"] not in ROLES:
            raise ValueError("invalid artifact fields")
        safe_filename(artifact["original_filename"])
        for name in ("sha1", "md5"):
            if name in artifact and not HASH_RE[name].fullmatch(artifact[name]):
                raise ValueError(f"invalid {name}")
        provenance = value["provenance"]
        if not isinstance(provenance["acquired_at"], str) or not provenance["acquired_at"] or not isinstance(provenance["source"], str) or not provenance["source"]:
            raise ValueError("invalid provenance")
        rights = value["rights"]
        if rights["status"] not in RIGHTS:
            raise ValueError("invalid rights status")
        for key in ("preserve_locally", "install_locally", "redistribute_original", "publish_to_bbs_filebase", "export_from_archive"):
            if not isinstance(rights[key], bool):
                raise ValueError(f"invalid rights.{key}")
        preservation = value["preservation"]
        if preservation["class"] not in ("original", "reconstructed", "derived", "private_preservation") or preservation["immutable"] is not True:
            raise ValueError("invalid preservation classification")
        lineage = preservation.get("lineage")
        if lineage:
            if not lineage.get("parents") or not lineage.get("action") or not lineage.get("derived_at"):
                raise ValueError("invalid lineage")
            for parent in lineage["parents"]:
                validate_id(parent["artifact_id"])
                if not HASH_RE["sha256"].fullmatch(parent["sha256"]):
                    raise ValueError("invalid lineage parent sha256")
    except (KeyError, TypeError, ValueError, ArchiveError) as exc:
        raise ArchiveError(f"invalid artifact metadata: {exc}") from exc


def object_path(root: pathlib.Path, digest: str) -> pathlib.Path:
    if not HASH_RE["sha256"].fullmatch(digest):
        raise ArchiveError("invalid object digest")
    return root / "objects" / "sha256" / digest[:2].lower() / digest.lower()


def hashes_for(handle: BinaryIO, destination: BinaryIO, max_bytes: int) -> tuple[dict[str, str], int]:
    hashes = {name: hashlib.new(name) for name in ("sha256", "sha1", "md5")}
    size = 0
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise ArchiveError(f"input exceeds maximum size of {max_bytes} bytes")
        destination.write(chunk)
        for digest in hashes.values():
            digest.update(chunk)
    return {name: digest.hexdigest() for name, digest in hashes.items()}, size


def check_expected(actual: dict[str, str], expected: dict[str, str]) -> None:
    for name, wanted in expected.items():
        if wanted and not HASH_RE[name].fullmatch(wanted):
            raise ArchiveError(f"invalid expected {name}")
        if wanted and actual[name].lower() != wanted.lower():
            raise ArchiveError(f"expected {name} {wanted.lower()}, got {actual[name]}")


def open_local(path: pathlib.Path) -> BinaryIO:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ArchiveError(f"cannot open import file: {exc}") from exc
    mode = os.fstat(fd).st_mode
    if not stat.S_ISREG(mode):
        os.close(fd)
        raise ArchiveError("import path must be a regular, non-symlink file")
    return os.fdopen(fd, "rb")


def source_predecessors(root: pathlib.Path, source_url: str, digest: str) -> list[str]:
    result = []
    for path in (root / "metadata").glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("provenance", {}).get("source_url") == source_url and value.get("artifact", {}).get("sha256") != digest:
            result.append(value.get("id", path.stem))
    return sorted(set(result))


def rights_document(args: argparse.Namespace) -> dict:
    return {
        "status": args.rights_status,
        "preserve_locally": True,
        "install_locally": bool(args.install_locally),
        "redistribute_original": bool(args.redistribute_original),
        "publish_to_bbs_filebase": bool(args.publish_to_bbs_filebase),
        "export_from_archive": not bool(args.no_owner_export),
        "evidence": list(args.rights_evidence or []),
    }


def preserve_stream(root: pathlib.Path, artifact_id: str, filename: str, stream: BinaryIO, provenance: dict,
                    args: argparse.Namespace, preservation_class: str = "original", role: str = "preservation_original",
                    lineage: dict | None = None, expected_size: int | None = None) -> dict:
    require_archive(root)
    validate_id(artifact_id)
    filename = safe_filename(filename)
    meta_path = metadata_path(root, artifact_id)
    if meta_path.exists():
        raise DuplicateArtifact(f"artifact id already exists: {artifact_id}")
    lock = root / "state" / "locks" / artifact_id
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise DuplicateArtifact(f"artifact id is currently being written: {artifact_id}") from exc
    os.close(lock_fd)
    quarantine = root / "quarantine" / f"{artifact_id}.{os.getpid()}.part"
    try:
        with quarantine.open("xb") as output:
            digests, size = hashes_for(stream, output, args.max_bytes)
            output.flush()
            os.fsync(output.fileno())
        if expected_size is not None and size != expected_size:
            raise ArchiveError(f"incomplete download: expected {expected_size} bytes, received {size}")
        check_expected(digests, {"sha256": args.expected_sha256, "sha1": args.expected_sha1, "md5": args.expected_md5})
        target = object_path(root, digests["sha256"])
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        if target.exists():
            if target.stat().st_size != size:
                raise ArchiveError("existing content-addressed object has an impossible size mismatch")
            quarantine.unlink()
        else:
            try:
                os.link(quarantine, target)
            except FileExistsError:
                pass
            target.chmod(0o444)
            fsync_dir(target.parent)
            quarantine.unlink()
        prior = source_predecessors(root, provenance.get("source_url", ""), digests["sha256"]) if provenance.get("source_url") else []
        provenance["source_changed"] = bool(prior)
        if prior:
            provenance["previous_artifacts_from_source"] = prior
        artifact = {"role": role, "original_filename": filename, **digests, "size": size,
                    "media_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"}
        for source, target_key in ((args.software_family, "software_family"), (args.version, "version"), (args.platform, "platform")):
            if source:
                artifact[target_key] = source
        if lineage:
            artifact["derived_from"] = [p["artifact_id"] for p in lineage["parents"]]
        document = {"kind": "artifact", "schema_version": 1, "id": artifact_id, "artifact": artifact,
                    "provenance": provenance, "rights": rights_document(args),
                    "preservation": {"class": preservation_class, "immutable": True, "status": "READY"}}
        if lineage:
            document["preservation"]["lineage"] = lineage
        validate_metadata(document)
        atomic_json(meta_path, document)
        return document
    finally:
        with contextlib.suppress(FileNotFoundError):
            quarantine.unlink()
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()


def import_artifact(args: argparse.Namespace) -> dict:
    path = pathlib.Path(args.file)
    raw_url, clean_url = sanitized_url(args.source_url)
    del raw_url
    with open_local(path) as stream:
        return preserve_stream(root_path(args.root), args.artifact_id, args.original_filename or path.name, stream,
                               {"acquired_at": now(), "source": args.source_name, "source_url": clean_url,
                                "retrieval_method": "local_file", **({"notes": args.notes} if args.notes else {})}, args)


def response_filename(response, url: str) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename\s*=\s*(?:\"([^\"]+)\"|([^;]+))", disposition, re.I)
    candidate = (match.group(1) or match.group(2)).strip() if match else pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).name
    return safe_filename(candidate or "download.bin")


def acquire_http(args: argparse.Namespace) -> dict:
    request_url, clean_url = sanitized_url(args.source_url)
    request = urllib.request.Request(request_url, headers={"User-Agent": "UltimateBBSBox-Archive/1"})
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            length = response.headers.get("Content-Length")
            expected_size = int(length) if length else None
            if expected_size is not None and expected_size > args.max_bytes:
                raise ArchiveError(f"download exceeds maximum size of {args.max_bytes} bytes")
            filename = args.original_filename or response_filename(response, clean_url)
            return preserve_stream(root_path(args.root), args.artifact_id, filename, response,
                                   {"acquired_at": now(), "source": args.source_name, "source_url": clean_url,
                                    "retrieval_method": urllib.parse.urlsplit(clean_url).scheme,
                                    **({"notes": args.notes} if args.notes else {})}, args, expected_size=expected_size)
    except ArchiveError:
        raise
    except Exception as exc:
        raise ArchiveError(f"acquisition failed: {exc}") from exc


def derive(args: argparse.Namespace) -> dict:
    root = root_path(args.root)
    parents = [load_metadata(root, item) for item in args.parent]
    lineage = {"parents": [{"artifact_id": p["id"], "sha256": p["artifact"]["sha256"]} for p in parents],
               "action": args.action, "derived_at": now()}
    if args.tool:
        lineage["tool"] = args.tool
    if args.notes:
        lineage["notes"] = args.notes
    with open_local(pathlib.Path(args.file)) as stream:
        return preserve_stream(root, args.artifact_id, args.original_filename or pathlib.Path(args.file).name, stream,
                               {"acquired_at": now(), "source": "derived in archive", "retrieval_method": "derived",
                                **({"notes": args.notes} if args.notes else {})}, args, "reconstructed" if args.role == "reconstructed" else "derived", args.role, lineage)


def verify_one(root: pathlib.Path, artifact_id: str) -> dict:
    metadata = load_metadata(root, artifact_id)
    path = object_path(root, metadata["artifact"]["sha256"])
    try:
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk); size += len(chunk)
    except OSError as exc:
        raise VerificationError(f"{artifact_id}: object missing or unreadable: {exc}") from exc
    if digest.hexdigest() != metadata["artifact"]["sha256"] or size != metadata["artifact"]["size"]:
        raise VerificationError(f"{artifact_id}: object checksum or size mismatch")
    return metadata


def write_text(path: pathlib.Path, value: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush(); os.fsync(handle.fileno())


def build_export(root: pathlib.Path, artifact_id: str, output: pathlib.Path, publication: bool, redistribution: bool = False) -> pathlib.Path:
    metadata = verify_one(root, artifact_id)
    rights = metadata["rights"]
    if publication and not rights["publish_to_bbs_filebase"]:
        raise ArchiveError("publication denied: rights.publish_to_bbs_filebase is false")
    if not publication and not rights["export_from_archive"]:
        raise ArchiveError("export denied: rights.export_from_archive is false")
    if redistribution and not rights["redistribute_original"]:
        raise ArchiveError("redistribution export denied: rights.redistribute_original is false")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o750)
    final = output / artifact_id
    if final.exists():
        raise ArchiveError(f"output already exists: {final}")
    temporary = pathlib.Path(tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=output))
    try:
        source = object_path(root, metadata["artifact"]["sha256"])
        name = safe_filename(metadata["artifact"]["original_filename"])
        if publication:
            shutil.copyfile(source, temporary / name, follow_symlinks=False)
            atomic_json(temporary / f"{name}.json", metadata)
            description = metadata["provenance"].get("notes") or f"{artifact_id}: preserved {name}"
            write_text(temporary / "FILE_ID.DIZ.generated", description.strip() + "\n")
            with contextlib.suppress(zipfile.BadZipFile, OSError, UnicodeError):
                with zipfile.ZipFile(source) as archive:
                    matches = [i for i in archive.infolist() if pathlib.PurePosixPath(i.filename).name.upper() == "FILE_ID.DIZ" and not i.is_dir() and i.file_size <= 65536]
                    if matches:
                        with archive.open(matches[0]) as item, (temporary / "FILE_ID.DIZ").open("xb") as target:
                            target.write(item.read(65537))
        else:
            artifacts = temporary / "artifacts"; artifacts.mkdir()
            shutil.copyfile(source, artifacts / name, follow_symlinks=False)
            atomic_json(temporary / "metadata.json", metadata)
            write_text(temporary / "checksums.sha256", f"{metadata['artifact']['sha256']}  artifacts/{name}\n")
            write_text(temporary / "RIGHTS.txt", "Rights status: " + rights["status"] + "\n" + "\n".join(f"{key}: {str(value).lower()}" for key, value in rights.items() if isinstance(value, bool)) + "\n")
            lineage = metadata["preservation"].get("lineage")
            text = f"Ultimate BBS Box preservation export\n\nArtifact: {artifact_id}\nOriginal filename: {name}\nAcquired: {metadata['provenance']['acquired_at']}\nSource: {metadata['provenance']['source']}\nSHA-256: {metadata['artifact']['sha256']}\n"
            if lineage:
                text += "\nDerived artifact lineage:\n" + "\n".join(f"- {p['artifact_id']} ({p['sha256']})" for p in lineage["parents"]) + f"\nAction: {lineage['action']}\n"
            write_text(temporary / "README.txt", text)
        os.replace(temporary, final); fsync_dir(output)
        return final
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=str(DEFAULT_ROOT))


def add_ingest(parser: argparse.ArgumentParser, source_required: bool = True) -> None:
    add_common(parser)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--source-url", required=source_required)
    parser.add_argument("--source-name", required=source_required)
    parser.add_argument("--original-filename")
    parser.add_argument("--expected-sha256"); parser.add_argument("--expected-sha1"); parser.add_argument("--expected-md5")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--rights-status", choices=RIGHTS, default="unknown")
    parser.add_argument("--install-locally", action="store_true")
    parser.add_argument("--redistribute-original", action="store_true")
    parser.add_argument("--publish-to-bbs-filebase", action="store_true")
    parser.add_argument("--no-owner-export", action="store_true")
    parser.add_argument("--rights-evidence", action="append")
    parser.add_argument("--software-family"); parser.add_argument("--version"); parser.add_argument("--platform"); parser.add_argument("--notes")


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(description="Ultimate BBS Box preservation archive")
    sub = main.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); add_common(init)
    acquire = sub.add_parser("acquire"); add_ingest(acquire); acquire.add_argument("--file"); acquire.add_argument("--timeout", type=float, default=30)
    imp = sub.add_parser("import-file"); add_ingest(imp); imp.add_argument("--file", required=True)
    show = sub.add_parser("show"); add_common(show); show.add_argument("artifact_id")
    verify = sub.add_parser("verify"); add_common(verify); verify.add_argument("artifact_id")
    verify_all = sub.add_parser("verify-all"); add_common(verify_all)
    derived = sub.add_parser("derive"); add_ingest(derived, False); derived.add_argument("--parent", action="append", required=True); derived.add_argument("--file", required=True); derived.add_argument("--role", choices=ROLES, required=True); derived.add_argument("--action", required=True); derived.add_argument("--tool")
    export = sub.add_parser("export"); add_common(export); export.add_argument("artifact_id"); export.add_argument("--output", required=True); export.add_argument("--for-redistribution", action="store_true")
    publication = sub.add_parser("publication-export"); add_common(publication); publication.add_argument("artifact_id"); publication.add_argument("--output", required=True)
    return main


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = root_path(args.root)
        if args.command == "init": init_archive(root); print(f"initialized {root}")
        elif args.command == "import-file": print(json.dumps(import_artifact(args), indent=2, sort_keys=True))
        elif args.command == "acquire":
            if args.file: print(json.dumps(import_artifact(args), indent=2, sort_keys=True))
            else: print(json.dumps(acquire_http(args), indent=2, sort_keys=True))
        elif args.command == "show": print(json.dumps(load_metadata(root, args.artifact_id), indent=2, sort_keys=True))
        elif args.command == "verify": verify_one(root, args.artifact_id); print(f"OK {args.artifact_id}")
        elif args.command == "verify-all":
            failures = []
            for path in sorted((root / "metadata").glob("*.json")):
                try: verify_one(root, path.stem); print(f"OK {path.stem}")
                except ArchiveError as exc: failures.append(str(exc)); print(f"FAIL {exc}", file=sys.stderr)
            if failures: return 1
        elif args.command == "derive": print(json.dumps(derive(args), indent=2, sort_keys=True))
        elif args.command == "export": print(build_export(root, args.artifact_id, pathlib.Path(args.output), False, args.for_redistribution))
        elif args.command == "publication-export": print(build_export(root, args.artifact_id, pathlib.Path(args.output), True))
        return 0
    except (ArchiveError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
