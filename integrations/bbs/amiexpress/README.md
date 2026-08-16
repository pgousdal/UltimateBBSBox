# AmiExpress/Amiga reference integration

M7.3 selects **AmiExpress BBS system redeveloped in E, release 5.6.1** (`Amix561.lha`). Aminet lists it under `comm/amiex` on 2024-03-02. The package readme identifies the original lineage as LightSpeed Technologies AmiExpress, credits Darren Coles for the rewrite, says the rewrite is open source, and points to the maintained source/wiki at `github.com/dmcoles/AmiExpress`.

The exact M1-preserved reference bytes are 1,161,960 bytes: SHA-256 `f49d051222a4a951597d241469dab24adb198c6849cdb111734fdd8c03571f4d`, SHA-1 `ee7986a0d89e15e63c066263fb49884af3f0791d`, MD5 `f4a8d5794bfebaeb359d85d78fca3ae6`. The archive was acquired from `https://aminet.net/comm/amiex/Amix561.lha` into a temporary M1 archive and is not committed.

The bundled readme grants MIT terms for the rewrite, but the same distribution includes an Escom AG licensed Installer and historical LightSpeed/Commodore documentation. UBB therefore classifies the mixed original `preservation_only`: local preservation and installation are allowed, while original redistribution, BBS publication, and unrestricted export remain denied pending component-level review. A user-supplied/licensed-private import is supported.

## Profiles and workflow

The release declares only `amiga-a1200-os31` as supported/default. The canonical profile is an A1200, 68020, AGA, 2 MiB Chip RAM, 8 MiB Fast RAM, Kickstart 3.1 and AmigaOS/Workbench 3.1, with a hard disk workspace. Kickstart and OS images are operator-supplied licensed-private files and never enter Git. Historical AmiExpress documentation describes Workbench and Kickstart 2.0+ requirements; the maintained 5.6.1 reference deliberately uses the repository’s canonical 3.1 profile rather than silently choosing newer OS media.

Acquire with M1, verify, and derive an immutable lineage-recorded installation tree. In Workbench, run the supplied installer, complete the base configuration, configure serial.device caller mode, remove private users/messages/logs, and approve a golden HDF. A separate working HDF holds mutable configuration, users, messages, conferences, filebase metadata, uploads, logs, statistics, queues, door state and generated files. Repeated convergence never overwrites it.

FS-UAE is selected through the M5 adapter using generated canonical profile metadata and a raw TCP serial listener on port 6403. M3 owns on-demand/always-on lifecycle, readiness and scheduled maintenance holds; M4 owns direct route authorization and raw terminal streams. AmiExpress owns destination login. Real Amiga boot, AmiExpress startup, readiness, login/menu, restart and living-state checks are `HUMAN_REQUIRED` without licensed assets; synthetic tests do not claim them.

The profile resolver, prerequisite handling, golden/working image model, FS-UAE configuration writer and serial path are the same generic components used by ABBS and are suitable for future AmiExpress releases.

## Stable and current tracks

The stable museum release remains `5.6.1` / `Amix561.lha` and is never overwritten. The current operational track is pinned to the GitHub `dev-build` release published as `amiExpress-nightly0f344713f30da7b6a4629643e32b50094cb2bd0b.lha`, source commit `0f344713f30da7b6a4629643e32b50094cb2bd0b`, SHA-256 `23459a56b086a28f9cad1da59691f0867c2e15f16bc37417723fd10207e42533`. The floating `dev-build` URL is discovery-only; M1 acquisition stores the exact asset before any install.

Use `python3 scripts/ubb-integration.py releases amiexpress-amiga` to inspect channels and `check-updates amiexpress-amiga` to query GitHub. Checks report `NO_CHANGE`, `NEW_BUILD_AVAILABLE`, `INVALID_UPSTREAM_METADATA`, or `DIGEST_MISMATCH`; they never install or promote. Promotion requires a per-artifact qualification record and explicit approval for `HUMAN_REQUIRED` checks:

```text
python3 scripts/ubb-integration.py --archive-root PATH acquire amiexpress-amiga --channel development
python3 scripts/ubb-integration.py --install-root PATH promote amiexpress-amiga --release amiexpress-dev-0f344713f30d --approve-human
python3 scripts/ubb-integration.py --install-root PATH deployment-status amiexpress-amiga
python3 scripts/ubb-integration.py --install-root PATH rollback amiexpress-amiga
```

Promotion maintains `current` and `previous` deployment pointers; it never copies or mutates preserved objects and never rolls back living users, messages, queues, or door state. The development integration recommends `always_on`, while the service manifest remains selectable as `on_demand`. Source snapshot preservation is intentionally deferred: the exact binary, commit identity, release metadata, and digest are preserved, but UBB does not claim reproducible rebuilding.
