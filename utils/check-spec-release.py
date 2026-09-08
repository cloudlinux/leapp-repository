#!/usr/bin/env python3
"""Check that the release we ship is the release the spec declares.

The CloudLinux fork owns its release numbers: the release process keys the Jira
fixVersion, the spec's Release field and the git tag to one X.Y.Z-R, and the build is
cut from that tag. Nothing in the build may rewrite that number.

Upstream works the other way round. Its spec carries the placeholder
`Release: 1%{?dist}` and the Makefile stamps a computed release over it for COPR
scratch builds:

    RELEASE="$(N_REL).$(TIMESTAMP).$(SHORT_SHA).$(BRANCH)$(REQUEST)$(_SUFFIX)"
    sed -i "s/1%{?dist}/$(RELEASE)%{?dist}/g" packaging/$(PKGNAME).spec

That pattern is an unanchored SUBSTRING. Against our own release numbers it matches
inside them: `Release: 11%{?dist}.cloudlinux` contains `1%{?dist}` from the second
character, so the leading `1` survives and the rest is replaced, yielding

    Release: 10.202608141010Z.b80470e8.HEAD%{?dist}.cloudlinux

Release 0.20.0-11 was built exactly that way and had to be discarded. It bites any
release ending in 1 (1, 11, 21, ...); -2 through -10 were correct only because they do
not contain the pattern, which is luck rather than design. And it is not hypothetical
that the Makefile runs here: buildsys-pre-build, the CloudLinux Build System hook,
invokes `make srpm` and unpacks the SRPM it produces.

Two things are therefore checked:

1. `make print_release` reports the spec's release, so the Makefile's notion of the
   release is the spec's and not a composed one;
2. nothing in the Makefile edits a spec IN PLACE, which is how the corruption happened.
   Check 1 alone would not catch a stamp reintroduced into the `srpm` or `_build_local`
   recipes, since those do not affect `print_release`.

   In place is the distinction that matters: reading a spec through a pipe is how both
   VERSION and RELEASE are derived and must stay allowed, so the signature looked for is
   an editing invocation (`sed -i`) aimed at a spec, not the word `sed` near `Release:`.

Exit 0 when the release is intact, 1 otherwise. Pure stdlib, like
utils/check-non-ascii.py, so CI can run it without a venv.
"""

import os
import re
import subprocess
import sys

SPEC = os.path.join("packaging", "leapp-repository.spec")
MAKEFILE = "Makefile"

# An in-place edit aimed at a spec: `sed -i ... something.spec`, or any -i edit of a file
# under packaging/. Reading a spec through a pipe (how VERSION and RELEASE are derived) has
# no -i and is deliberately not matched.
_STAMP_PATTERNS = (
    re.compile(r"\bsed\b[^\n]*\s-i(?:\S*)?\s[^\n]*(?:\.spec\b|packaging/)"),
)


def spec_release(text):
    """The release the spec declares, macros and dist tag stripped.

    `Release:        11%{?dist}.cloudlinux` -> `11`. Everything from the first `%` on is
    rpm's business (the dist tag and our `.cloudlinux` marker); the number before it is
    the release the process assigned.
    """
    m = re.search(r"^Release:[ \t]*([^%\n]+)", text, re.M)
    return m.group(1).strip() if m else None


def stamping_sites(makefile_text):
    """Lines that edit a spec in place, as (lineno, text). Empty when clean."""
    hits = []
    for n, line in enumerate(makefile_text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if any(p.search(line) for p in _STAMP_PATTERNS):
            hits.append((n, line.strip()))
    return hits


def main():
    failed = False

    for path in (SPEC, MAKEFILE):
        if not os.path.exists(path):
            print("ERROR: {0} not found - run from the repository root".format(path),
                  file=sys.stderr)
            return 1

    with open(SPEC) as f:
        declared = spec_release(f.read())
    if not declared:
        # Unreadable is not a pass: without the declared release there is nothing to
        # compare the build against.
        print("ERROR: could not read Release from {0}".format(SPEC), file=sys.stderr)
        return 1

    # 1. the Makefile must report the spec's release
    # --no-print-directory because GNU make turns on -w for a sub-make, and this
    # script is itself run from a make recipe (lint-spec-release) in CI. Without
    # it stdout is "Entering directory ..." / the release / "Leaving directory
    # ...", the last line is the directory message, and the check fails on every
    # branch. The make[N]: filter keeps any other recursion chatter out too.
    proc = subprocess.run(["make", "--no-print-directory", "print_release"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print("ERROR: `make print_release` failed:\n{0}".format(
            (proc.stderr or proc.stdout).strip()), file=sys.stderr)
        return 1
    reported = [line.strip() for line in (proc.stdout or "").splitlines()
                if line.strip() and not line.startswith("make[")]
    reported = reported[-1] if reported else ""
    if reported != declared:
        failed = True
        print("ERROR: the build would not ship the declared release.", file=sys.stderr)
        print("  {0} declares: {1}".format(SPEC, declared), file=sys.stderr)
        print("  make print_release: {0}".format(reported or "(nothing)"),
              file=sys.stderr)
        print("  The release number is assigned by the release process and the build "
              "must not compose one.", file=sys.stderr)

    # 2. nothing may rewrite a spec's Release
    for lineno, line in stamping_sites(MAKEFILE and open(MAKEFILE).read()):
        failed = True
        print("ERROR: {0}:{1} edits a spec in place:".format(MAKEFILE, lineno),
              file=sys.stderr)
        print("  {0}".format(line), file=sys.stderr)
        print("  Release 0.20.0-11 was corrupted this way. The spec's Release is "
              "authoritative in this fork.", file=sys.stderr)

    if failed:
        return 1
    print("Release {0} is declared by the spec and not rewritten by the build.".format(
        declared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
