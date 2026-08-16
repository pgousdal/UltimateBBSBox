# Canonical Amiga BBS profiles

Profiles are machine/runtime declarations, not product integrations. They contain no ABBS or AmiExpress knowledge.

| ID | Historical baseline | UBB canonical BBS configuration | Private assets |
| --- | --- | --- | --- |
| `amiga-a500-k13` | Amiga 500, 68000, OCS, Kickstart/Workbench 1.3 | 1 MiB Chip, 2 MiB Fast, 20 MiB hard-disk workspace | Kickstart 1.3 ROM and Workbench/AmigaOS 1.3 image |
| `amiga-a1200-os31` | Amiga 1200, 68020, AGA, Kickstart/Workbench 3.1 | 2 MiB Chip, 8 MiB Fast, 100 MiB hard-disk workspace | Kickstart 3.1 ROM and AmigaOS/Workbench 3.1 image |

The expanded memory and hard-disk values are practical UBB reference configurations, not claims that every historical BBS ran on stock hardware. Profiles validate supported/default declarations and reject unknown IDs. ROM and OS files are resolved by explicit operator paths and never downloaded or stored in Git.

ABBS 3.2 currently declares only `amiga-a1200-os31`, based on its OS3 distribution and the M7.2 evidence. AmiExpress 5.6.1 also declares only `amiga-a1200-os31`; its bundled historical documentation mentions Kickstart 2.0+, while the maintained release is qualified against the canonical 3.1 profile. A future release may declare A500/Kickstart 1.3 only after evidence supports it.
