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
