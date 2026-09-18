#!/usr/bin/env python3
"""Discover, build, and publish immutable UGREEN candidates. Never promote stable."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from discover_unraid import discover
from verify_kernel_config import parse_config

REPOSITORY = "unraid/unraid-ugreenleds-driver"
FEED = "https://releases.unraid.net/usb-creator"
RECIPE = 1
DRIVER_COMMIT = "992fc6dcb5da4cfc9aa25561eff2f584c06f586d"
DRIVER_SHA256 = "a3e47c0fac4a3a099b2b83e366a436565ce2c77f7b05fd10c25ab1355d785c19"
I2C_SHA256 = "1f899e43603184fac32f34d72498fc737952dbc9c97a8dd9467fadfdf4600cf9"
HERE = Path(__file__).resolve().parent


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def output(*args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url, path, expected=None):
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS downloads are allowed")
    if path.exists():
        raise ValueError(f"Download destination already exists: {path.name}")
    run("curl", "--fail", "--location", "--retry", "3", "--proto", "=https",
        "--proto-redir", "=https", "--connect-timeout", "30", "--max-time", "1800",
        "--output", path, url)
    actual = digest(path)
    if expected is not None and actual != expected:
        raise ValueError(f"Checksum mismatch: {path.name}")
    return actual


def receipts_name(version):
    return f"unraid-{version}-r{RECIPE}.json"


def github_releases():
    pages = json.loads(output("gh", "api", "--paginate", "--slurp",
                              f"repos/{REPOSITORY}/releases"))
    return [release for page in pages for release in page]


def queue(feed, releases, version=None):
    candidates = discover(feed, version)
    complete = [
        {asset["name"] for asset in release["assets"]} for release in releases
        if not release["draft"] and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-Unraid", release["tag_name"])
    ]
    # Receipts are uploaded last by the publication job. Drafts and partial
    # uploads do not establish completion. Exact-version requests also obey it.
    result = []
    for item in candidates:
        prefix = f"unraid-{item['version']}-r{RECIPE}--"
        expected = [prefix + name for name in ("stock.config", "config-validation.json", "led-layout.json",
                                               "compatibility.txt", "userspace-compatibility.txt")]
        def finished(names):
            packages_present = all(any(name.startswith(prefix + role) and name.endswith(".txz")
                                       for name in names)
                                   for role in ("ugreen_leds-", "ugreenleds-driver-", "i2c-tools-"))
            return receipts_name(item["version"]) in names and packages_present and set(expected) <= names
        if not any(finished(names) for names in complete):
            result.append(item)
    return result


def version_number(value):
    number = int(value)
    return f"{number // 10000}.{number // 100 % 100}.{number % 100}"


def extract_payloads(archive, inputs):
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        for name in ("bzroot", "bzmodules"):
            for member in (name, name + ".sha256"):
                if names.count(member) != 1:
                    raise ValueError(f"Installer must contain exactly one {member}")
            checksum = source.read(name + ".sha256").decode().split()[0]
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError(f"Invalid installer checksum: {name}")
            with source.open(name) as stream, (inputs / name).open("xb") as dest:
                shutil.copyfileobj(stream, dest)
            if digest(inputs / name) != checksum:
                raise ValueError(f"Installer payload checksum mismatch: {name}")


def build(release, work, commit):
    # Revalidate the externally supplied job input before any download or path use.
    release = discover({"os_list": [release]})[0]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full repository commit is required")
    work.mkdir(parents=True, exist_ok=False)
    inputs, assets = work / "inputs", work / "assets"
    inputs.mkdir()
    assets.mkdir()
    zip_hash = fetch(release["url"], inputs / "unraid.zip")
    extract_payloads(inputs / "unraid.zip", inputs)
    runtime = work / "runtime"
    run("unmkinitramfs", inputs / "bzroot", runtime)
    versions = list(runtime.glob("**/etc/unraid-version"))
    if len(versions) != 1 or f'version="{release["version"]}"' not in versions[0].read_text().splitlines():
        raise ValueError("Installer version does not match release feed")
    root = versions[0].parent.parent
    kernels = [p.name for p in (root / "lib/modules").iterdir() if p.is_dir()]
    if len(kernels) != 1 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-Unraid", kernels[0]):
        raise ValueError("Cannot resolve one exact stock kernel")
    kernel = kernels[0]
    config_text = output("unsquashfs", "-cat", inputs / "bzmodules", f"src/linux-{kernel}/config")
    config = parse_config(config_text)
    if config["CONFIG_AS_VERSION"] != config["CONFIG_LD_VERSION"]:
        raise ValueError("Mixed assembler/linker versions require a reviewed builder")
    gcc, binutils = version_number(config["CONFIG_GCC_VERSION"]), version_number(config["CONFIG_AS_VERSION"])
    source_url = f"https://github.com/ich777/unraid_kernel/releases/download/{kernel}/linux-{kernel}.tar.xz"
    fetch(source_url + ".sha256", inputs / "kernel.sha256")
    kernel_hash = (inputs / "kernel.sha256").read_text().split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", kernel_hash):
        raise ValueError("Invalid prepared kernel checksum")
    fetch(source_url, inputs / "linux.tar.xz", kernel_hash)
    fetch(f"https://codeload.github.com/miskcoo/ugreen_leds_controller/tar.gz/{DRIVER_COMMIT}",
          inputs / "controller.tar.gz", DRIVER_SHA256)
    fetch("https://www.kernel.org/pub/software/utils/i2c-tools/i2c-tools-4.3.tar.xz",
          inputs / "i2c-tools.tar.xz", I2C_SHA256)
    binutils_hash = fetch(f"https://ftp.gnu.org/gnu/binutils/binutils-{binutils}.tar.xz",
                          inputs / "binutils.tar.xz")
    run("docker", "pull", "--platform", "linux/amd64", f"gcc:{gcc}")
    image = json.loads(output("docker", "image", "inspect", f"gcc:{gcc}"))[0]
    if image["Architecture"] != "amd64" or not image["RepoDigests"]:
        raise ValueError("Could not resolve an immutable x86-64 GCC image")
    gcc_image = image["RepoDigests"][0]
    builder = f"ugreen-builder:{gcc}-{binutils}"
    run("docker", "build", "--platform", "linux/amd64", "-f", HERE / "Dockerfile.kernel",
        "--build-arg", f"GCC_IMAGE={gcc_image}", "--build-arg", f"BINUTILS_VERSION={binutils}",
        "--build-arg", f"BINUTILS_SHA256={binutils_hash}", "-t", builder, HERE)
    os_version = release["version"].replace("-", "_")
    variables = {"UNRAID_VERSION": release["version"], "KERNEL_RELEASE": kernel,
                 "DRIVER_VERSION": f"{DRIVER_COMMIT[:7]}_{os_version}",
                 "PLUGIN_VERSION": f"{os_version}_r{RECIPE}", "BUILD": f"{RECIPE}candidate",
                 "EXPORT_UID": str(os.getuid()), "EXPORT_GID": str(os.getgid())}
    arguments = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none",
                 "--entrypoint", "/bin/bash"]
    for key, value in variables.items():
        arguments.extend(["-e", f"{key}={value}"])
    for host, guest in ((HERE.parent, "/repo:ro"), (inputs, "/inputs:ro"), (assets, "/export")):
        arguments.extend(["-v", f"{host.resolve()}:{guest}"])
    run(*arguments, builder, "/repo/source/build-packages-in-container.sh")
    # Prefix every file so parallel Unraid branches sharing a kernel have
    # independent immutable evidence. The installer will use the exact receipt.
    prefix = f"unraid-{release['version']}-r{RECIPE}--"
    for path in list(assets.iterdir()):
        path.rename(path.with_name(prefix + path.name))
    for path in assets.glob("*.txz.sha256"):
        archive = path.with_suffix("")
        path.write_text(f"{digest(archive)}  {archive.name}\n")
    sums = assets / (prefix + "SHA256SUMS")
    sums.write_text("".join(f"{digest(p)}  {p.name}\n" for p in sorted(assets.iterdir()) if p != sums))
    packages = {}
    for role, pattern in (("kernel", "ugreen_leds-*.txz"), ("monitor", "ugreenleds-driver-*.txz"),
                          ("i2c_tools", "i2c-tools-*.txz")):
        matches = list(assets.glob(prefix + pattern))
        if len(matches) != 1:
            raise ValueError(f"Expected one {role} package")
        packages[role] = matches[0].name
    manifest = {
        "schema": 1, "recipe": RECIPE, "status": "candidate", "unraid": release["version"],
        "kernel": kernel, "channel": release["channel"], "installer_url": release["url"],
        "installer_sha256": zip_hash, "repository_commit": commit,
        "config_sha256": digest(assets / (prefix + "stock.config")),
        "gcc_image": gcc_image, "gcc_version": gcc, "binutils_version": binutils,
        "binutils_sha256": binutils_hash, "kernel_source_url": source_url,
        "kernel_source_sha256": kernel_hash, "driver_commit": DRIVER_COMMIT,
        "driver_sha256": DRIVER_SHA256, "i2c_tools_sha256": I2C_SHA256,
        "packages": packages,
        "assets": [{"name": p.name, "sha256": digest(p), "size": p.stat().st_size}
                   for p in sorted(assets.iterdir())],
        "hardware_validation": "not performed; stable promotion prohibited",
    }
    (assets / receipts_name(release["version"])).write_text(json.dumps(manifest, indent=2) + "\n")


def validate_candidate(directory):
    receipts = list(directory.glob(f"unraid-*-r{RECIPE}.json"))
    if len(receipts) != 1:
        raise ValueError("Expected one complete build receipt")
    manifest = json.loads(receipts[0].read_text())
    if manifest.get("schema") != 1 or manifest.get("recipe") != RECIPE or manifest.get("status") != "candidate":
        raise ValueError("Unsupported candidate receipt")
    if not re.fullmatch(r"7\.[0-9]+\.[0-9]+(?:-(?:beta|rc)\.[0-9]+)?", manifest["unraid"]):
        raise ValueError("Invalid receipt version")
    if receipts[0].name != receipts_name(manifest["unraid"]):
        raise ValueError("Receipt filename mismatch")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-Unraid", manifest["kernel"]):
        raise ValueError("Invalid kernel tag")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["repository_commit"]):
        raise ValueError("Invalid repository commit")
    names = set()
    for asset in manifest["assets"]:
        name = asset["name"]
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", name) or name in names:
            raise ValueError("Unsafe or duplicate asset name")
        path = directory / name
        if path.is_symlink() or path.stat().st_size != asset["size"] or digest(path) != asset["sha256"]:
            raise ValueError(f"Candidate asset mismatch: {name}")
        names.add(name)
    if set(manifest["packages"]) != {"kernel", "monitor", "i2c_tools"}:
        raise ValueError("Incomplete package roles")
    if len(set(manifest["packages"].values())) != 3 or not set(manifest["packages"].values()) <= names:
        raise ValueError("Missing or duplicate packages")
    prefix = f"unraid-{manifest['unraid']}-r{RECIPE}--"
    for role, stem in (("kernel", "ugreen_leds-"), ("monitor", "ugreenleds-driver-"), ("i2c_tools", "i2c-tools-")):
        name = manifest["packages"][role]
        if not name.startswith(prefix + stem) or not name.endswith(".txz"):
            raise ValueError(f"Incorrect package identity: {role}")
    if {p.name for p in directory.iterdir()} != names | {receipts[0].name}:
        raise ValueError("Unrecorded candidate files")
    return manifest, receipts[0]


def publish(directory):
    manifest, receipt = validate_candidate(directory)
    tag = manifest["kernel"]
    matching = [r for r in github_releases() if r["tag_name"] == tag]
    if not matching:
        # The creation response owns the new draft. An immediate list response
        # can omit it, as observed in the first real publication job.
        release = json.loads(output(
            "gh", "api", "--method", "POST", f"repos/{REPOSITORY}/releases",
            "-f", f"tag_name={tag}", "-f", f"target_commitish={manifest['repository_commit']}",
            "-f", f"name=UGREEN candidates for {tag}", "-F", "draft=true", "-F", "prerelease=true",
            "-f", "body=Experimental kernel-specific candidates. No hardware approval. Do not use as a stable replacement."))
        if release["tag_name"] != tag or not release["draft"]:
            raise ValueError("GitHub did not return the requested kernel draft")
    else:
        release = matching[0]
    existing = {a["name"]: a for a in release["assets"]}
    # Resume only byte-identical partial uploads. Never use --clobber.
    for path in [directory / a["name"] for a in manifest["assets"]] + [receipt]:
        if path.name in existing:
            with tempfile.TemporaryDirectory() as temporary:
                remote = Path(temporary) / path.name
                run("gh", "release", "download", tag, "--repo", REPOSITORY,
                    "--pattern", path.name, "--dir", temporary)
                if digest(remote) != digest(path):
                    raise ValueError(f"Refusing to overwrite published asset: {path.name}")
        else:
            run("gh", "release", "upload", tag, path, "--repo", REPOSITORY)
    if release["draft"]:
        run("gh", "release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--prerelease")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    discovery = commands.add_parser("discover")
    discovery.add_argument("--version")
    builder = commands.add_parser("build")
    builder.add_argument("--work", required=True, type=Path)
    publisher = commands.add_parser("publish")
    publisher.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "discover":
        feed = json.loads(output("curl", "--fail", "--silent", "--show-error", "--location",
                                 "--proto", "=https", "--proto-redir", "=https", "--max-time", "60", FEED))
        candidates = queue(feed, github_releases(), args.version)
        matrix = json.dumps({"include": candidates}, separators=(",", ":"))
        print(matrix)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as dest:
                dest.write(f"matrix={matrix}\ncount={len(candidates)}\n")
    elif args.command == "build":
        build(json.loads(os.environ["RELEASE_JSON"]), args.work, os.environ["GITHUB_SHA"])
    else:
        publish(args.directory)


if __name__ == "__main__":
    main()
