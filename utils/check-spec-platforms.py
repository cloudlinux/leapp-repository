#!/usr/bin/env python3
"""Check that the packages build, and install beside leapp-data, on every platform.

Two ways the 0.24.0 work broke that, each invisible where it was made:

1. A build whose bundled deps the source tarball does not carry.

Each build copies leapp*deps*el<next major>.noarch.rpm out of deps-pkgs.tar.gz,
which `make source` builds with one `DIST_VERSION=N _build_subpkg` per next major
(N produces el(N+1)). The merge resolved the Makefile to bundle 7 and 9, so the
CL8 build found no el9 deps and failed in %build.

2. A file leapp-data-cloudlinux also ships.

leapp-data-cloudlinux installs the CloudLinux target GPG keys into this package's
tree, at repos/system_upgrade/common/files/distro/cloudlinux/rpm-gpg/<major> (its
Makefile's GPG_DIR_RHEL). A copy committed here too makes both RPMs own the same path
with different content, and the transaction check refuses to install them together:
CL7 QA stopped at "Install Leapp Framework" on exactly that. leapp-data owns the keys,
so nothing may be committed under that directory here.

The CloudLinux 7 to 8 upgrade is built from the cloudlinux-el7toel8 branch, so
nothing here checks what an el7 build parses any more.

Exit 0 when clean, 1 when any check fails, 2 when the spec cannot be evaluated.
Pure stdlib python3, like utils/check-spec-release.py, so CI can run it without
rpm installed.
"""

import os
import re
import sys

SPEC = os.path.join("packaging", "leapp-repository.spec")
MAKEFILE = "Makefile"
LEAPP_DATA_OWNED = os.path.join("repos", "system_upgrade", "common", "files", "distro",
                                "cloudlinux", "rpm-gpg")

class UnknownCondition(Exception):
    """The spec does not say what this script needs to know."""


def missing_deps_bundles(spec_text, makefile_text):
    """DIST_VERSIONs a build needs deps from that `make source` does not build."""
    needed = {int(major) - 1 for major in
              re.findall(r"^\s*%define\s+next_major_ver\s+(\d+)", spec_text, re.M)}
    if not needed:
        raise UnknownCondition("the spec defines no next_major_ver")
    bundled = {int(n) for n in re.findall(r"DIST_VERSION=(\d+) _build_subpkg", makefile_text)}
    return sorted(needed - bundled)


def files_leapp_data_owns(root):
    """Files committed under the tree leapp-data-cloudlinux installs into, relative."""
    found = []
    for dirpath, _dirs, files in os.walk(os.path.join(root, LEAPP_DATA_OWNED)):
        found.extend(os.path.relpath(os.path.join(dirpath, name), root) for name in files)
    return sorted(found)


def main():
    try:
        with open(SPEC) as fp:
            spec = fp.read()
        with open(MAKEFILE) as fp:
            makefile = fp.read()
        missing = missing_deps_bundles(spec, makefile)
        shared = files_leapp_data_owns(".")
    except UnknownCondition as e:
        print("ERROR: cannot evaluate {0}: {1}".format(SPEC, e), file=sys.stderr)
        return 2
    if missing:
        print("ERROR: `make source` in {0} bundles no deps for DIST_VERSION {1}, which the"
              " spec's builds copy in %build. Add a `DIST_VERSION=N _build_subpkg` line for"
              " each.".format(MAKEFILE, ", ".join(str(n) for n in missing)), file=sys.stderr)
    if shared:
        print("ERROR: leapp-data-cloudlinux installs these, so shipping them here too makes"
              " both packages own one path with different content:", file=sys.stderr)
        for path in shared:
            print("  " + path, file=sys.stderr)
        print("Remove them from this tree; leapp-data owns the CloudLinux target keys.",
              file=sys.stderr)
    if missing or shared:
        return 1
    print("Every build's deps are bundled, and nothing here is shipped by leapp-data too.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
