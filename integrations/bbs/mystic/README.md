# Mystic/Linux reference integration

This is the first production museum integration. It is intentionally separate from catalog declarations, preservation objects, supervisor state, and Mystic's living data.

The pre-M7 configuration requested Mystic `1.12.A3` and `linux-x64`, but the official directory contains A3 only as a 32-bit RAR and the constructed tar URL returns 404. M7.1 therefore selects the latest stable versioned Linux x64 distribution listed by upstream: Mystic `1.12.A48`, original filename `mys112a48_l64.rar`. A real M1 smoke acquisition on 2026-08-16 established SHA-256 `fb427b57d9627ef93008c561df807991bdd288b4a1fc1757dfb5bb5434f286a3`; future canonical acquisition enforces it. The operator acquires it through M1; the integration never downloads into an install directory. Upstream did not publish that checksum beside the directory listing, so it is an observed preservation identity rather than a publisher-signed checksum.

Rights are conservative: local preservation and installation are allowed for the owner workflow, but original redistribution and BBS-filebase publication are false. The included description calls Mystic free software, but its documentation also states copyright/all rights reserved and no explicit redistribution grant was found. The public download URL is not treated as a redistribution license. See `acquisition.json` for the recorded decision and evidence.

## Workflow

```text
python3 scripts/ubb-archive.py init --root /srv/ultimate-bbs-box/archive
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive acquire mystic-linux
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive verify mystic-linux
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive --install-root /opt/mystic install mystic-linux
sudo -u bbs /opt/mystic/software/current/mis -cfg
python3 scripts/ubb-integration.py --install-root /opt/mystic configure mystic-linux \
  --evidence version_screen --evidence configured_message_base
python3 scripts/ubb-integration.py --archive-root /srv/ultimate-bbs-box/archive --install-root /opt/mystic qualify mystic-linux
```

Acquisition can use `--file PATH` for an operator-downloaded copy while retaining the authoritative source URL as provenance. That import still passes through M1 quarantine and object publication. A clean install refuses an unknown, tampered, incorrectly classified, or locally non-installable artifact.

## Assisted configuration and evidence

`mis -cfg` remains interactive. The workflow is therefore `assisted`, not fully automated. Record a version-screen observation and evidence that a message base was configured, then rerun `configure`. Repeating install is safe: the same digest reuses its release directory and never resets live state.

The qualification report uses `PASS`, `FAIL`, `HUMAN_REQUIRED`, and `SKIP`, and is written to `qualification/latest.json`. Login/menu presentation remains `HUMAN_REQUIRED`; a running process alone is not READY.

## Filesystem separation

```text
/opt/mystic/
  software/releases/<sha256>/   verified extracted software
  software/current -> releases/<sha256>
  live/data/                    users, indexes and core data
  live/text/                    operator-customized menus and text
  live/logs/                    mutable logs
  live/doors/                   installed door/game state
  live/msgs,files,echomail/     message/file bases and network queues
  live/localqwk,semaphore/      transfer/work state
  live/themes/                  customized themes
  live/config/                  root Mystic .dat/.ini configuration files
  qualification/latest.json    evidence/status, never terminal content
```

The release tree links those mutable paths to `live/`. Installation fills missing seed files but never replaces an existing live file. User records, messages, filebase metadata, generated indexes, logs, queues, customized displays, doors/game state, and configuration are therefore outside digest-named software. Backup policy must cover all of `live/` and qualification evidence. Preserved objects remain in M1 and are not backup substitutes for living state.

The official distribution is RAR and contains Mystic's own installer payload. Installation uses `/usr/bin/unrar`, then runs `install auto` into a new digest-specific release with argument vectors and bounded timeouts; the Ansible host-convergence role installs `unrar`. It never uses the upstream installer's overwrite mode. No shell snippet or downloader is involved.

M3 owns start/stop/restart and permits `on_demand` or `always_on` as a manifest choice without reinstalling. M5's native adapter launches `mis`; M4 routes raw TCP to port 6400. Mystic owns caller authentication. The legacy Ansible role still converges packages, account, directories and permissions; on clean install it now requires an M1 object digest, and its systemd unit is migration-only.
