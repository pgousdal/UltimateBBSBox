# ABBS/Amiga reference integration

This production integration models ABBS as a family and initially selects **ABBS “For All” 3.2**, public serial `#999` (`ABBS320_999.lha`). The authentic distribution is maintained by Kåre Johansen on Aminet; its internal documentation credits GIH/JEO. The reference bytes are 751,581 bytes: SHA-256 `5e9fd4cbf871a2bbd4579a3f9b35a0cd2187676cab8886b16adbfe8b038380e4`, SHA-1 `742354e4a4e68c28a5ec80622d5b844aab43aeca`, MD5 `ac5c8633bb33f936ab38535d0c994178`.

The maintainer offers “ABBS for all” free with serial 999, but no explicit redistribution licence was found. UBB therefore records `freeware`, allows local preservation/installation, and denies redistribution and BBS publication. Private registered releases may be imported through M1 as `licensed_private`; keys and private binaries never enter Git.

## Workflow

1. `ubb-integration.py acquire abbs-amiga` downloads from `https://aminet.net/comm/bbs/ABBS320_999.lha` through M1 quarantine and immutable storage. An operator may instead use `--file` with authentic supplied bytes.
2. Verification checks the known hashes. Preparation extracts the LHA and preserves a deterministic derived tar with parent lineage; neither source is mutated.
3. Supply a licensed Kickstart ROM and an AmigaOS 3.x base HDF outside Git. Install the prepared files in AmigaOS, add `ABBS:` assignment and required libraries, run `ConfigNode`, select nullmodem operation on `serial.device`, then run `Config BBS`.
4. Record `abbs_installed`, `confignode_completed`, `config_bbs_completed`, and `golden_image_qualified`. A secret-free golden HDF is copied once to a mutable working HDF. Subsequent convergence never overwrites it.
5. FS-UAE uses `serial_port = tcp://127.0.0.1:6402/wait`. M5 starts FS-UAE; M3 waits for that serial listener; M4 routes raw bytes. This is raw TCP, not Telnet. ABBS owns user login.

The conservative configurable reference profile is A1200, 68020/AGA, 2 MiB Chip RAM, 8 MiB Fast RAM, Kickstart 3.1 and AmigaOS 3.x. This is an integration baseline, not a claim of ABBS's minimum requirements. The selected package is tagged OS3; uncertainties remain recorded rather than guessed. Terminal qualification uses extensible `amiga-8bit`, ANSI, 80x25 metadata; the exact configured ABBS charset must be observed by the operator.

## State and qualification

The preserved LHA and derived install tree are immutable. The installation workspace is reproducible. The golden HDF is a clean base. The working HDF contains mutable configuration, users, messages, file headers, uploads, logs/statistics, queues, door state, Hold/Tmp data, and generated indexes. Reinstalling never replaces that working image.

Without user-licensed ROM/OS assets, a real FS-UAE boot, ABBS startup, terminal/login/menu observation, stop/restart, and living-state test are `HUMAN_REQUIRED`, never synthetic `PASS`. Process existence alone is insufficient: readiness is the configured guest serial TCP listener.

The generic asset resolver, FS-UAE profile writer, golden/working image handling, raw serial-over-TCP path, and qualification vocabulary are reusable by AmiExpress M7.3; no ABBS branch exists in M1–M5.
