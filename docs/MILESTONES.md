# Delivery milestones

## M0 — Contracts and repository foundation — COMPLETE

M0 freezes the core vocabulary and establishes executable schema checks.

Acceptance:

- architecture contract documents caller authentication ownership, modular integrations, remote endpoints, lifecycle, scheduled wake, and preservation-first acquisition;
- JSON Schema contracts exist for artifact, endpoint, service, and integration manifests;
- example manifests cover a local BBS and a remote shell reachable only through a BBS;
- repository has a single `make check` entry point and CI workflow;
- existing Mystic Ansible role continues to syntax-check and is explicitly classified as an early integration rather than core;
- no mass-import or mass-install assumption exists in M0.

## M1 — Preservation archive and catalog — COMPLETE

Implement immutable content-addressed storage, provenance, rights decisions, acquisition quarantine, derived-artifact lineage, verification, export bundles, and rights-gated publication artifacts.

Acceptance is implemented by the configurable filesystem archive and CLI, additive artifact-v1 schema fields, offline unit tests, and preservation documentation. Network acquisition is quarantined and bounded; SHA-256 objects deduplicate without losing changed-source history; rights default to no redistribution or publication; lineage, verification, human-readable exports, and exact-byte publication staging are covered by `make check`. Actual filebase publication and lifecycle/service registry behavior remain later milestones.

## M2 — Service and endpoint registry — COMPLETE

Persist and query service/endpoint manifests. Resolve local, serial, TCP, SSH, and remote-supervisor endpoints without product-specific branching.

Acceptance is implemented by production catalog directories, a shared M0 schema validator, a deterministic in-memory registry API, generic reference resolution, exposure/type/runtime filters, CLI text/JSON inspection, representative local and remote manifests, and offline tests. M2 is metadata only; it performs no lifecycle action, network connection, routing, or installer execution.

## M3 — Lifecycle supervisor — COMPLETE

Implement `on_demand`, `always_on`, readiness, idle shutdown, multiuser sharing, crash restart, and scheduled wake/maintenance.

Acceptance is implemented by the explicit state machine, counted holds, generic driver protocol, fake and local-process drivers, bounded recovery, injected clock, interval/daily scheduler, atomic state and JSONL journal, reconciliation, CLI, systemd one-shot/timer examples, and deterministic concurrency tests. Terminal routing, menus, runtime-specific adapters, remote RPC, and network services remain later milestones.

## M4 — Session router and exposure policy — COMPLETE

Implement main-menu exposure, via-BBS-only services, stream handoff, terminal metadata, and remote endpoint routing. No mandatory UBB end-user login.

Acceptance is implemented by the explicit session model/state graph, exposure policy, active-origin anchoring, M2 resolution, M3 hold ownership, extensible terminal metadata, raw TCP and injectable stream contracts, generic handoff/return semantics, idempotent teardown, metadata-only JSONL journal, CLI inspection, and deterministic tests. Emulator transports, actual BBS door integration, authenticated IPC, and network services remain later milestones.

## M5 — Runtime adapters — COMPLETE

Add adapters incrementally: native Linux, DOS, FS-UAE, VICE, MAME, Hatari, QEMU, SIMH, and others as integrations require them.

Acceptance is implemented by the runtime protocol/registry, safe process adapter, PTY/stdio/TCP streams, five generic readiness strategies, FS-UAE/VICE/QEMU/SIMH process specializations, M3/M4 bridges, conservative PID reconciliation, diagnostics CLI, and fake-executable tests. DOS, MAME, Hatari, remote RPC, and real product integrations are explicitly deferred.

## M6 — BBS network/core services

Add DNS, NTP/time, SMTP/POP3/IMAP, NNTP/INN, IRCd, FTP/TFTP, UUCP, FTN (binkd/Husky), QWK/REP, Blue Wave, modem/serial bridges, and rights/policy-controlled gateways.

## M7 — Tier-1 and museum integrations

Mystic, ABBS, and AmiExpress are equal Tier-1 priorities. The submilestone numbers express implementation sequence only, not product priority. Every museum integration is independently preserved, documented, installed, and qualified.

### M7.1 — Mystic/Linux reference integration — COMPLETE

