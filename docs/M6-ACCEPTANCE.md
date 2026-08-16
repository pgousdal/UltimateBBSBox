# M6 qualification matrix

The machine-readable inventory and readiness CLI are deterministic checks only.
They do not claim real-world protocol qualification. Each M6 service currently
has `READY_WITH_HUMAN_REQUIREMENTS` pending daemon/provider evidence.

| Layer | Deterministic state | Human evidence still required |
|---|---|---|
| DNS/NTP | config/registry intent valid | daemon activation, queries, clock sync |
| Edge/overlay | topology and policy intent valid | VPS and provider tunnel connectivity |
| SMTP | Postfix/mail routing intent valid | MX, PTR, inbound/outbound, DKIM/SPF/DMARC |
| NNTP | group/retention intent valid | daemon/client and feed interoperability |
| IRC | listener/channel intent valid | daemon/client/TLS and public ingress |
| FTN | BinkP/network/area intent valid | real peer and toss/scan interoperability |
| Offline exchange | bounded QWK/Blue Wave metadata valid | historical reader and Tier-1 BBS tests |

No real infrastructure, public DNS, mail, news, IRC, FTN, or private packets are
modified by tests.
