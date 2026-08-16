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

## Lifecycle

Every runnable service can select independently:

- `on_demand` or `always_on` availability;
- `single_session` or `multiuser` sharing;
- idle timeout and startup timeout;
- crash restart policy;
- zero or more scheduled maintenance jobs.

Scheduled maintenance is orthogonal to availability. An on-demand BBS may wake at 03:00, import/export network traffic, then return to sleep. An always-on BBS runs the same maintenance job without being stopped afterward.

## Remote services

A service endpoint may be on another machine. This is first-class, not a workaround. A front-end UBB instance may route a caller to a remote supervisor hosting SIMH, QEMU, UNIX Time Machine, VAX/VMS, MUDs, or other services.

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
