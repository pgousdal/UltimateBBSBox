# Tier-1 hardening and qualification

M7.4 hardens the existing Mystic/Linux, ABBS/Amiga, AmiExpress stable, and
AmiExpress current integrations. It does not add products or M6 network
services.

## Evidence and readiness

Qualification evidence is recorded per integration and release with one of
`PASS`, `FAIL`, `HUMAN_REQUIRED`, `SKIP`, or `BLOCKED`. The readiness command
aggregates those observations; a green test suite is not itself production
readiness.

```text
READY                         all checks PASS
READY_WITH_HUMAN_REQUIREMENTS PASS plus HUMAN_REQUIRED checks
NOT_READY                     a FAIL exists
BLOCKED                       no evidence or an external prerequisite blocks work
```

Use `python3 scripts/ubb-integration.py readiness <integration>` to inspect a
deployment. Real Amiga boot, BBS login/menu observation, and licensed-private
ROM/OS checks remain human evidence when those assets are unavailable. No
terminal content, passwords, ROMs, or registration data is written to evidence.

## State boundaries and recovery

Preserved M1 objects are immutable and recoverable software. Installation
creates derived media or an installed release; a golden/base image is never
used as the mutable runtime working image. Users, messages, filebase metadata,
uploads, queues, configuration, and door state are mutable state and must be
backed up independently. Logs and caches are transient.

The shared `ubb_integrations.hardening` helpers provide a backup manifest,
verified restore, immutable-object assertion, and golden/working invariant.
Restore refuses to run unless the preservation artifact has already been
verified and never overwrites the archive. Use disposable roots for drills.

Current AmiExpress promotion remains candidate -> qualification -> explicit
`current`, retaining `previous`. Rollback swaps software pointers and leaves
live BBS state untouched by default. Unknown data migration makes rollback
`HUMAN_REQUIRED`, not an automatic promise.

## Lifecycle, routing, and bridges

M3 remains the sole lifecycle owner. Restart limits, stale-process
reconciliation, readiness timeouts, holds, idle shutdown, and scheduled wake
are tested through the generic supervisor. M4 owns route authorization and
releases each lifecycle hold exactly once on close or failure. Amiga
integrations use the generic FS-UAE and raw serial-over-TCP path; reconnect,
EOF, sequential callers, and failed-connect cleanup are transport concerns,
not ABBS/AmiExpress branches.

## Qualification matrix

| Integration | Intended state | Current evidence |
|---|---|---|
| Mystic/Linux | native, on-demand or always-on | synthetic lifecycle/state/backup checks PASS; real installation/login is HUMAN_REQUIRED |
| ABBS 3.2 | FS-UAE, on-demand or always-on | preservation and synthetic bridge/lifecycle checks PASS; licensed Amiga boot/login HUMAN_REQUIRED |
| AmiExpress 5.6.1 | FS-UAE museum reference | preservation and synthetic checks PASS; licensed Amiga boot/login HUMAN_REQUIRED |
| AmiExpress pinned development | FS-UAE, recommended always-on | immutable pin/promotion/rollback and synthetic checks PASS; licensed Amiga boot/login HUMAN_REQUIRED |

M7.4 is complete when these external observations have an explicit workflow,
the shared recovery/state invariants are proven, and no synthetic result is
reported as a real emulator observation.

## Disaster-recovery drill

The repeatable drill is: verify the M1 artifact, install into a disposable
root, restore a verified live-state backup, start through M3/M5, route through
M4, observe readiness, then stop and reconcile. Mystic can use a disposable
native fixture; Amiga products require operator-supplied licensed assets. The
repository tests exercise the same ordering and fail-closed behavior without
those assets.

M7.4 intentionally does not add new BBS products, M6 services, emulator
adapters, central identity, or automatic production upgrades.
