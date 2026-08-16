# Ultimate BBS Box

Ultimate BBS Box is infrastructure-as-code for a BBS-centric preservation and online-services appliance. It began as a Debian/Mystic deployment for an industrial multi-serial mini-PC and is being generalized into a modular system capable of preserving and running historical BBSes, doors, MUDs/online worlds, interactive fiction, remote shells, and supporting communications services.

**M5 adds product-neutral runtime adapters.** The existing Mystic-on-metal Ansible integration and M0–M4 layers are retained, but Mystic is not the architecture: product-specific integrations are added and qualified one at a time.

## Core rules

- Callers do **not** need a UBB login. Authentication normally happens after a destination is selected.
- Services can be `on_demand` or `always_on` and may wake on schedules for network-message/file exchange.
- Services can run locally, in an emulator/VM, over serial/TCP/SSH, or on another UBB-compatible host.
- Main-menu exposure is policy. A door, MUD, shell, IRC service, etc. can be direct, BBS-only, both, or hidden.
- Network-acquired software is preserved immutably with provenance and checksums **before** installation.
- Redistribution to Mystic/ABBS filebases is deny-by-default and requires explicit rights metadata.
- Runnable integrations are added incrementally; manual/assisted setup is a supported first-class state.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/MILESTONES.md](docs/MILESTONES.md).

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

M5 supplies the default adapter-backed runtime driver. Existing services without runnable `runtime_config`—including the current Mystic deployment—remain managed by their current deployment; the supervisor fails closed rather than pretending it can control them. See [docs/SUPERVISOR.md](docs/SUPERVISOR.md).

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
  mystic_bbs/        early Mystic integration
  network_gateway/   firewall/fail2ban
  backup/            current Mystic-specific backup implementation
  monitoring/        node_exporter
files/mystic_doors/   current Mystic .mpy door placeholders
```

These roles continue to work during the transition. Later milestones will separate lifecycle, routing, backup/state, and actual BBS publication from individual BBS integrations.

## Current deployment

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/bootstrap.yml -u root -k
ansible-playbook playbooks/site.yml
```

The current Mystic installation still requires an assisted first-time `mis -cfg` configuration. This is now intentionally modeled as a valid `assisted` integration rather than considered an automation failure.

## Secrets

Do not commit credentials, BBS registration keys, FTN passwords, SMTP secrets, or SSH private keys. They must remain outside preservation objects and catalog manifests and be injected through a later secrets-provider contract.
