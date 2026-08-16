# Security policy

Ultimate BBS Box is an infrastructure/preservation project under active
development. Security reports should be made privately to the repository
maintainer through the Git hosting account's private security-reporting channel
(or a private maintainer contact if one is configured); do not disclose an
unfixed issue in a public issue first. This repository does not promise 24/7 or
commercial incident response.

Never include passwords, FTN peer credentials, DKIM/TLS private keys, admin
credentials, ROMs, registration keys, private mail/messages, packet contents,
or other private assets in issues, patches, or logs. Remove secrets before
sharing diagnostics.

Important trust boundaries include the public VPS edge, secure overlay, local
admin plane, immutable M1 preservation archive, runtime/living state, and
external secret references. The dashboard is loopback-bound by default and
network services use explicit exposure policies. Real public DNS, SMTP, NNTP,
IRC, FTN, and historical BBS interoperability remain HUMAN_REQUIRED unless
observed in a controlled environment; deterministic tests are not evidence of
public deployment safety.

The repository currently has no explicit project license. Do not assume that
third-party BBS software, ROMs, AmigaOS media, or preserved artifacts are
redistributable.

Repository-owned UBB source and documentation are MIT-licensed. That license
does not extend to third-party software or preserved artifacts.

## Admin login protection

Admin login failures are throttled independently by username and socket-peer
source. Failures 1–3 have no delay; failure 4 applies a 5-second reject-until
delay, then delays increase and cap at 60 seconds. Throttling rejects
immediately rather than sleeping, expires with cooldown, resets on successful
login, and is bounded to a finite in-memory table. Process restart resets the
table. Unknown users use the same PBKDF2 verification path and receive the same
external invalid-login response. Untrusted forwarding headers are ignored.
Throttled web requests return 429 with bounded `Retry-After`.
