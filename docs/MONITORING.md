# Monitoring hardening (M8.4)

Monitoring is a derived layer over the M1–M8 authoritative state. It does not
control services, write registry/archive data, or provide notifications.

## Health and hosts

Service lifecycle (`running`, `stopped`, `failed`) is separate from health:
`HEALTHY`, `DEGRADED`, `UNHEALTHY`, or `UNKNOWN`. An expected on-demand stop is
healthy; an always-on stop is unhealthy. Remote services and hosts without
telemetry remain `UNKNOWN`, never `OFFLINE`.

The local host is observed conservatively. Remote heartbeat/RPC ingestion is
limited to strict JSON observations via `ubb-monitor.py heartbeat ingest FILE`;
it never executes commands, and no remote supervisor RPC exists. Stale or
missing observations produce `UNKNOWN`.

Storage policy observes logical state, backup, and archive roots using both
free percentage and absolute free bytes. Warning and critical thresholds are
configurable in `MonitoringEngine` and filesystem failures degrade to
`UNKNOWN` without attempting repair.

## Alert lifecycle

`scripts/ubb_monitoring` derives stable condition IDs and persists only bounded
derived records under `state/observatory/alerts.json`. Records contain
`ACTIVE`/`CLEARED`, first/last seen, occurrence count, severity, and safe
target summaries. Re-evaluation updates an existing condition rather than
creating alert storms; cleared history is retained up to the configured bound.

Backup, qualification, artifact, host, and service health conditions are
represented without rehashing the archive or reading terminal/message data.

## Interfaces

`python3 scripts/ubb-monitor.py evaluate --json` performs one evaluation and
returns 0 for no warning/critical alerts, 1 for warnings, and 2 for critical
alerts. The authenticated dashboard exposes `/api/v1/health`, host detail, and
alert lifecycle data. `ubb-monitor.service` plus `.timer` are optional,
unprivileged one-minute systemd units.

No acknowledgement, suppression, email/webhook delivery, database, remote RPC,
or automatic cleanup is implemented in M8.4.
