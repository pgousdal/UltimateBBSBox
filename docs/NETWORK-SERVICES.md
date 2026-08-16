# M6.1 DNS and NTP

DNS and NTP are infrastructure services, hidden from caller menus and exposed
through accurate UDP endpoint declarations. The initial strategy is deterministic
configuration rendering compatible with Debian-packaged Unbound/dnsmasq and
chrony; package installation remains ordinary OS package management, not a
museum artifact download. Any non-package-managed payload must enter through
M1 under the global preservation-first policy.

DNS targets Debian's `unbound` package (with dnsmasq-compatible local rendering)
and uses configurable `ubb.internal` by default, loopback/private binding,
explicit trusted recursion policy, and opt-in static records. NTP supports
`client_only` and trusted `client_and_server` modes using Debian's `chrony`
package; public serving is never a default. Historical guests may use these services where their TCP/IP stack
supports DNS/NTP; guest clock compatibility hacks are intentionally deferred.

`scripts/ubb-network.py dns|ntp render|validate|status` provides safe diagnostics.
Registry services `dns-core` and `ntp-core` use `always_on`, infrastructure
type, and no main-menu exposure. M8 observes them through the ordinary service,
health, endpoint, and alert models. Ports are DNS TCP/UDP 53 and NTP UDP 123;
firewall changes and daemon activation remain operator/provisioning concerns.
Generated text can be published with the shared atomic-write helper; invalid
input is rejected before publication. CI uses fixtures and does not install
packages or alter the host resolver or system clock. Package versions are
therefore environment-specific and must be recorded during deployment
qualification.

This document introduced M6.1. Subsequent M6 milestones now provide Edge,
Internet Mail, NNTP, IRC, FTN, Offline Exchange, and network hardening; see
[EDGE.md](EDGE.md), [MAIL.md](MAIL.md), [NEWS.md](NEWS.md), [IRC.md](IRC.md),
[FTN.md](FTN.md), [OFFLINE-EXCHANGE.md](OFFLINE-EXCHANGE.md), and
[NETWORK-HARDENING.md](NETWORK-HARDENING.md).
