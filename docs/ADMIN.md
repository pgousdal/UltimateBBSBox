# M8.1 Admin Observatory

The Admin Observatory is a local, read-only operator plane. It aggregates the
validated M2 registry, M1 preservation metadata, M3 persisted instance state
and event journal, M4 session journal, M5/integration diagnostics, and M7
qualification/deployment records. None of those sources is rewritten and the
observatory is not a second source of truth.

## CLI

```text
python3 scripts/ubb-admin.py status
python3 scripts/ubb-admin.py --json services
python3 scripts/ubb-admin.py --json service abbs-main
python3 scripts/ubb-admin.py --json sessions
python3 scripts/ubb-admin.py --json activity --limit 50
python3 scripts/ubb-admin.py --json alerts
python3 scripts/ubb-admin.py --json readiness
python3 scripts/ubb-admin.py --json artifacts
python3 scripts/ubb-admin.py --json backups
```

Use `--catalog`, `--archive-root`, `--supervisor-state`, `--router-state`, and
`--install-root INTEGRATION=PATH` to point at an appliance or disposable test
roots. JSON and text output are deterministically ordered. Normal views read
metadata only; they do not run archive `verify-all` or contact GitHub.

## Semantics and safety

Configured lifecycle policy (`always_on`/`on_demand`) is shown separately from
actual M3 state. Remote endpoints retain their location and report health as
`UNKNOWN` when remote-supervisor RPC is unavailable. Session and activity
records contain anonymous IDs and metadata only: passwords, credentials,
terminal bytes, and private messages are filtered. Backup rows summarize the
existing verified M7 live-state manifests; no backup operation is performed.

Qualification states and current/previous/candidate deployment pointers are
read from the integration records. Missing optional journals or malformed
optional event lines degrade the snapshot and appear in `degraded_sources`;
registry/schema failures still fail loudly.

Alerts are derived and read-only: failed or unexpectedly stopped `always_on`
services, blocked qualification, unverified artifacts, missing backup evidence,
and candidate deployments are surfaced with stable severity/IDs. M8.1 adds no
start/stop, maintenance, qualification, promotion, rollback, web server, or
admin authentication.

M8.2 may serialize this same model to a read-only web view. M8.3 owns
authenticated actions and audit; M8.4 owns remote hosts and monitoring
hardening. Optional Prometheus export remains future work.
