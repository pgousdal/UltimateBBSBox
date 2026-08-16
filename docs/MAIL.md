# M6.3 Internet mail

M6.3 models a Debian-package Postfix edge MTA and a separate UBB Mail Core.
The edge terminates public TCP/25, applies normal Postfix anti-open-relay and
recipient checks, and queues accepted mail while the private site or overlay is
unavailable. Mail Core routes validated recipients to product adapters; the
two roles may share a host for a small installation but remain separate.

Mail domains, recipients, aliases, MX/SPF/DKIM/DMARC intent, TLS references,
trusted relay networks, and direct-MX/smarthost outbound mode are typed and
deterministic in `scripts/ubb_mail.py`. Catch-all is disabled by default,
unknown recipients are rejected, SPF always terminates explicitly (never
`+all`), and Postfix uses `reject_unauth_destination`. TCP/25 is modeled; mail
submission is not enabled by default and would require authentication.

DKIM uses an external OpenDKIM-compatible key reference and configurable selector;
public DNS records are intent for an external authoritative provider. DMARC
defaults to `p=none` for safe rollout and can progress to quarantine/reject
after evidence. STARTTLS is opportunistic for server-to-server SMTP, with
external certificate/key references. PTR/rDNS is controlled by the VPS provider,
not the public MX zone. Technical correctness does not guarantee deliverability.

Adapters are product-neutral: `native_smtp`, `mailbox_bridge`,
`batch_exchange`, and `scheduled_exchange` (the latter reuses M3 lifecycle
holds/scheduling). Current Tier-1 mail capability remains `HUMAN_REQUIRED`
until qualified from authoritative product evidence.

Postfix queue data and adapter checkpoints are living state. Do not tar a live
spool and call it a valid backup; follow M8.3c state-specific recovery. DKIM/TLS
keys and smarthost credentials require secure external backup. Observability and
CLI expose only aggregate queue counts/ages and routing metadata—never message
bodies, subjects, credentials, or arbitrary headers.

Use `python3 scripts/ubb-mail.py {status,domains,recipients,dns,queue,adapters,validate,render}`
for fixture diagnostics. No real DNS is changed and no Internet mail is sent by
tests; public MX, PTR, inbound/outbound delivery, and external DKIM/SPF/DMARC
verification remain `HUMAN_REQUIRED`.
