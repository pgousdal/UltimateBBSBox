# M6.2 edge node and secure overlay

M6.2 defines a public VPS edge (`edge-1`) and private UBB site without requiring
public home IPv4, static home addressing, or inbound port forwarding. The
recommended provider is Headscale as a control plane with Tailscale clients on
the edge and home nodes. Headscale coordinates peers; it is not a mandatory
packet-forwarding gateway. Direct peer traffic is preferred and optional DERP
relay is represented but disabled by default.

Tailscale SaaS, raw WireGuard, ZeroTier, and Nebula are supported configuration
identities. Their real tunnel qualification remains `HUMAN_REQUIRED` until an
operator performs provider-specific connectivity checks. Private keys, auth
keys, certificates, and tokens are external secret references only.

## Public edge and ingress

`EdgeConfig` models edge nodes, private sites, least-privilege routes, public
identities, and TCP/UDP/HTTP/HTTPS ingress. Listener conflicts are rejected.
Raw TCP/Telnet does not carry the DNS hostname selected by a caller, so two
names cannot share one IP/port listener. Use different public ports or distinct
public IP selectors; a future shared `bbs.example` selector is a separate
service concern. HTTP/HTTPS hostname routing is representable because those
protocols carry Host/SNI identity.

Public identities are intent for an external authoritative DNS provider. M6.1
Unbound remains internal DNS and is never changed into public authoritative DNS.
The firewall posture is deny-by-default: only explicitly declared edge
listeners (and optional Headscale HTTPS/DERP) should be opened. The admin
dashboard remains private and is reached over the overlay or an operator VPN.

## State and recovery

Headscale database/state, configuration, policy, and private DERP-related state
are living infrastructure state and are eligible for the M8.3c backup model.
Package binaries are reconstructable and are not museum artifacts. A replacement
VPS is provisioned, package-managed daemons are installed, control state and
configuration are restored, and public DNS is updated if the address changes;
home nodes then reconnect. No provider API or remote command executor is added.

Use `python3 scripts/ubb-edge.py {status,nodes,routes,ingress,public-identities,validate}`
for deterministic read-only fixture diagnostics.

M4 remains the logical caller-session router. Edge forwarding is transport
ingress and does not itself implement terminal sessions. Guest DNS/NTP usage is
documented by M6.1; guest OS-specific networking is deferred.
