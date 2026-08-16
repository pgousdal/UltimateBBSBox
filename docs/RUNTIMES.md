# Runtime adapters

M5 supplies product-neutral runtime mechanics beneath the M3 supervisor and M4 router. An adapter knows how to launch a native process or emulator family; it never knows which BBS, MUD, operating system, or application runs inside.

Future examples:

```
ABBS integration  -> runtime: fs_uae -> FSUAEAdapter
NiKom integration -> runtime: fs_uae -> the same FSUAEAdapter
C-Net integration -> runtime: vice   -> VICEAdapter
UNIX/VMS service  -> runtime: qemu or simh -> generic adapter
```

These are architectural examples only. M5 adds none of those product integrations or software images.

## Contract and registry

`RuntimeAdapter` defines:

- `prepare(instance, config)` — validate and prepare adapter state;
- `start(instance, config)` — idempotently create a runtime;
- `stop(instance, config)` — bounded graceful/forced shutdown;
- `status(instance, config)` — structured liveness and identity;
- `readiness(instance, config, strategy)` — one readiness observation;
- `open_stream(instance, config)` — PTY, stdio, or raw TCP byte stream;
- `cleanup(instance, config)` — idempotent transient resource cleanup.

Results are typed `RuntimeStartResult`, `RuntimeStopResult`, `RuntimeStatus`, and `RuntimeReadinessResult`. `RuntimeAdapterRegistry` has a deterministic fixed mapping and never loads Python code from YAML. Unknown names raise `UnknownRuntimeError`.

Supported adapters:

- `native`: explicit local executable and argv;
- `fs_uae`: executable plus supplied FS-UAE config file and argv;
- `vice`: caller-selected VICE binary (`x64sc`, `x128`, etc.) plus argv;
- `qemu`: caller-selected QEMU executable plus argv and optional graceful hook;
- `simh`: caller-selected simulator executable, argv, and optional command/config file.

Explicitly deferred registrations are `dos`, `mame`, `hatari`, and `remote`. Operations raise `UnsupportedRuntimeError`.

## Runtime configuration

`integration.runtime_config` is optional for backward schema compatibility but required before an adapter-backed service can run. A representative synthetic declaration is:

```yaml
runtime: fs_uae
runtime_config:
  executable: /usr/bin/fs-uae
  argv: [--fullscreen=0]
  config_file: /srv/ultimate-bbs-box/runtime/example.fs-uae
  working_directory: /srv/ultimate-bbs-box/runtime
  environment:
    DISPLAY: :99
  inherit_environment: [XAUTHORITY]
  stop_timeout_seconds: 5
  readiness:
    type: tcp_port
    host: 127.0.0.1
    port: 2301
    timeout_seconds: 0.2
  stream:
    type: tcp
    host: 127.0.0.1
    port: 2301
    connect_timeout_seconds: 5
```

FS-UAE receives the supplied config; M5 does not generate it. VICE machine selection is the configured executable, never inferred from a product. QEMU guest behavior and SIMH command files are likewise integration-owned.

## Process lifecycle and reconciliation

The shared process adapter requires an absolute executable, existing absolute working directory, and argv arrays. It uses `subprocess` without a shell, a new process session/group, a deliberately minimal environment, and closed inherited file descriptors. Only explicitly allowlisted environment names are inherited; configured overrides are bounded and dynamic-loader/Python injection variables are rejected. Environment values are redacted from diagnostics.

Duplicate start checks status first and returns `already_running` without spawning. Stop optionally runs a configured graceful argv hook, sends SIGTERM to the isolated process group, waits `stop_timeout_seconds`, then uses SIGKILL and a bounded wait. Cleanup closes PTY/pipe resources idempotently.

M3 persists runtime metadata within its separate supervisor state, not registry YAML, preservation objects, or living BBS data. It records PID, observed `/proc/<pid>/exe`, process start ticks, adapter, and a command digest. After a supervisor restart an adapter calls a process alive only when executable and start ticks both still match; inability to prove identity fails closed. Recovered PTY/stdio descriptors cannot be reconstructed, so stream opening fails explicitly even if process identity survives.

## Streams

- `PTYStream` is raw byte-safe, supports width/height resize, maps PTY hangup to EOF, and closes idempotently.
- `PipeStream` exposes explicitly configured stdin/stdout pipes.
- `TCPStream` uses a bounded raw TCP connection with no Telnet negotiation or implicit TLS.

`RuntimeStreamResolver` bridges an already-held M4 session to the adapter stream for the M3 instance. If stream creation fails, M4's existing cleanup releases the lifecycle session hold.

## Readiness

M3 owns the overall startup deadline and polling. M5 performs one bounded observation per poll:

- `immediate`;
- `process_alive`;
- `tcp_port` with host, port, and per-attempt timeout;
- `file_exists` with an absolute path;
- `command_exit_zero` with argv and timeout.

There is no banner/product matching, network protocol login, or unbounded probe. Readiness failure propagates through M3's existing failed/restart state machine; M3 now also stops a process created before readiness failure to avoid leaks.

## CLI and security boundary

```bash
python3 scripts/ubb-runtime.py list-adapters
python3 scripts/ubb-runtime.py --json list-adapters
python3 scripts/ubb-runtime.py --catalog PATH validate SERVICE_ID
```

The runtime CLI is diagnostic. Operators continue to use `ubb-supervisor.py` for lifecycle start/stop, avoiding conflicting control planes.

Configuration is trusted administrator/repository data but rejects unknown fields, relative executables/directories, malformed argv/environment/ports, conflicting PTY modes, and unsupported stream types. No shell snippets, passwords, terminal bytes, or environment values are journaled. Physical serial devices, Telnet negotiation, remote RPC, libvirt, disk creation, guest installation, and dynamic plugins are outside M5.

## M7.4 hardening note

Tier-1 checks exercise adapter failure/reconcile and bridge cleanup in
disposable fixtures. Real FS-UAE boot still requires operator-supplied licensed
Kickstart/AmigaOS assets and is recorded as human evidence when absent.

## Explicitly deferred

M5 does not contain product behavior. M7.1 supplies Mystic's native metadata and M7.2/M7.3 supply ABBS/AmiExpress FS-UAE metadata outside runtime core. FS-UAE's configured raw TCP serial listener is handled by the existing generic TCP readiness/stream contracts; no product branch was added. NiKom, C-Net, DOS setup, MAME/Hatari integration, physical serial hardware, remote-supervisor RPC, FTN/NNTP/SMTP/IRC, and BBS filebase publication remain outside M5.
