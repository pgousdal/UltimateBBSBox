# M8.2 read-only dashboard

`scripts/ubb-dashboard.py` is a small Python standard-library HTTP server
that presents the M8.1 `ubb_observatory` read model. It does not parse M3/M4
files itself, create a database, or perform lifecycle, backup, qualification,
promotion, or rollback actions.

Start locally with `python3 scripts/ubb-dashboard.py --bind 127.0.0.1 --port
8088`. The default is loopback-only; remote operation belongs behind an
authenticated reverse proxy or VPN until M8.3. Pages cover overview,
services/detail, sessions, activity, alerts, readiness, artifacts, backups,
and hosts. Versioned GET-only JSON endpoints live under `/api/v1/`.

HTML is escaped and uses semantic headings, table headers, visible focus,
text state labels, and a restrictive content security policy. API output
inherits M8.1 privacy filtering: no passwords, keys, credentials, terminal
bytes, or private message content. Remote health without telemetry is
`UNKNOWN`; normal requests do not hash archive objects or contact GitHub.

The server is dependency-free and has no frontend build pipeline. Authenticated
admin actions, audit, and hardened remote deployment are deferred to M8.3.
