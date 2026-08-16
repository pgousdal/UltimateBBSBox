# Ultimate BBS Box Architecture

## M0 architecture contract

Ultimate BBS Box (UBB) remains BBS-centric. It is a front door, catalog, session router, lifecycle supervisor, preservation system, and infrastructure host. It does **not** require end users to authenticate to UBB before selecting a destination. Authentication normally belongs to the selected BBS, MUD, shell, IRC service, or other destination.

### Core abstractions

UBB core understands generic contracts, not product names:

- **Artifact** — an immutable preservation object plus provenance and rights metadata.
- **Service** — what a caller can reach: BBS, door, MUD/world, talker, interactive fiction, shell, IRC, NNTP, Gopher, or another terminal service.
- **Endpoint** — where a service runs: local process, TCP service, SSH target, serial device, or another UBB-compatible supervisor.
- **Exposure** — whether a service appears in the UBB main menu, is reachable only through selected BBSes, both, or neither.
- **Lifecycle** — on-demand or always-on operation, sharing semantics, readiness, idle shutdown, and scheduled wake/maintenance.
- **Integration** — the product-specific recipe that acquires, installs, configures, qualifies, and operates one service target.

Core code must not branch on BBS product names. Product knowledge belongs in integrations.

## Caller authentication

UBB does not provide a mandatory shared end-user identity system.

Typical flow:

```
caller -> UBB menu -> BBS -> BBS login
caller -> UBB menu -> MUD -> MUD login
caller -> BBS door -> remote UNIX -> UNIX login
```

A future optional identity bridge may exist for selected services, but it is not part of the v1 core contract.

## M4 routing boundary

M4 enforces exposure as route authorization. A direct route requires both `main_menu: true` and `access.direct_allowed` (true by default); an administrative-only declaration is denied because M4 has no identity assertion system. A via-service route must name an allowed `via_bbs` service and be anchored to an active parent session for that origin, so merely supplying a BBS ID cannot bypass direct-route policy.

Router sessions have their own explicit state machine, separate from M3 runtime instances. Opening resolves M2 metadata, acquires an M3 logical session hold, and only then connects a transport. Close, EOF, and failure paths own cleanup exactly once. Terminal capabilities and opaque non-secret caller metadata travel with the session, but authentication credentials and terminal bytes belong to the destination/stream and are never journaled.

M4 provides raw generic TCP and injected stream contracts. It does not perform Telnet negotiation, suspend a real BBS stream, connect SSH/serial/remote-supervisor endpoints by default, build menus, synchronize accounts, or implement product/runtime adapters. Handoff and return-to-origin are modeled as a parent/child session relationship for later integrations.

## M5 runtime boundary

M5 maps the generic `integration.runtime` enum to a deterministic built-in adapter registry. Adapters receive only validated `runtime_config`; they know process/emulator mechanics, never the BBS or guest product. M3 remains the sole lifecycle state machine through an adapter-backed driver bridge, while M4 may obtain an adapter PTY, stdio, or raw TCP stream only after its lifecycle hold succeeds.

Runtime process identity (PID, `/proc` executable, process start ticks, and command digest) is stored in M3's separate runtime state. Reconciliation adopts a recorded process only when identity can be proven, avoiding blind PID reuse. Native, FS-UAE, VICE, QEMU, and SIMH share bounded process-group cleanup and generic readiness. DOS, MAME, Hatari, physical serial, and remote RPC fail explicitly pending later work.

## Lifecycle

Every runnable service can select independently:

- `on_demand` or `always_on` availability;
- `single_session` or `multiuser` sharing;
- idle timeout and startup timeout;
- crash restart policy;
- zero or more scheduled maintenance jobs.

Scheduled maintenance is orthogonal to availability. An on-demand BBS may wake at 03:00, import/export network traffic, then return to sleep. An always-on BBS runs the same maintenance job without being stopped afterward.

### M3 supervisor boundary

M3 represents each catalog service with one shared runtime instance and an explicit `stopped → starting → ready → running/maintenance → stopping` state graph plus `failed` recovery. Per-service locks serialize state changes. Counted holds for always-on policy, administration, sessions, maintenance, and recovery prevent one activity from stopping a runtime still needed by another. Readiness remains separate from process existence, and restart attempts are bounded within a configured window.

Runtime state is stored separately from catalog YAML under `/var/lib/ultimate-bbs-box/supervisor/` by default. Atomic instance files support reconciliation, and an append-only JSONL journal records transitions. Caller streams are never stored. A dependency-injected driver contract isolates lifecycle orchestration from runtimes; M3 bundles only a deterministic fake and a generic local-process implementation, not emulator or remote-supervisor adapters.

M3 scheduling is a single-writer, one-shot `tick` model suitable for a systemd timer. It calculates fixed intervals and daily local wall-clock times, wakes on-demand instances for driver-defined jobs, and releases only the maintenance hold afterward. M3 does not route sessions, build menus, enforce exposure, authenticate callers, or implement maintenance actions such as FTN exchange.

