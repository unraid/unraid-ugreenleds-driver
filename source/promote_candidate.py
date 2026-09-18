#!/usr/bin/env python3
"""Publish an immutable hardware-approval receipt from an explicit maintainer report."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from release_pipeline import RECIPE, REPOSITORY, digest, github_releases, output, run, validate_candidate

CHECKS = {"new_install", "legacy_upgrade", "settings_preserved", "reboot",
          "rollback", "disk_leds", "network_leds", "network_connectivity"}
MODELS = ("DX4600", "DX4700", "DXP2800", "DXP4800", "DXP480T", "DXP6800", "DXP8800")


def validate_report(report, manifest, manifest_hash):
    if report.get("confirm_hardware_tested") is not True:
        raise ValueError("Explicit hardware-test confirmation is required")
    for key, value in (("unraid", manifest["unraid"]), ("kernel", manifest["kernel"]),
                       ("manifest_sha256", manifest_hash)):
        if report.get(key) != value:
            raise ValueError(f"Report does not identify this exact candidate: {key}")
    evidence = report.get("evidence_url", "")
    url = urlsplit(evidence)
    if url.scheme != "https" or url.netloc != "github.com" or not re.fullmatch(
            rf"/{re.escape(REPOSITORY)}/issues/[1-9][0-9]*", url.path) or url.query or url.fragment:
        raise ValueError("A redacted test report in this repository's issues is required")
    results = report.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("At least one physical model test result is required")
    models = []
    for result in results:
        model = result.get("system_product_name", "")
        if not isinstance(model, str) or not model.startswith(MODELS) or not re.fullmatch(r"[A-Za-z0-9 ._+-]{1,80}", model):
            raise ValueError("Unsupported or invalid system product name")
        if model in models:
            raise ValueError("Duplicate model result")
        checks = result.get("checks", {})
        if set(checks) != CHECKS:
            raise ValueError("Every installation, LED, network, and recovery check is required")
        # The original DXP480T monitor has static LEDs only, not disk/network
        # activity. Record that explicitly instead of claiming nonexistent tests.
        expected = {check: "pass" for check in CHECKS}
        if model.startswith("DXP480T"):
            expected["disk_leds"] = expected["network_leds"] = "not-applicable-static-model"
            if result.get("static_leds") != "pass":
                raise ValueError("DXP480T static LED verification is required")
        if checks != expected:
            raise ValueError("Failed or incomplete checks prohibit stable approval")
        models.append(model)
    return models


def approve(directory, report, actor):
    manifest, receipt = validate_candidate(directory)
    manifest_hash = digest(receipt)
    models = validate_report(report, manifest, manifest_hash)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", actor):
        raise ValueError("A GitHub approver identity is required")
    issue = report["evidence_url"].rsplit("/", 1)[-1]
    if output("gh", "api", f"repos/{REPOSITORY}/issues/{issue}", "--jq", ".html_url") != report["evidence_url"]:
        raise ValueError("Could not verify the evidence issue exists")
    approval = {
        "schema": 1, "recipe": RECIPE, "status": "approved",
        "unraid": manifest["unraid"], "kernel": manifest["kernel"],
        "manifest_sha256": manifest_hash, "system_product_names": models,
        "evidence_url": report["evidence_url"], "results": report["results"],
        "approved_by": actor,
        "approved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "basis": "Explicit maintainer attestation; CI does not perform physical hardware tests",
    }
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / ("approved-" + receipt.name)
        releases = [r for r in github_releases() if r["tag_name"] == manifest["kernel"]]
        if len(releases) != 1 or releases[0]["draft"]:
            raise ValueError("Approval requires an existing published kernel candidate")
        if any(a["name"] == path.name for a in releases[0]["assets"]):
            run("gh", "release", "download", manifest["kernel"], "--repo", REPOSITORY,
                "--pattern", path.name, "--dir", temporary)
            existing = json.loads(path.read_text())
            # Preserve the original approver and timestamp on an identical
            # attestation retry, including after a failed release edit.
            identity = set(approval) - {"approved_by", "approved_at"}
            if set(existing) != set(approval) or any(existing[k] != approval[k] for k in identity):
                raise ValueError("Refusing to overwrite a different hardware approval")
        else:
            path.write_text(json.dumps(approval, indent=2) + "\n")
            run("gh", "release", "upload", manifest["kernel"], path, "--repo", REPOSITORY)
    # Other OS versions in this kernel release can remain unapproved. The
    # installer must require their own exact approval receipt and model match.
    run("gh", "release", "edit", manifest["kernel"], "--repo", REPOSITORY, "--prerelease=false",
        "--notes", "Only OS versions and exact hardware models with approved-unraid-*.json receipts are approved. Other assets remain experimental candidates. See each approval's evidence link.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    approve(args.directory, json.loads(os.environ["HARDWARE_REPORT"]), os.environ["GITHUB_ACTOR"])


if __name__ == "__main__":
    main()
