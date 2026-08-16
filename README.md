# Ultimate BBS Box

Ultimate BBS Box is infrastructure-as-code for a BBS-centric preservation and online-services appliance. It began as a Debian/Mystic deployment for an industrial multi-serial mini-PC and is being generalized into a modular system capable of preserving and running historical BBSes, doors, MUDs/online worlds, interactive fiction, remote shells, and supporting communications services.

**M7.3 adds the preservation-first AmiExpress/Amiga reference integration.** M0–M5, M7.1 and M7.2 remain intact, M6 remains the reserved network/core-services milestone, and museum integrations are added and qualified one at a time.

## Core rules

- Callers do **not** need a UBB login. Authentication normally happens after a destination is selected.
- Services can be `on_demand` or `always_on` and may wake on schedules for network-message/file exchange.
- Services can run locally, in an emulator/VM, over serial/TCP/SSH, or on another UBB-compatible host.
- Main-menu exposure is policy. A door, MUD, shell, IRC service, etc. can be direct, BBS-only, both, or hidden.
- Network-acquired software is preserved immutably with provenance and checksums **before** installation.
- Redistribution to Mystic/ABBS filebases is deny-by-default and requires explicit rights metadata.
- Runnable integrations are added incrementally; manual/assisted setup is a supported first-class state.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/MILESTONES.md](docs/MILESTONES.md).

The admin plane's generic backup API preserves integration living state (users,
messages, configuration and declared file data) separately from immutable M1
software. Backups are staged, verified and exposed through the authenticated
admin action service; see [docs/BACKUP.md](docs/BACKUP.md). The dashboard/systemd
deployment uses an unprivileged service account and keeps the preservation
archive read-only.

## Preservation archive

The dependency-light archive CLI stores immutable, content-addressed objects, records provenance and conservative rights decisions, verifies objects, records derived lineage, and creates museum or rights-gated publication exports. The default production root is `/srv/ultimate-bbs-box/archive`; always select a development root explicitly when working without root privileges.

```bash
python3 scripts/ubb-archive.py init --root /tmp/ubb-archive
python3 scripts/ubb-archive.py import-file --root /tmp/ubb-archive \
  --artifact-id example --file ./software.zip \
  --source-url https://example.invalid/software.zip --source-name "Example archive"
python3 scripts/ubb-archive.py verify-all --root /tmp/ubb-archive
python3 scripts/ubb-archive.py export --root /tmp/ubb-archive example --output /tmp/exports
```

HTTP/HTTPS `acquire` follows quarantine → identify/hash → immutable preservation. Both acquisition modes deny redistribution and BBS publication unless their explicit flags are supplied with documented rights evidence. See [docs/PRESERVATION.md](docs/PRESERVATION.md).

## Service registry

Production YAML manifests live separately from educational examples in `catalog/services/`, `catalog/endpoints/`, and `catalog/integrations/`. The read-only registry validates and indexes them, resolves declaration chains, and queries service type, endpoint type, runtime, and exposure metadata without connecting to or controlling anything.

```bash
python3 scripts/ubb-registry.py validate
python3 scripts/ubb-registry.py list --main-menu
python3 scripts/ubb-registry.py list --via-bbs mystic-main
python3 scripts/ubb-registry.py --json resolve unix-v7-shell
```

See [docs/REGISTRY.md](docs/REGISTRY.md) for the model and full command set.

## Lifecycle supervisor

The M3 supervisor turns lifecycle declarations into explicit, persisted state transitions. It tracks independent always-on, administrative, maintenance, recovery, and session holds; enforces readiness, bounded restart, sharing, and idle rules; and runs interval or daily maintenance orchestration through an injected generic driver.

```bash
python3 scripts/ubb-supervisor.py --state-dir /tmp/ubb-state status
python3 scripts/ubb-supervisor.py --state-dir /tmp/ubb-state reconcile
python3 scripts/ubb-supervisor.py --state-dir /tmp/ubb-state tick
python3 scripts/ubb-supervisor.py --state-dir /tmp/ubb-state --json status mystic-main
```

M5 supplies the default adapter-backed runtime driver. Services without runnable `runtime_config` fail closed rather than pretending they can be controlled; M7.1 now gives Mystic an explicit native declaration. See [docs/SUPERVISOR.md](docs/SUPERVISOR.md).

M7.1 gives Mystic a production `native` runtime configuration and a preservation-first install workflow. A clean install can no longer fetch Mystic directly from Ansible. See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) and [integrations/bbs/mystic/README.md](integrations/bbs/mystic/README.md).

M7.2 applies that contract to ABBS for All 3.2. It preserves the authentic LHA before deriving an install tree, requires operator-supplied licensed Kickstart/AmigaOS assets, separates golden and mutable HDFs, and routes a raw FS-UAE serial bridge through M3/M4. See [integrations/bbs/abbs/README.md](integrations/bbs/abbs/README.md) and [docs/AMIGA-INTEGRATIONS.md](docs/AMIGA-INTEGRATIONS.md).

M7.3 adds AmiExpress 5.6.1 from Aminet and canonical `amiga-a500-k13`/`amiga-a1200-os31` profiles. AmiExpress uses only the evidence-supported A1200/OS3.1 profile and the same generic Amiga helpers as ABBS. See [integrations/bbs/amiexpress/README.md](integrations/bbs/amiexpress/README.md) and [docs/AMIGA-PROFILES.md](docs/AMIGA-PROFILES.md).

