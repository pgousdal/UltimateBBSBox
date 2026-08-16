# Lifecycle supervisor

M3 is the product-neutral runtime lifecycle layer. It consumes validated M2 service declarations and coordinates one shared runtime instance per service. It does not interpret product names and does not imply that every cataloged service has a usable driver.

## State machine

The explicit states are:

```
stopped -> starting -> ready -> running -> stopping -> stopped
                          \-> maintenance -/

starting/running/maintenance/stopping -> failed
failed -> starting   (bounded recovery or explicit start)
failed -> stopped    (cleanup/reconciliation)
```

Every transition is validated; invalid edges raise `InvalidTransitionError`. A successful start first asks the driver to create or adopt a runtime, then polls readiness, records `ready`, and finally records `running`. Process existence alone is not readiness.

An instance ID is stable as `<service-id>:shared`. Clustering and per-caller runtime nodes are deliberately deferred.

## Holds and sharing

Counted holds explain why an instance must remain alive:

- `always_on`: declarative convergence policy;
- `admin`: explicit operator intent;
- `sessions`: logical M4-facing session references;
- `maintenance`: one or more jobs;
- `recovery`: a pending/restarting runtime.

Removing one hold never stops a runtime while another remains. `single_session` rejects a second logical session; `multiuser` permits multiple opaque session IDs. No end-user identity or terminal bytes are involved. Session references are intentionally process-transient and are not restored as caller sessions after supervisor recovery.

For `on_demand`, final hold release sets an idle deadline. A new hold clears it. `idle_timeout_seconds: 0` means stop on the next `tick`, not recursively inside release. For `always_on`, reconciliation installs an `always_on` hold and converges toward running.

Examples:

```
A. caller -> session hold -> start -> ready -> running
          -> release -> idle deadline -> tick -> stop

B. 03:00 -> maintenance hold -> wake -> ready -> network-exchange action
          -> release -> stop (when maintenance was the sole reason)

C. maintenance hold + caller session hold
          -> maintenance ends -> release maintenance -> remain running

D. always-on multiuser UNIX/VMS-style service
          -> always_on hold + N session holds -> remains running after sessions leave
```

## Drivers and readiness

`RuntimeDriver` defines `start`, `stop`, `status`, `is_ready`, and `run_maintenance`, returning structured mappings. `FakeDriver` provides deterministic tests. `LocalProcessDriver` is the only bundled production driver: it starts a trusted `local_process` endpoint argument vector without a shell, records the PID, checks process liveness, and can run an explicit maintenance command argument vector.

Readiness types are `immediate`, `process_alive`, `command_probe`, and `driver_specific`. The driver interprets them; command probes use argument vectors and no shell. Startup polling uses `startup_timeout_seconds`, and timeout enters `failed` before restart policy is considered. Unsupported endpoint/runtime combinations fail closed pending M5 adapters.

## Failure and restart

`never`, `on_failure`, and the already-defined `always` policy are understood. Failure recovery is bounded by `max_restarts` (default 3) inside `restart_window_seconds` (default 60), with optional `restart_backoff_seconds` (default 0). Exhaustion leaves the instance failed and raises `RestartLimitExceededError`; no infinite loop is hidden. Last failure, attempt timestamps, and next eligible restart time are persisted.

## Maintenance scheduling

Supported schedule strings are:

- `every Nm`, `every Nh`, or `every Nd` with a positive integer;
- `daily HH:MM`, or `daily at HH:MM`.

Daily time uses the timezone-aware local clock of the supervisor process. Interval comparisons use persisted timezone-aware timestamps. A job is marked due before execution and guarded in memory so overlapping ticks cannot execute it twice.

The supervisor acquires a maintenance hold, starts and waits for readiness if necessary, invokes the driver's named job, stores its structured result, and releases only that hold. An always-running or administratively held runtime stays up. A runtime woken solely for a job with `shutdown_after: true` stops immediately afterward. M3 orchestrates actions; it contains no FTN, QWK, NNTP, BBS, or product-specific maintenance logic.

## Concurrency and persistence

Every service has a reentrant lock covering transition and hold changes. Duplicate starts coalesce, stop/start operations serialize, final-session releases are atomic, and the driver maintenance call deliberately runs outside the service lock so a caller hold may arrive. The scheduler separately marks running jobs to prevent duplicate execution.

The default state root is `/var/lib/ultimate-bbs-box/supervisor/`:

```
instances/<service-id>.json  atomic current/recovery state
events.jsonl                append-only structured transition journal
```

State files contain timestamps, administrative/always-on intent, restart accounting, failures, maintenance outcomes, schedules, and generic driver runtime data. Registry YAML remains authoritative configuration. Caller streams are never persisted.

On construction, persisted states are loaded. `reconcile` compares them with driver status: stale starting/stopping states are adopted or reset, abandoned maintenance returns to running, missing on-demand runtimes without surviving holds settle stopped, and always-on/admin holds converge toward running. Lost transient sessions lead to the normal idle rule rather than permanent leaked holds.

M3 supports one supervisor writer process. The library is thread-safe per service; the provided systemd timer serializes one-shot `tick` processes. A future local authenticated IPC service may provide cross-process control, but no network control API is exposed.

## CLI and execution model

```bash
python3 scripts/ubb-supervisor.py --state-dir PATH status [SERVICE_ID]
python3 scripts/ubb-supervisor.py --state-dir PATH start SERVICE_ID
python3 scripts/ubb-supervisor.py --state-dir PATH stop [--force] SERVICE_ID
python3 scripts/ubb-supervisor.py --state-dir PATH restart SERVICE_ID
python3 scripts/ubb-supervisor.py --state-dir PATH maintenance SERVICE_ID JOB_ID
python3 scripts/ubb-supervisor.py --state-dir PATH reconcile
python3 scripts/ubb-supervisor.py --state-dir PATH tick
```

Place global `--json`, `--catalog`, and `--state-dir` options before the command. The included `systemd/ubb-supervisor.service` is a hardened one-shot tick and `systemd/ubb-supervisor.timer` invokes it every 30 seconds. Installation must create the unprivileged `ubb-supervisor` account and install the checkout at `/opt/ultimate-bbs-box`; M3 does not modify the existing Ansible deployment automatically.

## Explicitly deferred

M4 and later own terminal byte streams, menu generation, exposure/access enforcement, door/session handoff, terminal negotiation, authenticated local control IPC, remote-supervisor RPC, emulator adapters, network services, product-specific maintenance implementations, BBS publication, and central UBB identity. Existing Mystic remains managed by its current Ansible role until a separately qualified generic runtime integration replaces that responsibility.
