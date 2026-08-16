# DOS runtime foundation (M9.1)

M9.1 provides a product-neutral DOS guest foundation; it does not install a BBS
product. The reference open guest is FreeDOS, represented by the `freedos-bbs`
profile. Operator-supplied MS-DOS or DR-DOS media can be represented only with
`licensed_private` rights metadata. UBB never downloads proprietary DOS media.

## Backend decision

The architecture evaluates DOSEMU2, DOSBox-X, DOSBox Staging, and QEMU/VM. The
reference adapter is `dos`, with a selectable backend (`dosemu2`, `dosbox_x`,
`dosbox_staging`, or `qemu`). DOSEMU2 is the preferred production investigation
because its headless Linux process model and serial support fit BBS workloads;
the repository does not claim a real backend or FreeDOS boot qualification until
an isolated operator test is performed (`HUMAN_REQUIRED`). DOSBox-X/Staging are
useful compatibility alternatives, while QEMU provides stronger VM isolation at
greater operational cost. No emulator is installed by this milestone.

## Isolation and lifecycle

The preserved/golden DOS base is immutable. A deployment materializes a separate
working root under `services/<service-id>/`; drives are explicit absolute roots,
never `/`, and traversal/symlink exposure is not accepted by the model. Runtime
assets are reconstructable; BBS databases, messages, configuration changes, node
state, and file areas are living state and require the normal M8 backup policy.
Guest networking is disabled by default.

M3 continues to own `always_on`, `on_demand`, and `scheduled` lifecycle policy.
M5's generic process adapter owns start/stop/reconcile/readiness. Readiness can
prove process and PTY availability, but not that an uninstalled BBS is ready.

## Serial and terminal boundary

COM1–COM4 are modeled as generic PTY, TCP, physical-serial, or future modem
endpoints. The connector preserves bytes and carries terminal metadata (CP437,
ANSI, 80x25, explicit CR/LF/CRLF and baud). The current capability is
`byte_stream`; modem signal and full Hayes emulation are not claimed. M4 remains
the caller session boundary: caller → router → generic stream → DOS COM port.
Raw TCP, Telnet-compatible bytes, and negotiated Telnet are distinct concepts.

## Multinode and security

`NodeAllocator` provides bounded, thread-safe, idempotent allocation, release, and
stale recovery. Shared BBS databases are explicit; per-node temporary/session
state remains isolated. DOS guests receive no host shell, privileged devices,
arbitrary filesystem, or unrestricted IP networking. Physical RS-232 is modeled
but not required for tests. Future M9.2 products own their startup commands,
dropfiles, and BBS-specific locking qualification; no product branch exists here.

FreeDOS acquisition, if performed later, must pass through M1 preservation,
provenance, checksums, and rights metadata. Historical BBS compatibility,
multinode file-lock behavior, physical serial, and real emulator/guest boot are
`HUMAN_REQUIRED`.
