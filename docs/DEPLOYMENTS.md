# Preservation-first deployment assets

M8.4c makes preservation-first a repository-wide invariant: third-party
software enters through M1 quarantine and immutable preservation before any
installer or runtime consumes it. OS package-manager operations (`apt`, `dnf`,
`apk`) remain valid for base host dependencies; they are not museum payloads.

The four layers are preserved artifact, derived artifact, deployment asset, and
living state. `DeploymentManager` materializes verified artifacts into isolated
per-service trees and records a manifest containing artifact identity, SHA-256,
lineage references, materialization mode, and state scope. Mutable state is
`per_deployment` by default; shared state requires an explicit stable ID.

Use `scripts/ubb-deployment.py show|provenance|verify` to inspect the provenance
chain. Deployment never implies redistribution or BBS filebase publication.
Recovery is repository/configuration plus M1 plus living-state backups, followed
by reconstruction of deployment assets. Future doors can use separate per-BBS
asset trees without sharing mutable state implicitly.

The integration guard covers wget, curl, get_url, direct Python HTTP acquisition,
and mutable git clone patterns in product paths while permitting M1, package
manager tasks, test fixtures, and metadata-only GitHub discovery.
Host-installed DNS/NTP daemons are ordinary OS package-manager dependencies, not
museum payloads. Any non-package-managed network software must still follow the
M1 preservation-first acquisition and deployment chain.
