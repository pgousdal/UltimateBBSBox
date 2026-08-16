# Contributing

UBB is product-neutral infrastructure for preservation, BBS runtimes, network
services, and operator observability. Keep the preservation-first invariant:
third-party software is acquired through M1 or an explicitly permitted host
package manager. Never add direct download/install paths (`curl`, `wget`,
`get_url`, mutable clones) to integration or deployment code.

Keep core models generic; product-specific behavior belongs in integrations and
adapters. Be honest about qualification: use `HUMAN_REQUIRED`, `UNKNOWN`, or
`UNSUPPORTED` instead of turning fixture results into real-world PASS claims.
Do not add secrets, private packets, ROMs, registrations, or real public-network
changes to tests.

Before submitting changes, run:

    make check
    python3 -m compileall -q scripts tests
    git diff --check

CI runs `make check-strict`, which requires Ansible tooling. If local tooling is
unavailable, `make check` reports `PASS WITH SKIPS`; do not conceal the skip.
Add focused deterministic tests and update milestone/acceptance documentation
when behavior or scope changes. Prefer small incremental commits, do not rewrite
history, and do not push without explicit authorization.

The repository-owned source and documentation are MIT-licensed. Third-party
products, tools, ROMs, preserved artifacts, and their rights metadata remain
separate and are not relicensed by contributions here.
