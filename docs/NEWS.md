# M6.4 NNTP / news service

M6.4 models a Debian-package INN deployment as `nntp-core`. INN is a mature
NNTP daemon; UBB owns validated group/policy intent and deterministic generated
definitions while the package owns protocol handling. No NNTP server is written
in Python and no public feed is contacted by tests.

The conservative default is `private_only` on TCP/119. `public_read` and
`public_read_write` are explicit; public posting requires TLS configuration.
Optional NNTPS/implicit TLS on TCP/563 is modeled. Private keys are external
references. Public identities are M6.2/external-DNS intent; M6.1 Unbound stays
internal. Retention is bounded by age, article count, and bytes.

Groups have independent read/post policies, moderation, descriptions, and
optional BBS service/area mappings. Adapters are product-neutral and support
inbound, outbound, bidirectional, scheduled exchange, and native NNTP modes.
Scheduled exchange reuses M3 holds/scheduling. Stable external checkpoints and
Message-ID tracking belong to adapters to prevent NNTP/BBS loops; article
content is never placed in observatory, dashboard, or audit state.

External feeds are explicit disabled-by-default intent with external secret
references. The spool is living mutable state: raw live-spool tar is not claimed
as a consistent backup. Recovery combines package/config, bounded checkpoint
backups, and feed replay or a daemon-consistent spool strategy. Queue/spool
metrics and outage/expiry/adapter alerts are safe aggregate evidence.

Tier-1 product capability and real public peering remain `HUMAN_REQUIRED`.
