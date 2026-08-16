#!/usr/bin/env python3
"""Read-only diagnostics for the UBB public edge/secure-overlay model."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ubb_edge import EdgeConfig, Ingress, PrivateSite, PublicIdentity, Route

def sample() -> EdgeConfig:
    return EdgeConfig(
        sites=(PrivateSite("home-main", "home-1", ("192.168.50.0/24",), ("mystic-main", "abbs-main"), "home.ubb.internal"),),
        public_identities=(PublicIdentity("bbs.example.invalid", "edge-1"),),
        ingress=(Ingress("bbs-telnet", "tcp", 2323, "mystic-main", 23, public_address="203.0.113.10"),),
        routes=(Route("edge-1", "192.168.50.0/24", approved=False),),
        secret_refs=("/etc/ultimate-bbs-box/secrets/overlay.key",),
    )

def main() -> int:
    parser=argparse.ArgumentParser(description="UBB edge and secure-overlay diagnostics")
    parser.add_argument("command", choices=("status","nodes","routes","ingress","public-identities","validate"))
    parser.add_argument("--json", action="store_true")
    args=parser.parse_args(); config=sample(); data=config.to_dict()
    if args.command == "nodes": data={"edge_node": data["edge_node"], "sites": data["sites"]}
    elif args.command == "routes": data={"routes": data["routes"]}
    elif args.command == "ingress": data={"ingress": data["ingress"]}
    elif args.command == "public-identities": data={"public_identities": data["public_identities"]}
    elif args.command == "validate": data={"valid": True, "provider": config.provider, "support_level": config.support_level}
    if args.json: print(json.dumps(data, sort_keys=True, separators=(",", ":")))
    else:
        if args.command == "validate": print("valid provider=%s support=%s" % (config.provider, config.support_level))
        else: print(json.dumps(data, indent=2, sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