## Remote services

A service endpoint may be on another machine. This is first-class, not a workaround. A front-end UBB instance may route a caller to a remote supervisor hosting SIMH, QEMU, UNIX Time Machine, VAX/VMS, MUDs, or other services.

## M2 registry boundary

Repository YAML under `catalog/services/`, `catalog/endpoints/`, and `catalog/integrations/` is the authoritative production control-plane registry. M2 validates these manifests with the M0 schemas, indexes each kind independently, rejects duplicate IDs and unresolved references, and resolves a service declaration to its endpoint and optional integration. Endpoint normalization is generic across local process, TCP, SSH, serial, and remote-supervisor metadata.

Exposure and lifecycle declarations are data in M2. Queries may select main-menu, hidden, or via-BBS services, but do not build menus, enforce access, schedule maintenance, allocate sessions, connect endpoints, or start processes. Likewise, catalog presence, preserved artifacts, integration presence, qualification evidence, declarative enablement, and runtime state remain distinct. An M2 registry result never claims that a service is installed, qualified, enabled, reachable, or running.

## Preservation

Network-acquired artifacts must not be consumed directly by installers. The required flow is:

```
discover -> acquire -> quarantine/identify -> hash -> preserve immutable original
        -> classify rights -> derive install media -> install
        -> optionally publish the unchanged redistributable artifact to BBS filebases
```

Original bytes are immutable. Repacked, patched, converted, or reconstructed artifacts are new derived objects and must retain ancestry metadata.

Redistribution is deny-by-default. `publish_to_bbs_filebase` must be explicitly true before an artifact can be surfaced as a downloadable file on Mystic, ABBS, or another BBS.

### M1 archive boundary

M1 implements this contract as an ordinary-filesystem archive. SHA-256 names immutable objects; artifact IDs name independently validated metadata records. Acquiring the same bytes deduplicates the object, while acquiring changed bytes from the same sanitized source URL creates a new object and cross-references earlier artifact IDs. Network bytes enter `quarantine/` and cannot become a catalog artifact until the complete stream is hashed, any expected checksums match, the object is atomically linked into place, and metadata is durably written.

Rights decisions remain separate booleans: preservation, local installation, original redistribution, owner export, and BBS publication. Their separation is intentional; provenance from a public site grants none of them. M1 only stages exact-byte publication copies and sidecars. It does not update a Mystic or ABBS filebase.

Artifact preservation state also remains independent of the service and integration contracts. An artifact existing in this archive says nothing about whether its software has an integration, is qualified, or is enabled.

## Mutable state

Preserved artifacts, golden installations, and living mutable state are separate:

```
preserved artifact -> golden installation -> running mutable state
                                         -> users/messages/files/saves/world state
```

Reinstalling software must not destroy living BBS or game state.

## Integration model

Runnable integrations are added one at a time. A registry may know about hundreds of historical targets, but each integration is individually acquired, installed, documented, qualified, and committed.

Automation levels:

- `fully_automated`
- `assisted`
- `manual_install`
- `preservation_only`

Manual installation steps are legitimate and must record required evidence rather than being hidden behind pretend automation.

## Existing Ansible roles

The repository started as a Mystic-on-metal deployment. Those roles remain useful, but in M0 they are treated as an early integration rather than the architecture of UBB itself. Later milestones will move acquisition, preservation, lifecycle, routing, and publication concerns out of product-specific roles.

## Museum integration boundary (M7.1–M7.2)

M7.1 proves the boundary with one real product declaration: Mystic/Linux. Trusted integration code orchestrates existing public APIs in the order `M1 acquire/verify -> product install/configure -> M5 runtime via M3 -> M4 route -> qualification`. It does not download directly, supervise its own process, implement routing, or make artifact presence equivalent to readiness.

The production state remains split:

- catalog manifests declare `mystic-main`, `mystic-local`, and `mystic-linux`;
- M1 stores the original distribution and rights/provenance;
- `integrations/bbs/mystic` owns product-specific extraction and assisted evidence;
- digest-named software releases remain separate from Mystic's living `data`, `text`, `logs`, and `doors`;
- M3 state and M4 sessions remain separate from both preservation and living data.

M7.2 and M7.3 prove the protocol has no assumptions about Linux archives or native execution. Product code selects releases and guest-side assisted steps; canonical Amiga profiles and generic helpers resolve private prerequisites and separate golden/working disks; M5 receives only `fs_uae` metadata; M3 owns boot/readiness and M4 owns raw serial-over-TCP sessions. Preservation, licensed platform assets, installation workspace, golden state, runtime working state, and qualification evidence remain distinct. See [INTEGRATIONS.md](INTEGRATIONS.md), [AMIGA-INTEGRATIONS.md](AMIGA-INTEGRATIONS.md), and [AMIGA-PROFILES.md](AMIGA-PROFILES.md).
