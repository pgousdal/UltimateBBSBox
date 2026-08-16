# Museum integrations

M7 integrations connect the independent M1–M5 layers without collapsing them. Catalog YAML says a service and integration exist. M1 says exact bytes are preserved. Product implementation describes installation and assisted work. M3/M5 control a runtime, M4 controls an authorized session, and qualification evidence—not process existence—determines readiness.

## Trusted contract and layout

The small `ubb_integrations` package defines the trusted registry, errors, result types, and these operations:

- `acquire`: use M1 quarantine and immutable publication;
- `verify_artifacts`: resolve and hash-check required M1 objects and rights;
- `install`: consume only verified objects or supported derived objects;
- `configure`: report automated or exact human work and evidence;
- `qualify`: record `PASS`, `FAIL`, `HUMAN_REQUIRED`, or `SKIP` per check.

Product knowledge lives under `integrations/<kind>/<product>/`; it is registered explicitly in repository code. Catalog YAML cannot load Python objects. The production catalog remains under `catalog/`, archive objects under the configured M1 root, runtime state under the supervisor state directory, and living product data under its installation's documented live path.

```text
integrations/bbs/mystic/
  integration.py       product installation and qualification behavior
  acquisition.json     source/version/rights decision
  README.md             operator and living-state instructions
```

`integrations/bbs/abbs/` and `integrations/bbs/amiexpress/` use the same contract while canonical profiles live in `ubb_integrations.profiles` and generic Amiga helpers live in `ubb_integrations.amiga`.

No integration installer may contain a direct canonical product downloader. The repository guard scans product integration implementation and the migrating Mystic role for `get_url` and command-line HTTP/FTP `curl`/`wget`; package-manager declarations that happen to install those utilities are permitted.

## Operator CLI

```text
python3 scripts/ubb-integration.py list
python3 scripts/ubb-integration.py --archive-root PATH acquire mystic-linux [--file FILE]
python3 scripts/ubb-integration.py --archive-root PATH verify mystic-linux
python3 scripts/ubb-integration.py --archive-root PATH --install-root PATH install mystic-linux
python3 scripts/ubb-integration.py --install-root PATH configure mystic-linux --evidence version_screen
python3 scripts/ubb-integration.py --archive-root PATH --install-root PATH qualify mystic-linux
python3 scripts/ubb-integration.py --install-root PATH status mystic-linux
python3 scripts/ubb-integration.py --archive-root PATH acquire abbs-amiga
python3 scripts/ubb-integration.py --archive-root PATH --install-root PATH install abbs-amiga \
  --asset kickstart=/private/kick.rom --asset amigaos_base_hdf=/private/base.hdf
```

The CLI intentionally does not become another lifecycle interface: start/stop remain M3 commands. Qualification callers supply observed runtime/readiness/route outcomes through the Python API; omitted live observations are `SKIP`, never fabricated passes.

## Mystic reference pipeline

The old configuration combined Mystic `1.12.A3` with an unavailable x64 tar filename. The authoritative upstream directory instead provides the selected stable Linux x64 release as `mys112a48_l64.rar` (Mystic `1.12.A48`). Acquisition records that versioned URL, original filename, all M1 hashes, conservative rights, and exact preserved bytes. Installation verifies SHA-256, invokes bounded argv-only `unrar` and Mystic `install auto` processes into a new digest-named release (never overwrite mode), separates live data, and atomically selects the release. `mis -cfg` and login/menu confirmation remain human-required.

The production chain resolves `mystic-main -> mystic-local -> mystic-linux -> native`. M3 owns lifecycle holds and readiness; M4 opens raw TCP after the lifecycle hold; Mystic presents and owns its login. Operators may choose `on_demand` or `always_on` in service lifecycle metadata without reinstalling.

## ABBS/Amiga pipeline and M7.3 compatibility

M7.2 selects authentic ABBS for All 3.2 (`ABBS320_999.lha`) as the first family release. Acquisition and verification use M1; a deterministic derived installation tree names the original as parent. Kickstart and AmigaOS remain user-supplied licensed-private assets. Assisted guest installation produces a qualified golden image, then a separate working image that convergence never overwrites. The M5 FS-UAE adapter consumes generated metadata, M3 uses its serial-listener readiness, and M4 routes raw TCP bytes to the emulated serial port. See [AMIGA-INTEGRATIONS.md](AMIGA-INTEGRATIONS.md) and the product README.

M7.3 selects AmiExpress 5.6.1 (`Amix561.lha`) from Aminet. Its rewrite is described as MIT in the package readme, but bundled historical Installer/documentation components have separate rights, so the mixed original is preservation-only. It declares the A1200/OS3.1 profile and reuses the same generic Amiga mechanics. See [AMIGA-PROFILES.md](AMIGA-PROFILES.md) and the product README.

M7.3a adds a second AmiExpress channel: a pinned GitHub development artifact identified by source commit `0f344713f30da7b6a4629643e32b50094cb2bd0b`, exact filename, and SHA-256. GitHub `dev-build` is queried only for discovery. M1 acquisition, candidate qualification, explicit promotion, and bounded rollback maintain immutable software and mutable BBS state separately. `always_on` is recommended for current deployment, but `on_demand` remains a service policy choice. Update checks never boot the Amiga or mutate installation state.

The contract deliberately does not prescribe a container format, host-side executable installer, native runtime, self-hosted TCP listener, or unattended configuration. AmiExpress can reuse prerequisite resolution, FS-UAE profile handling, golden/working images, serial bridging, and qualification helpers without product branching in M1–M5.

M7.2 does not implement AmiExpress, M6 network/core services, BBS publication, a final menu UI, central identity, or mass ingestion.
