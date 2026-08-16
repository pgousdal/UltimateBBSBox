# ADR 0004: Lifecycle and scheduled wake are independent

Status: Accepted

Services may be `on_demand` or `always_on`. Scheduled maintenance is independent: an on-demand BBS may wake periodically for FTN/QWK/UUCP/network exchange and return to sleep, while an always-on service runs the job in-place.
