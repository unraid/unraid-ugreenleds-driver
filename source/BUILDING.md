# Build the UGREEN kernel module

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
