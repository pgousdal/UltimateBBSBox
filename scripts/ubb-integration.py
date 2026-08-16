#!/usr/bin/env python3
"""Operator CLI for trusted museum integrations."""
from __future__ import annotations

import argparse
import inspect
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ubb_integrations import IntegrationError, IntegrationRegistry, readiness_summary  # noqa: E402


def parser():
    result = argparse.ArgumentParser(description="Ultimate BBS Box museum integrations")
    result.add_argument("--archive-root", default="/srv/ultimate-bbs-box/archive")
    result.add_argument("--install-root", default="/opt/mystic")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    for command in ("releases", "check-updates", "deployment-status"):
        item = sub.add_parser(command); item.add_argument("integration_id")
    promote = sub.add_parser("promote"); promote.add_argument("integration_id"); promote.add_argument("--release", required=True); promote.add_argument("--approve-human", action="store_true")
    rollback = sub.add_parser("rollback"); rollback.add_argument("integration_id")
    readiness = sub.add_parser("readiness"); readiness.add_argument("integration_id"); readiness.add_argument("--artifact-id"); readiness.add_argument("--channel", choices=("stable", "development"))
    for command in ("verify", "install", "configure", "qualify", "status"):
        item = sub.add_parser(command); item.add_argument("integration_id")
        if command in ("verify", "install", "qualify", "status"):
            item.add_argument("--artifact-id")
        if command in ("configure", "qualify"):
            item.add_argument("--evidence", action="append", default=[])
        if command == "install":
            item.add_argument("--evidence", action="append", default=[])
            item.add_argument("--asset", action="append", default=[], metavar="NAME=PATH")
    acquire = sub.add_parser("acquire"); acquire.add_argument("integration_id")
    acquire.add_argument("--file"); acquire.add_argument("--source-url"); acquire.add_argument("--artifact-id"); acquire.add_argument("--release"); acquire.add_argument("--channel", choices=("stable", "development"))
    return result


def main(argv=None):
    args = parser().parse_args(argv); registry = IntegrationRegistry.defaults()
    try:
        if args.command == "list":
            print(json.dumps([{"id": x.id, "runtime": x.runtime, "automation_level": x.automation_level} for x in registry.list()], indent=2)); return 0
        integration = registry.get(args.integration_id)
        artifact_id = getattr(args, "artifact_id", None) or integration.artifact_id
        if args.command == "acquire":
            kwargs={"local_file":args.file,"source_url":args.source_url,"artifact_id":args.artifact_id}
            if "release" in inspect.signature(integration.acquire).parameters: kwargs["release"]=args.release or (getattr(integration, "current_release_key", None) if args.channel == "development" else None)
            value = integration.acquire(args.archive_root, **kwargs)
        elif args.command == "verify": value = integration.verify_artifacts(args.archive_root, artifact_id)
        elif args.command == "releases": value = [{"key": item.key, "artifact_id": item.artifact_id, "channel": item.channel, "purpose": item.purpose, "source_commit": item.source_commit, "sha256": item.sha256} for item in integration.releases_by_channel()]
        elif args.command == "check-updates": value = integration.check_updates()
        elif args.command == "deployment-status": value = integration.deployment_status(args.install_root)
        elif args.command == "readiness":
            if args.channel and hasattr(integration, "releases_by_channel"):
                choices = integration.releases_by_channel(args.channel)
                if len(choices) != 1: raise IntegrationError("readiness channel must resolve to exactly one release")
                artifact_id = choices[0].artifact_id
            evidence_path = pathlib.Path(args.install_root) / "qualification" / f"{artifact_id}.json"
            if not evidence_path.is_file():
                evidence_path = pathlib.Path(args.install_root) / "qualification" / "latest.json"
            if evidence_path.is_file():
                evidence = json.loads(evidence_path.read_text(encoding="utf-8")).get("results", [])
            else:
                evidence = [{"status": "BLOCKED", "detail": "no qualification evidence recorded"}]
            value = readiness_summary(evidence, integration=integration.id, release=artifact_id)
        elif args.command == "promote": value = integration.promote(args.install_root, args.release, approve_human=args.approve_human)
        elif args.command == "rollback": value = integration.rollback(args.install_root)
        elif args.command == "install":
            assets={}
            for item in args.asset:
                if "=" not in item: raise IntegrationError("--asset must be NAME=PATH")
                name,path=item.split("=",1); assets[name]=path
            kwargs={}
            signature=inspect.signature(integration.install).parameters
            if "assets" in signature: kwargs["assets"]=assets
            if "evidence" in signature: kwargs["evidence"]=args.evidence
            value = integration.install(args.archive_root, artifact_id, args.install_root, **kwargs).to_dict()
        elif args.command == "configure": value = integration.configure(args.install_root, args.evidence).to_dict()
        elif args.command == "qualify": value = [x.to_dict() for x in integration.qualify(args.archive_root, artifact_id, args.install_root, evidence=args.evidence)]
        else:
            value = {"integration": integration.id, "artifact_id": artifact_id,
                     "installed": (pathlib.Path(args.install_root) / "software/current/.ubb-install.json").is_file(),
                     "automation_level": integration.automation_level}
        print(json.dumps(value, indent=2, sort_keys=True)); return 0
    except (IntegrationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
