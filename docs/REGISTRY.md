# Service and endpoint registry

M2 is Ultimate BBS Box's read-only metadata/control plane. It answers what services are cataloged, where their declared endpoints are, and which integration manifest describes them. It does not assert or discover runtime state.

## Source of truth

Production manifests are committed YAML files:

```
catalog/services/<service-id>.yml
catalog/endpoints/<endpoint-id>.yml
catalog/integrations/<integration-id>.yml
```

`catalog/examples/` remains the educational M0 example set and is not loaded by the production registry API. `scripts/ubb-schema.py` validates both production and example manifests together, including cross-references. The registry has no database or authoritative cache; every load safely parses, validates, sorts, and indexes the YAML source.

IDs are unique within each kind. Filenames aid humans but IDs and references define identity. A malformed manifest, unsupported schema version, duplicate ID, missing endpoint/integration, mismatched integration target, or invalid `via_bbs` reference fails the whole load loudly.

## Service model

A service describes a caller-visible type such as `bbs`, `door`, `mud_world`, `talker`, `interactive_fiction`, `shell`, `irc`, `nntp`, `gopher`, or `other`. It includes a title and may include description, family, version, platform, terminal data, and tags. It references exactly one endpoint and optionally one integration.

Lifecycle, maintenance, sharing, access, and exposure values are retained as declarations. The registry can query them but never acts on them. There is deliberately no M2 online/offline state. Catalog presence does not imply preserved media, an integration, qualification, enablement, installation, reachability, or a running process.

## Endpoint model

Endpoints describe connection metadata without making a connection:

- `local_process`: an argument-vector declaration;
- `tcp`: host, port, and protocol;
- `ssh`: host and optional port/protocol metadata;
- `serial`: device and baud rate;
- `remote_supervisor` (and the M0-compatible `supervisor` spelling): host and remote service ID.

Normalized results map legacy `supervisor` to `remote_supervisor` and add `location: local|remote`. Loopback TCP, local processes, and serial devices are local; SSH and supervisor endpoints are remote. This classification is metadata, not an availability check or remote RPC.

## Integration references

An integration targets a known service and declares automation level, runtime, installation recipe metadata, and qualification checks. A service's optional `integration` field must name an integration targeting that same service. The registry validates this chain but runs no installation step and does not treat a list of qualification checks as evidence that they passed.

Product knowledge is allowed inside individual integration manifests and future implementation code. Registry loading and querying branch only on generic kinds, service/endpoint types, references, exposure, and runtime values. Future BBS, door, MUD, and interactive-fiction integrations should be added and qualified individually alongside only the service and endpoint manifests they need.

## Exposure queries

Exposure is declarative input for the future M4 router. M2 supports listing services visible or hidden in the main menu, services reachable through a named BBS, and BBS-only declarations (not in the main menu and with at least one `via_bbs` reference). No menu is generated and no policy is enforced.

## API and CLI

Python callers import `load_registry` from `ubb_registry`. A `Registry` provides sorted mappings, typed lookup methods, `list_services(...)`, and `resolve(service_id)`. Returned resolution data is the service → normalized endpoint → optional integration declaration chain.

```bash
python3 scripts/ubb-registry.py validate
python3 scripts/ubb-registry.py list
python3 scripts/ubb-registry.py list --type bbs
python3 scripts/ubb-registry.py list --main-menu
python3 scripts/ubb-registry.py list --hidden
python3 scripts/ubb-registry.py list --bbs-only
python3 scripts/ubb-registry.py list --via-bbs mystic-main
python3 scripts/ubb-registry.py endpoint unix-v7-remote
python3 scripts/ubb-registry.py integration mystic-linux
python3 scripts/ubb-registry.py resolve mystic-main
python3 scripts/ubb-registry.py graph mystic-main
python3 scripts/ubb-registry.py --json resolve unix-v7-shell
```

`--catalog PATH` selects another source root, which is useful for tests. Output order is stable by ID. Expected registry errors go to stderr and exit with status 2. The implementation performs no shell execution and no network I/O; manifests must never contain passwords, private keys, registration keys, or credential-bearing targets.

## Explicitly deferred

M3 and later own process start/stop, on-demand activation, always-on supervision, readiness, idle shutdown, restart, scheduled wake, multiuser allocation, terminal handoff, menu generation, access enforcement, routing, emulator/runtime adapters, remote-supervisor RPC, publication, and network core services. M2 merely stores, validates, resolves, and queries declarations for those future layers.
