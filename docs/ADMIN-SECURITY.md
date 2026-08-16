# M8.3 admin security

M8.3 introduces a separate operator identity plane; it is never a BBS caller
account and is not synchronized with Mystic, ABBS, or AmiExpress users.

Accounts are stored outside Git (default
`/etc/ultimate-bbs-box/admin-users.json`) with mode 0600 and PBKDF2-HMAC-SHA256
password hashes (240,000 iterations and a random 128-bit salt). The helper
`scripts/ubb-admin-auth.py add USER --role viewer|operator|administrator`
prompts without putting passwords in shell history. Passwords, cookies, CSRF
tokens, and private credentials are not audited.

Web sessions use random 256-bit identifiers, rotate on login, expire after
eight hours, and use HttpOnly, `SameSite=Strict` cookies. Secure cookies should
be added by an HTTPS reverse proxy deployment. Failed login attempts receive a
short per-user/IP exponential in-memory backoff. Browser writes require POST
and a session-bound random CSRF token; GET has no side effects.

`viewer` is read-only, `operator` may request start/stop/restart and registered
operational jobs, and `administrator` may change lifecycle policy or perform
high-impact release actions. The action layer delegates to M3/M7 APIs and
never edits registry, archive, or supervisor files directly. Audit records are
append-only JSONL (default `/var/log/ultimate-bbs-box/admin-audit.jsonl`, mode
0640), include actor/action/target/result/request ID, and are not editable in
the UI. Rotation and cryptographic tamper evidence are operational follow-up,
not claimed here.

The dashboard remains loopback-bound by default and has no custom TLS, public
admin listener, caller identity, or unrestricted-root requirement. Use a VPN,
SSH tunnel, or authenticated reverse proxy for remote access. M8.4 covers
further privilege separation and monitoring hardening.

M8.3b completes registered maintenance, backup, qualification, and AmiExpress
promotion/rollback routes. Operators use the same delegated action service as
the web/API layer; administrators alone may change lifecycle policy or release
pointers. Dashboard forms are role-filtered and every attempt is audited.
