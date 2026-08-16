# M6.8 network hardening and qualification

M6.8 consolidates the M6.1–M6.7 registry services into a read-only inventory
and readiness view. `scripts/ubb_network_hardening.py` derives services and
listeners from the authoritative catalog/registry; it is not a second registry.
The CLI `scripts/ubb-network.py` provides status, services, listeners, exposure,
dependencies, readiness, secrets, TLS, queues, validation, and drift views.

Readiness distinguishes deterministic configuration from real deployment
qualification. Current fixture services are `READY_WITH_HUMAN_REQUIREMENTS`;
real daemon activation, public DNS, VPS/overlay connectivity, SMTP/NNTP/IRC/FTN
peers, and historical offline-reader interoperability require operator evidence.
Invalid configuration or dependency cycles are hard validation failures.

The reference exposure policy is private/overlay first and explicit `edge_public`
only. A deny-by-default firewall intent records established/related handling,
trusted overlay policy, and protections against open DNS/NTP, SMTP relay, and
anonymous FTN injection. No firewall rules are applied by this milestone.

Secret inventory contains identifiers and external references only. TLS state is
not fabricated when certificate files are unavailable. Queue views are aggregate
placeholders for mail, NNTP, FTN, and offline exchange; content is never read.
Drift inspection compares deterministic desired digests without overwriting live
configuration. Remote health continues to use M8.4 heartbeat semantics.

M6.8 adds no protocol, daemon, remote command path, or admin identity system.
