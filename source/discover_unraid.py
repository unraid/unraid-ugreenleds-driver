#!/usr/bin/env python3
"""Read the official USB Creator feed on stdin and emit Unraid 7 build inputs."""

import argparse
import datetime
import json
import re
import sys
from urllib.parse import urlsplit, urlunsplit


VERSION = r"[0-9]+\.[0-9]+\.[0-9]+(?:-(?:beta|rc)\.[0-9]+)?"
DOWNLOAD = re.compile(
    rf"/dl/(?P<channel>stable|next)/(?P<version>{VERSION})/"
    rf"[0-9a-f]{{64}}/unRAIDServer-(?P=version)-x86_64\.zip"
)


def discover(feed, version=None):
    """Validate feed entries before selecting any release or returning a queue."""
    if version is not None and not re.fullmatch(VERSION, version):
        raise ValueError("Invalid requested Unraid version")
    if not isinstance(feed, dict) or not isinstance(feed.get("os_list"), list):
        raise ValueError("Feed must contain an os_list array")
    releases = {}

    def visit(entries, depth=0):
        if depth > 8:
            raise ValueError("Feed nesting exceeds the supported limit")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Feed entry must be an object")
            if "subitems" in entry:
                if "url" in entry or not isinstance(entry["subitems"], list):
                    raise ValueError("Ambiguous or invalid feed group")
                visit(entry["subitems"], depth + 1)
                continue
            url = entry.get("url")
            if not isinstance(url, str) or any(ord(c) <= 32 for c in url):
                raise ValueError("Missing or invalid release URL")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.netloc != "releases.unraid.net":
                raise ValueError("Release URL must use the official HTTPS host")
            match = DOWNLOAD.fullmatch(parsed.path)
            if match is None or parsed.fragment:
                raise ValueError("Unexpected installer URL format")
            found = match["version"]
            channel = match["channel"]
            if ("-" in found) != (channel == "next"):
                raise ValueError("Release channel does not match version")
            date = entry.get("release_date")
            if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                raise ValueError("Missing or invalid release date")
            datetime.date.fromisoformat(date)
            # Tracking queries are not part of the installer identity. The URL
            # path's hexadecimal component is NOT assumed to be a ZIP checksum.
            release = {
                "version": found,
                "channel": channel,
                "release_date": date,
                "url": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")),
            }
            if found in releases and releases[found] != release:
                raise ValueError(f"Conflicting feed entries for {found}")
            releases[found] = release

    visit(feed["os_list"])
    # Existing U7 replacement scope. Do not silently claim support for a future
    # major version or choose only the largest version across maintenance lines.
    selected = [r for r in releases.values() if r["version"].startswith("7.")]
    if version is not None:
        selected = [r for r in selected if r["version"] == version]
        if not selected:
            raise ValueError("Requested Unraid 7 version is not in the official feed")
    if not selected:
        raise ValueError("Official feed contains no supported Unraid 7 releases")
    return sorted(selected, key=lambda r: (r["release_date"], r["version"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Select one exact version advertised by the feed")
    args = parser.parse_args()
    try:
        result = discover(json.load(sys.stdin), args.version)
    except (ValueError, TypeError, RecursionError) as error:
        parser.exit(1, f"Release discovery failed: {error}\n")
    json.dump({"include": result}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
