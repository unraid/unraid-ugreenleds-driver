# Build the UGREEN kernel module

**Current status: experimental, not a production replacement.** The retired
beta2 workflow used GCC 14.2.0. The official beta2 configuration specifies GCC
15.3.0 and binutils 2.46.1. Its successful run does not establish a matching
target toolchain. Do not promote the existing `1test` or `2test` packages.

Release automation is under development. `discover_unraid.py` reads the
official USB Creator JSON feed on standard input. It includes all advertised
Unraid 7 stable, beta, and RC versions, including older maintenance branches.
`--version` selects one exact advertised version. The output is a discovery
queue, not a list of validated or supported packages. It does not infer kernel
versions or treat the URL path component as a ZIP checksum.

```bash
curl --fail --silent --show-error https://releases.unraid.net/usb-creator |
  python3 source/discover_unraid.py --version 7.4.0-beta.2
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s source/tests -v
```

`Dockerfile.kernel` defines the corrected kernel compiler environment using a
pinned GCC 15.3.0 image and checksum-pinned binutils 2.46.1 source. The image
build and real beta2 driver compilation passed on 2026-09-18. It is not yet
connected to release publication. Its Debian userspace libraries must not be
used as evidence that a userspace package works on Unraid.

`prepare-kernel.sh KDIR STOCK_CONFIG KERNEL_RELEASE` removes generated state
from an authenticated, disposable kernel source tree. It regenerates headers
from the official configuration and rejects changed kernel options or compiler
versions. It retains the supplied `Module.symvers`, which still requires
validation against stock symbols before publication. Never run this script
against a source tree that contains work you need to retain.

`verify_kernel_config.py` compares configurations. It records, but permits,
compiler banner differences and listed Rust-tool probes when Rust is disabled.
Other changed, added, or removed options stop the build. Rust-enabled targets
are unsupported and stop the build.

`verify_led_layout.py STOCK_INPUT_LEDS CANDIDATE_LED_UGREEN` inspects x86-64 ELF
instructions without loading either module. The rebuilt beta2 driver and stock
`input-leds` both place the pointer after `led_classdev` at byte 432. The check
rejects the known 416-byte mismatch and unknown instruction patterns. It is a
specific regression check, not proof of complete kernel ABI compatibility.

The real build used the official configuration extracted from `bzmodules` at
`src/linux-6.18.47-Unraid/config`, SHA-256
`b3462a4a0d1c7566f447230c970b068b7b4b759ff1f29a5f972216d14a661160`.
`unmkinitramfs` successfully extracted the stock beta2 modules without a fixed
offset. The regenerated configuration differed only in unused Rust-tool probes.
The module reports GCC 15.3.0 and the expected stock kernel vermagic. Package
publication, complete userspace packaging, and hardware validation remain open.

The sections below document the earlier test build and its limitations.

`ugreen-driver.SlackBuild` is a build-only template for an x86-64 Slackware
container. It produces a kernel-specific Slackware package and SHA-256 checksum.
It does not download sources, install packages, load modules, or publish releases.
The existing `compile.sh`, plugin installer, and update process remain unchanged.

## Inputs

Use a disposable build container, not a production NAS. Run the script as root
inside that container so package ownership is correct. Source Makefiles execute
code: review and authenticate the sources before building.

Provide a clean, pinned checkout of the upstream UGREEN controller and a prepared
Unraid kernel build tree. The kernel tree must contain the matching `.config`,
generated headers, `include/config/kernel.release`, and nonempty `Module.symvers`.
Use the compiler and build tools appropriate for that Unraid kernel.

The installer ZIP supplies runtime artifacts, but those are not a substitute for
these kernel build inputs unless a complete prepared tree is present.

## Invocation

Replace the example paths and values with verified inputs. The kernel release
must include the exact `-Unraid` suffix. Version labels cannot contain hyphens.

```bash
KDIR=/build/kernel \
KERNEL_RELEASE=6.18.47-Unraid \
DRIVER_SRC=/build/ugreen_leds_controller \
DRIVER_VERSION=PINNED_COMMIT \
OUTPUT=/build/packages \
JOBS=4 \
bash source/ugreen-driver.SlackBuild
```

`BUILD` defaults to `1`, `JOBS` to `2`, and `CC` to `gcc`.
Use `bash source/ugreen-driver.SlackBuild --help` for the input list.

The script copies the driver source into a unique staging directory, builds
against explicit `KDIR`, and checks the module's kernel release in `vermagic`.
It stages `led-ugreen.ko.xz` under `/lib/modules/<release>/extra/` and includes
license, source checksums, and build-input metadata. These records are not a
signed provenance attestation or proof of a reproducible build.

Output names use the form:

```text
ugreen_leds-<driver-version>_<kernel-release-with-underscores>-x86_64-<build>.txz
```

Existing output packages are not overwritten. Staging directories are retained
for inspection, including after failure. Remove only the specific staging
directory after inspecting it. A failure after package creation can leave the
package present without its checksum; only use outputs from a successful run.

