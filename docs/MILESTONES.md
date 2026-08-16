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

## M4 — Session router and exposure policy

Implement main-menu exposure, via-BBS-only services, stream handoff, terminal metadata, and remote endpoint routing. No mandatory UBB end-user login.

## M5 — Runtime adapters

Add adapters incrementally: native Linux, DOS, FS-UAE, VICE, MAME, Hatari, QEMU, SIMH, and others as integrations require them.

## M6 — BBS network/core services

Add DNS, NTP/time, SMTP/POP3/IMAP, NNTP/INN, IRCd, FTP/TFTP, UUCP, FTN (binkd/Husky), QWK/REP, Blue Wave, modem/serial bridges, and rights/policy-controlled gateways.

## M7+ — Museum integrations

Add BBS, Door, Interactive Fiction, and MUD/Online World integrations one at a time. Each integration is independently preserved, documented, installed, and qualified.
