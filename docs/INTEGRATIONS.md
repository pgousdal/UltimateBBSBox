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
```

The CLI intentionally does not become another lifecycle interface: start/stop remain M3 commands. Qualification callers supply observed runtime/readiness/route outcomes through the Python API; omitted live observations are `SKIP`, never fabricated passes.

## Mystic reference pipeline

The old configuration combined Mystic `1.12.A3` with an unavailable x64 tar filename. The authoritative upstream directory instead provides the selected stable Linux x64 release as `mys112a48_l64.rar` (Mystic `1.12.A48`). Acquisition records that versioned URL, original filename, all M1 hashes, conservative rights, and exact preserved bytes. Installation verifies SHA-256, invokes bounded argv-only `unrar` and Mystic `install auto` processes into a new digest-named release (never overwrite mode), separates live data, and atomically selects the release. `mis -cfg` and login/menu confirmation remain human-required.

The production chain resolves `mystic-main -> mystic-local -> mystic-linux -> native`. M3 owns lifecycle holds and readiness; M4 opens raw TCP after the lifecycle hold; Mystic presents and owns its login. Operators may choose `on_demand` or `always_on` in service lifecycle metadata without reinstalling.

## M7.2 and M7.3 compatibility

The contract deliberately does not prescribe a container format, host-side executable installer, native runtime, self-hosted TCP listener, or unattended configuration. ABBS and AmiExpress can therefore implement the same operations with preserved LHA/ADF media, assisted installation, an `fs_uae` runtime, and a configured serial/TCP bridge. M7.1 includes only a synthetic interface test for that shape; it contains no ABBS or AmiExpress product implementation or readiness claim.

M7.1 does not implement M6 network/core services, emulator product configuration, BBS publication, final menu UI, central identity, mass ingestion, or another BBS integration.