## Limits and validation

This is not yet wired into the legacy installer's package/checksum naming scheme.
Release integration must explicitly reconcile that contract before publication.
The script does not run `depmod` or sign the kernel module.

i2c-tools and the original monitor are excluded from this build. The monitor
still needs packaging for installation. Stock i2c-tools availability must be
verified for each supported Unraid release before removing that dependency from
the installer.

Local syntax and ShellCheck validation:

```bash
bash -n source/ugreen-driver.SlackBuild
shellcheck source/ugreen-driver.SlackBuild
```

A real Slackware container build succeeded for `6.18.47-Unraid` with GCC 14.2.0
on 2026-09-18. Hardware validation has not been performed. The first build exposed
the upstream Makefile's dependence on shell `PWD`. The SlackBuild now calls the
kernel build system directly with an explicit module directory, `M=...`.

See [the beta2 test instructions](TESTING-beta2.md) for the manual-start bundle.
Before release, test installation, LED behavior, networking, and recovery on
supported UGREEN hardware. A matching `vermagic` release is necessary but does
not prove configuration or symbol compatibility.

## Verified beta2 build inputs

- Controller: `miskcoo/ugreen_leds_controller`, commit `992fc6dcb5da4cfc9aa25561eff2f584c06f586d`.
- Prepared kernel: `https://github.com/ich777/unraid_kernel/releases/download/6.18.47-Unraid/linux-6.18.47-Unraid.tar.xz`.
- Kernel archive SHA-256: `72822aea43a7d6dab3ae7a8489481a583504896927c1ce7117df8ab1b46d173f`.
- Builder: `ghcr.io/ich777/unraid_kernel@sha256:4de2638e4614878b0a55df8bf7db93a8b643d6f221904a846d532c719b84440f`.
- Compiler: GCC 14.2.0, x86-64 Slackware.
- Package inputs: `DRIVER_VERSION=20260918.992fc6d BUILD=1test JOBS=4`.

Use `--platform linux/amd64 --network none --entrypoint /bin/bash` when running
this image. Do not run its default entrypoint. Mount reviewed source inputs
read-only and expose only the intended output directory for host writes.

Extract the verified kernel archive into `/kernel` inside the disposable container.
With the controller at `/inputs/controller`, repository at `/repo`, and output
at `/output`, run:

```bash
KDIR=/kernel KERNEL_RELEASE=6.18.47-Unraid \
DRIVER_SRC=/inputs/controller DRIVER_VERSION=20260918.992fc6d \
BUILD=1test OUTPUT=/output JOBS=4 bash /repo/source/ugreen-driver.SlackBuild
```

The build passed from the unrelated working directory `/usr/src`. Package
extraction matched the staged module. `depmod -e -E /kernel/Module.symvers`
against a separate tree of stock beta2 modules plus this module reported no
warnings. Both stock and rebuilt module metadata reported
`6.18.47-Unraid SMP preempt mod_unload`. These checks did not load the driver.

## GitHub Actions asset

The removed `build-beta2-kernel.yml` built the fixed beta2 target on Ubuntu 24.04 through the
pinned Slackware container. It is retired because its compiler does not match
the stock target. The description below records that historical build. The
replacement release workflow is not yet active. `validate-release-tooling.yml`
runs discovery tests only and does not publish packages.

The action authenticates the source, prepared kernel, and official installer ZIP
with SHA-256. It extracts stock modules without executing the Unraid rootfs.
Compilation, package staging, ownership changes, and archive creation happen on
the container's Linux-native filesystem. Only finished files enter the export
mount. The SlackBuild now explicitly sets all directories to `0755` and files to
`0644`, with root ownership. Archive metadata is checked before upload.

Compatibility checks require the pinned build configuration and Module.symvers,
GCC 14.2.0, matching stock I2C and LED class vermagic, and no depmod diagnostics.
The archive contains only the external kernel module and documentation. It has
no userspace/glibc dependency and does not replace stock modules or libraries.
The monitor and i2c-tools are not part of this action's asset. A future userspace
bundle requires separate checks against Unraid's loader and shared libraries.

The prepared configuration disables `CONFIG_IKCONFIG` and `CONFIG_MODVERSIONS`.
Therefore these checks do not prove an embedded configuration match, symbol CRC
match, or complete runtime ABI compatibility. Physical testing is still required.

Download the run artifact named `ugreen-leds-6.18.47-Unraid-<run>-<attempt>`.
It contains the `2test.txz` package, checksum, source archive, scripts, build log,
archive permission listing, and `compatibility.txt`. The workflow requests 30
days of retention, but the repository currently caps this at seven days.
The workflow does not create a GitHub Release or change the legacy installer.
The earlier manual test guide names the local `1test` package. For an action-built
module, use the `2test` filename, verify its SHA-256, and obtain the monitor and
i2c-tools separately. Do not interpret build success as hardware validation.
