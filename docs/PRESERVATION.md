# Preservation archive

M1 is the product-neutral preservation layer for future BBS software, doors, MUDs, interactive fiction, emulator media, utilities, documentation, and source. It implements:

```
acquire -> quarantine -> identify/hash -> immutable original
        -> classify rights -> record derived artifacts -> export/stage later
```

It does not install software, update Mystic or ABBS filebases, provide a service registry, run lifecycle supervision, extract packages, convert disk images, or mass-import a catalog.

## Layout and durability

The default root is `/srv/ultimate-bbs-box/archive`; `--root` makes tests and unprivileged development independent. `init` creates non-world-writable directories:

```
objects/sha256/ab/<full-sha256>  immutable canonical bytes
metadata/<artifact-id>.json     canonical catalog/provenance record
quarantine/                     incomplete acquisition streams
derived/                        reserved workspace for future derivation tools
exports/                        archive-managed export area
state/archive-v1.json           archive format marker
state/locks/                    per-artifact transaction locks
```

Objects are addressed by lowercase SHA-256 and made mode `0444`. Correctness does not depend on mode alone: archive code only creates canonical paths with an exclusive hard link and never opens them for writing. File and directory fsync plus atomic rename are used for durable metadata publication. Identical content reuses an object. A URL returning new bytes creates another object and metadata records earlier artifact IDs from that source; it never replaces history.

Back up `objects/` and `metadata/` together with a snapshot-capable or content-verifying tool. Preserve permissions, verify after restore with `verify-all`, keep at least one geographically separate copy, and test restores. `quarantine/`, locks, and generated exports are not authoritative backups.

## Acquisition and provenance

`acquire` accepts HTTP or HTTPS, or `--file` for a file already downloaded. `import-file` is the explicit local-file spelling. HTTP streams always enter quarantine, are bounded by `--max-bytes` (1 GiB default), receive SHA-256/SHA-1/MD5 hashes, and are checked against optional `--expected-sha256`, `--expected-sha1`, and `--expected-md5`. Only a complete, matching stream is preserved. Failed and interrupted streams leave no artifact metadata and quarantine is cleaned.

Metadata records acquisition time, sanitized source URL, named source/archive, retrieval method, filename, detected media type, byte size, hashes, notes, and optional software family, version, and platform. URL userinfo and fragments are removed before persistence. Public hosting is provenance, never rights evidence.

## Rights

New acquisitions use `unknown`, allow local preservation and owner export, and deny local installation, original redistribution, and BBS publication. These decisions are independent:

- `preserve_locally`
- `install_locally`
- `redistribute_original`
- `publish_to_bbs_filebase`
- `export_from_archive`

The CLI permission flags make decisions explicit; pair them with `--rights-evidence`. `export --for-redistribution` requires `redistribute_original`. Ordinary museum export is an owner/local operation and requires `export_from_archive`. Publication staging requires `publish_to_bbs_filebase`. Archive.org, Aminet, FTP archives, GitHub, and other public sources do not imply permission.

## Derived lineage and verification

`derive` preserves supplied output as a separate immutable object. It records each parent artifact ID and SHA-256, an action, time, and optional tool/version and notes. A `reconstructed` role is classified as reconstructed, never original. M1 deliberately does not perform transformations itself.

`verify ID` validates metadata then re-hashes the object and checks its size. `verify-all` checks every metadata record and returns failure for missing, unreadable, or changed objects.

## Exports and publication staging

Museum export creates `<output>/<artifact-id>/` containing the original filename below `artifacts/`, canonical `metadata.json`, `checksums.sha256`, `RIGHTS.txt`, and a plain-language `README.txt` with lineage for derived objects. It is understandable without UBB tooling.

Publication staging creates an exact copy with its original filename, a JSON description sidecar, and `FILE_ID.DIZ.generated`. It never repacks or modifies preserved bytes. For ZIP packages only, an existing case-insensitive `FILE_ID.DIZ` entry of at most 64 KiB is safely copied alongside the generated sidecar; archive paths are not extracted. A later publisher may consume this directory, but M1 never writes into live BBS file areas.

## Threat assumptions

Artifact IDs are restricted to lowercase safe components, filenames are reduced to a basename and sanitized, URL schemes are restricted, credentials/fragments are stripped, downloads are bounded, local imports must be regular non-symlink files, and exports are created beneath a resolved caller-selected output directory. No shell or external process is invoked. Existing output bundles are not overwritten.

The archive operator is trusted to choose a safe root, protect the host, provide truthful rights evidence, and keep secrets and commercial registration keys out of URLs, notes, metadata, and artifacts. M1 does not provide malware scanning, hostile archive extraction, encryption, multi-user authorization, filesystem immutability flags, or protection against an administrator deliberately changing files.

## CLI summary

Run `python3 scripts/ubb-archive.py COMMAND --help`. Commands are `init`, `acquire`, `import-file`, `show`, `verify`, `verify-all`, `derive`, `export`, and `publication-export`. Diagnostics go to stderr and expected archive/input failures exit with status 2.
