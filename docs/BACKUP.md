# Generic living-state backup

`ubb_backup.BackupManager` stores staged, deterministic tar payloads under a
configurable backup root separate from M1 objects and runtime state. Trusted
integration declarations register a living-state root and logical include /
exclude components. Tier-1 integrations exclude reinstallable software, cache,
logs, and temporary files by default while retaining configuration, users,
messages, file metadata, uploads, and door state where present.

The default consistency mode is `stopped`; active caller sessions cause a
clear conflict rather than silently disconnecting users. `live_best_effort` is
explicit and does not claim application consistency. Creation writes a staging
payload, hashes it, writes a manifest, and atomically publishes a backup ID.
Incomplete staging directories are never listed. Verification checks the
manifest, payload checksum, and tar member safety. Restore requires a verified
backup and first produces a `RestorePlan`; the fixture restore API restores
living files only and never overwrites immutable software.

The M8.3 action service receives a trusted callback to this manager. HTTP never
supplies a source or destination path. Viewer is denied; operator and
administrator may request backup, subject to active-session consistency.
Results are audited and become visible through M8.1 observatory metadata.

Expected deployment ownership is a dedicated `ubb-dashboard`/`ubb-supervisor`
service account with mode 0750 state directories, mode 0640 manifests/audit,
0600 admin credentials, and read-only access to M1 objects. No root dashboard,
world-writable directory, shell command, or arbitrary restore path is used.
Production restore orchestration and M8.3d end-to-end action verification
remain intentionally separate.
