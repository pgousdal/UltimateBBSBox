# Session router, exposure, and access

M4 turns a route request into an authorized, lifecycle-held byte stream. It has no mandatory login, account database, or shared user identity. Mystic, a MUD, UNIX/VMS, IRC, and every other destination continue to own their usernames, passwords, security levels, and login presentation.

## Exposure is authorization

Direct routes require `exposure.main_menu: true`, `access.direct_allowed: true` (the default), and no `admin_only` flag. The target ID itself grants nothing. Thus this request is denied:

```
caller -> UBB -> unix-v7-shell
DENIED: main_menu is false and direct access is false
```

Via-service routes require the origin ID in the target's `via_bbs` list. Router-level opening also requires an active or handing-off parent session whose target equals that origin. A caller cannot forge `origin_service: mystic-main` to bypass policy. M2 already validates that `via_bbs` entries name BBS services.

`admin_only` services are denied to caller routes in M4 because no generic administrative assertion exists. BBS security-level and user-group policy remains destination-owned; M4 invents no account synchronization.

Representative paths:

```
A. caller -> UBB -> Mystic -> Mystic login

B. caller -> Mystic session -> UNIX V7 child session -> UNIX login
          -> child closes -> return to Mystic session

C. caller -> UBB -> unix-v7-shell
          -> denied (via-BBS only)

D. caller -> UBB -> directly exposed MUD -> MUD-owned login
```

## Route and session models

`RouteRequest` carries target service, `direct` or `via_service` type, optional origin, terminal capabilities, and opaque non-secret caller metadata. M2 resolves the endpoint and optional integration. No username is required.

The transient `Session` records:

- opaque session ID and creation time;
- target and optional origin service;
- direct/via route type;
- terminal capabilities and opaque caller metadata;
- M3 lifecycle session-hold ID;
- normalized endpoint metadata;
- state and termination reason;
- optional parent, handoff mode, and return-to-origin intent.

Session and service lifecycle state are independent. The validated session graph is:

```
created -> authorizing -> acquiring -> connecting -> active
                                                   -> handing_off -> active
active/handing_off -> closing -> closed
any setup/active stage -> failed -> closing/closed
```

Opening authorizes before acquiring anything, then calls M3 `acquire_session`, then connects. Connection failure closes a partial stream and releases the M3 hold. Close and EOF release that hold exactly once. Closed sessions remain available as in-process diagnostics, but streams and active sessions are not persisted.

## Terminal capabilities

`TerminalCapabilities` carries arbitrary encoding/display strings, width, height, optional emulated baud, binary-safe capability, newline mode, and an extension mapping. It represents CP437/ANSI 80×25, PETSCII 40×25, ATASCII, Avatar, Viewdata, UTF-8 ANSI, raw terminals, and obscure future types without a closed enum.

M4 preserves this metadata but does no encoding conversion or terminal emulation. Telnet option negotiation is also deferred; TCP is raw bytes.

## Streams and transports

The minimal `ByteStream` contract is `read(size)`, `write(bytes)`, and idempotent `close()`. A `SessionHandle` applies router state and cleanup rules around that stream.

Built in:

- `TCPConnector`: `socket.create_connection` with endpoint `connect_timeout_seconds` or a router default, followed by raw blocking byte I/O;
- `MemoryStream`/`MemoryConnector`: deterministic fake transport for tests and integrations.

EOF (`read()` returning empty bytes) closes the session with `endpoint_eof`. Explicit close racing EOF is safe because teardown is guarded per session and release is marked exactly once. TCP half-close is treated as endpoint EOF for the routed session; M4 does not attempt prolonged half-duplex operation.

SSH, physical serial, and remote-supervisor streams raise `UnsupportedTransportError` unless a caller injects a product-neutral connector. M5 adds an optional runtime stream resolver for integration-backed PTY, stdio, and raw TCP streams. M4 does not fake connectivity, source credentials, or implement remote RPC.

## Handoff and return

`handoff(parent_session_id, target_service_id, return_to_origin=True)` transitions the active parent to `handing_off`, authorizes the child using the parent's target as the origin, and opens a child session. Only one handoff may be outstanding from a parent.

`return_to_origin` restores a still-open parent to active when the child closes. `replace` closes the parent once the child is active. If a parent closes while its child is active, child teardown does not resurrect it. This is the control-plane model only: physically suspending and resuming a Mystic/ABBS stream belongs to a later product integration.

## Concurrency and journal

The router uses a global index lock and a reentrant lock per session. Open/close state changes serialize, double close is idempotent, lifecycle release has an explicit once flag, two handoffs from one parent are rejected, and blocking reads do not hold the session lock so another thread can close the stream.

`<router-state>/events.jsonl` records timestamp, session/target/origin IDs, event type, state transition, endpoint ID, controlled termination reason, and exception class. Its fixed allowlist excludes caller metadata and terminal data. It never stores passwords, content, private messages, or a transcript. Caller-provided close reasons are reduced to a controlled value before journaling.

## API and CLI

The reusable package exposes `RoutePolicy`, `Router`, `RouteRequest`, `TerminalCapabilities`, `SessionHandle`, connectors, and typed errors.

```bash
python3 scripts/ubb-router.py services
python3 scripts/ubb-router.py services --direct
python3 scripts/ubb-router.py authorize mystic-main
python3 scripts/ubb-router.py authorize unix-v7-shell --via mystic-main
python3 scripts/ubb-router.py --json authorize mystic-main
```

The CLI is a read-only policy/development tool. `authorize --via` confirms that a declared origin is allowed; it does not manufacture the active origin session required by `Router.open_session`. Active streams remain within the embedding process because M4 adds no unauthenticated control API or IPC daemon.

## Explicitly deferred

M5 now supplies generic native, FS-UAE, VICE, QEMU, SIMH, PTY, stdio, and TCP runtime plumbing. Later work still owns DOS/MAME/Hatari support, SSH credentials, physical serial, remote-supervisor RPC, actual Mystic/ABBS door handoff, terminal negotiation/emulation, BBS user/security synchronization, central identity, FTN/NNTP/SMTP/UUCP/IRC services, web UI, and a polished ANSI menu. M4 remains the generic authorized routing/session contract those layers call.