The first complete preservation-first integration supplies a trusted minimal integration contract, production Mystic acquisition/rights declaration, verified content-addressed installation, separated living state, assisted `mis -cfg` evidence, native M5 runtime configuration, M3/M4 qualification hooks, explicit result vocabulary, CLI, downloader guard, offline tests, and documentation. A real temporary M1 acquisition/install smoke established the A48 SHA-256 and archive layout; production acquisition and first-run login/menu evidence remain operator-specific and are reported as `HUMAN_REQUIRED`, not fabricated as PASS.

### M7.2 — ABBS/Amiga reference integration — COMPLETE

The same contract now supports the ABBS family with authentic ABBS for All 3.2 provenance and known hashes, M1-only acquisition, conservative rights, lineage-recorded preparation, licensed-private Amiga prerequisites, assisted/resumable installation, golden/working HDF separation, generic FS-UAE metadata, raw serial-over-TCP routing, lifecycle declarations, and machine-readable qualification. A real distribution was acquired and verified through an isolated M1 archive. Licensed Amiga boot assets were unavailable, so boot, ABBS startup, login/menu, and living-state observations remain explicitly `HUMAN_REQUIRED`; no claim was fabricated from synthetic tests.

### M7.3 — AmiExpress/Amiga reference integration

The AmiExpress family integration selects the authentic Aminet `Amix561.lha` 5.6.1 maintained rewrite, preserves it through M1, records mixed-component rights conservatively, derives installation media with lineage, uses the canonical A1200/OS3.1 profile, and reuses generic golden/working HDF, FS-UAE and serial-bridge mechanics. Real boot/login evidence remains `HUMAN_REQUIRED` pending licensed platform assets; no synthetic result is presented as a real AmiExpress qualification.

### M7.3a — AmiExpress current GitHub track

The AmiExpress family now has an immutable, pinned GitHub development channel alongside the unchanged 5.6.1 museum reference. Current-build discovery validates release metadata, commit identity, asset selection, and GitHub digest; M1 preserves exact bytes; candidate qualification precedes explicit promotion; `current`/`previous` pointers support software rollback without reverting living BBS state. No automatic production update occurs. Real emulator qualification remains `HUMAN_REQUIRED` where licensed assets are unavailable.

### M7.4 — Tier-1 cross-integration hardening — COMPLETE

Shared qualification, immutable/live-state boundaries, verified backup/restore,
promotion/rollback gates, lifecycle/route cleanup, and readiness reporting are
implemented and tested. Real Amiga observations remain explicitly
`HUMAN_REQUIRED` where licensed-private assets are unavailable; no synthetic
test is presented as a real boot or login.

### M7.4a — ABBS 1.1 and Tier-1 lifecycle policy cleanup — COMPLETE

The ABBS family now preserves authentic Aminet ABBS v1.1 alongside the
unchanged For All 3.2 reference. Release-specific hashes, rights, profile
claims, and qualification evidence remain independent. Mystic and ABBS 3.2,
as well as the AmiExpress current channel, advertise `always_on` as a
deployment recommendation while service manifests remain configurable.

### M8 — Admin Plane & Observatory

### M8.1 — Observatory/read model + admin CLI — COMPLETE

The product-neutral read-only observatory aggregates M1–M7 state, exposes
deterministic service/session/activity/alert/readiness/artifact/backup views,
and deliberately introduces no write actions or network server.

### M8.2 — Read-only web dashboard — COMPLETE

The standard-library dashboard presents the M8.1 read model with server-rendered
overview/detail pages and versioned GET-only JSON endpoints. It binds to
loopback by default and introduces no database, write actions, authentication,
or frontend build stack.

### M8.3 — Authenticated admin actions + audit — COMPLETE

Authenticated operator sessions, role/CSRF checks, delegated operational action
endpoints, append-only audit records, and granular HTTP verification are
implemented. See [M8.3-ACCEPTANCE.md](M8.3-ACCEPTANCE.md).

### M8.3c — Generic Backup API + privilege boundary

The product-neutral staged backup manager, manifest verification, restore-plan
hooks, Tier-1 living-state declarations, and trusted dashboard delegation are
implemented. Full end-to-end admin action verification remains M8.3d.

### M8.3d — End-to-end admin action verification — COMPLETE

A granular loopback HTTP fixture verifies role matrices, CSRF, delegated
actions, backup/qualification/release paths, concurrency, audit privacy, and
the unprivileged systemd boundary.

### M8.4 — Alerts/remote hosts/monitoring hardening

Future work; not implemented.
