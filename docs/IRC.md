# M6.5 IRC infrastructure

M6.5 models a Debian-package InspIRCd deployment as the hidden, always-on
`irc-core` infrastructure service. InspIRCd is mature, supports TLS and modern
IRC behavior, and keeps protocol/configuration handling out of UBB Python. The
default is `private_only`; `public` requires explicit opt-in and an external TLS
certificate/key reference. TLS uses TCP/6697; plaintext TCP/6667 is optional and
never public by default.

Server/network identity, channels, visibility, invite-only/moderated flags,
bounded history, and connection limits are typed. No persistent history store
or services suite (NickServ/ChanServ) is required. IRC client credentials,
operator credentials, and BBS accounts are separate security domains and use
external secret references.

Bridges are explicit and product-neutral: inbound, outbound, bidirectional,
scheduled, or native IRC. A mapping names a BBS service, IRC channel, and BBS
area; private-to-public bridging is rejected unless IRC is public and the
mapping opts in. Adapter-owned stable checkpoints/message identity prevent
IRC/BBS loops. M3 remains the scheduler for legacy scheduled bridges, and BBS
nicknames are not automatically shared with IRC identities.

M6.2 supplies the public edge/overlay and external DNS identity; the home host
does not need direct public exposure. Observability exposes only aggregate
client/channel/bridge/listener metrics, never messages or private keys. Config
and persistent registration/bridge state are living data; transient connections
are not backup state. Real public IRC and Tier-1 bridge qualification remain
`HUMAN_REQUIRED`.

Use `python3 scripts/ubb-irc.py {status,channels,bridges,listeners,validate,render}`
for deterministic diagnostics. Tests do not alter DNS/firewalls or publish IRC.