M7.3a adds the pinned AmiExpress GitHub current track. The rolling `dev-build` release is discovery metadata only; exact commit, filename, digest, and preserved M1 artifact identity are required. Updates are checked explicitly, promoted only after qualification and operator approval, and rolled back through software pointers without reverting living BBS data.

```bash
python3 scripts/ubb-integration.py list
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive acquire mystic-linux
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive --install-root /opt/mystic install mystic-linux
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive --install-root /opt/mystic qualify mystic-linux
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive acquire abbs-amiga
```

## Session router

M4 authorizes direct and via-service paths, anchors via routes to real active origin sessions, acquires and releases M3 session holds, carries extensible terminal metadata, and exposes raw bidirectional stream handles. TCP is the only built-in network connector; other endpoint transports fail explicitly unless a connector is injected.

```bash
python3 scripts/ubb-router.py services --direct
python3 scripts/ubb-router.py authorize mystic-main
python3 scripts/ubb-router.py authorize unix-v7-shell --via mystic-main
python3 scripts/ubb-router.py --json services --direct
```

The authorization CLI inspects declared route policy; actual via-service opens additionally require an active origin session. UBB does not authenticate destination users or log terminal content. See [docs/ROUTER.md](docs/ROUTER.md).

## Runtime adapters

M5 maps `integration.runtime` to built-in adapters for native processes, FS-UAE, VICE, QEMU, and SIMH. Runtime metadata supplies explicit executable/argv paths, environment, readiness, and PTY/stdio/TCP stream configuration; adapters contain no BBS product rules.

```bash
python3 scripts/ubb-runtime.py list-adapters
python3 scripts/ubb-runtime.py --json list-adapters
python3 scripts/ubb-runtime.py validate SERVICE_ID
```

Lifecycle start/stop remains in `ubb-supervisor.py`. DOS, MAME, Hatari, and remote-supervisor RPC are registered as explicitly deferred rather than pretending to work. See [docs/RUNTIMES.md](docs/RUNTIMES.md).

## Contracts

```
schemas/
  artifact-v1.schema.json     preservation object + provenance + rights
  endpoint-v1.schema.json     local/remote connection target
  service-v1.schema.json      BBS/door/MUD/IF/shell/etc + exposure/lifecycle
  integration-v1.schema.json  install/qualification recipe
catalog/examples/             executable example manifests
catalog/{services,endpoints,integrations}/  production registry source
scripts/ubb-schema.py         manifest validator
scripts/ubb-archive.py        preservation archive CLI
scripts/ubb-registry.py       registry inspection CLI
scripts/ubb-supervisor.py     lifecycle supervisor CLI
scripts/ubb-router.py         exposure policy inspection CLI
scripts/ubb-runtime.py        runtime adapter diagnostics
scripts/ubb-integration.py    museum integration workflow
```

Validate everything with:

```bash
python3 -m pip install -r requirements-dev.txt
make check
```

`make check` validates catalog manifests, runs unit tests, and runs Ansible syntax checks when `ansible-playbook` is available.

## Existing Ansible layout

```
inventory/           hosts + group_vars
playbooks/
  bootstrap.yml      one-time managed-admin bootstrap
  site.yml           current convergence playbook
roles/
  common/            Debian base/hardening
  serial_ports/      stable serial names + RS485 setup
  mystic_bbs/        Mystic host convergence and legacy migration service
  network_gateway/   firewall/fail2ban
  backup/            current Mystic-specific backup implementation
  monitoring/        node_exporter
files/mystic_doors/   current Mystic .mpy door placeholders
```

Existing `/opt/mystic/mis` deployments remain recognized. On a clean host the Mystic role prepares host prerequisites, then deliberately pauses until the M7.1 CLI has installed a verified M1 artifact; its systemd service is opt-in for migration because M3 is the intended lifecycle owner. Backup/state modernization and actual BBS publication remain later work.

## Current deployment

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/bootstrap.yml -u root -k
ansible-playbook playbooks/site.yml
```

Mystic still requires assisted first-time `mis -cfg` configuration. Version-screen and configured-message-base evidence are explicit requirements; login/menu qualification remains `HUMAN_REQUIRED` until observed. Public download availability is not treated as redistribution permission.

## Secrets

Do not commit credentials, BBS registration keys, FTN passwords, SMTP secrets, or SSH private keys. They must remain outside preservation objects and catalog manifests and be injected through a later secrets-provider contract.

M7.4 hardens the four Tier-1 reference tracks with common qualification
evidence, fail-closed backup/restore, crash/restart and route-cleanup checks,
and explicit readiness reporting. Run
`python3 scripts/ubb-integration.py readiness mystic-linux` (or an Amiga
integration) to distinguish PASS from human-required observations. Licensed-
private Amiga assets and real BBS login/menu observations are never fabricated
or committed.

M7.4a adds authentic Aminet ABBS v1.1 (`abbs1_1.lha`) as a second release of
the existing ABBS family and aligns Mystic/ABBS deployment recommendations
with the appliance's normal `always_on` policy. Recommendations remain
metadata; operators can select `on_demand` without reinstalling.

M8.1 adds the local read-only Admin Observatory. `python3 scripts/ubb-admin.py
status` provides a concise overview; `--json services`, `activity`, `alerts`,
`readiness`, `artifacts`, and `backups` expose the same deterministic read
model for operators and future dashboards. It performs no lifecycle, backup,
promotion, or network-admin actions.

M8.2 adds the dependency-free read-only web view:
`python3 scripts/ubb-dashboard.py --bind 127.0.0.1 --port 8088`. It uses the
same observatory model and versioned GET-only `/api/v1/` endpoints, with no
database, write actions, authentication system, or public bind by default.
