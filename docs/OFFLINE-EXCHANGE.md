# M6.7 QWK / Blue Wave offline exchange

M6.7 provides bounded, product-neutral packet infrastructure for QWK and Blue
Wave. The formats are independent providers; QWKE is explicitly deferred until
authoritative tooling/interoperability evidence exists. UBB does not implement a
full offline reader.

`user_offline_mail` packets are tied to an opaque BBS-local service/user
reference and may only be delivered through that BBS's authorization path.
`system_exchange` is service-to-service and independently scheduled. These
identities are never central UBB caller accounts. Packet manifests track state,
format, direction, checksum, size, message count, origin and checkpoint without
message content.

QWK components such as CONTROL.DAT, MESSAGES.DAT, conference numbers, and reply
packets are represented by format/mapping metadata. Blue Wave has separate
provider identity and area/reply semantics. Legacy encodings (CP437/CP850/etc),
newline rules, 8.3 filenames, bounded counts/sizes, and allow-listed ZIP
compression are explicit; UTF-8 is never silently assumed.

Incoming archives are staged and reject absolute paths, `..`, symlink/hardlink
escapes, excessive files, or excessive uncompressed size. Checkpoints advance
only after successful generation/import; stable format-native identities and
adapter checkpoints prevent duplicate replies and exchange loops. Packets are
mutable transient data, not M1 museum artifacts. Retention and backup must
protect pending replies without indefinitely archiving private delivered mail.

M3 remains the scheduler for system exchange. Tier-1 historical QWK/Blue Wave
capability and independent-reader interoperability remain `HUMAN_REQUIRED`.
Use `python3 scripts/ubb-exchange.py {status,formats,mappings,packets,adapters,validate}`
for privacy-safe diagnostics.
