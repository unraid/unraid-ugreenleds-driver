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

A real Slackware build and hardware validation have not yet been performed.
Before release, verify package contents and dependencies, install on the matching
test system, run `depmod`, load the module, and test LED behavior on supported
UGREEN hardware. A matching `vermagic` release is necessary but does not prove
configuration or symbol compatibility.
