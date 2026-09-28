#!/usr/bin/env python3
"""Check that the spec builds on every platform it is shipped for.

Two ways the 0.24.0 merge broke that, each invisible where it was merged:

1. A boolean dependency the el7 build parses.

CL7 builds leapp-upgrade-el7toel8 with rpm 4.11, which predates boolean ("rich")
dependencies: one `Requires: (a if b)` anywhere in what it parses stops rpmbuild
before a source RPM exists. Upstream no longer builds for el7, so any merge from
them can bring one in - 0.24.0 did, with the fapolicyd subpackage, and the CL7
build failed at `rpmbuild -bs` while the CL8 build of the same commit succeeded.

rpm skips the lines inside a %if that is false, so only what an el7 build actually
parses counts. The spec's conditionals are evaluated here for rhel=7. A condition
this script does not understand is an error rather than a guess: reading it as
false would pass a spec el7 rejects.

2. A build whose bundled deps the source tarball does not carry.

Each build copies leapp*deps*el<next major>.noarch.rpm out of deps-pkgs.tar.gz,
which `make source` builds with one `DIST_VERSION=N _build_subpkg` per next major
(N produces el(N+1)). Upstream builds for el8 and el9 and bundles 8 and 9; we also
build for el7. The merge kept 7 and 9, so the CL8 build found no el9 deps and
failed in %build, while the CL7 build of the same commit got as far as it could.

Exit 0 when clean, 1 when either check fails, 2 when the spec cannot be evaluated.
Pure stdlib python3, like utils/check-spec-release.py, so CI can run it without
rpm installed.
"""

import os
import re
import sys

SPEC = os.path.join("packaging", "leapp-repository.spec")
MAKEFILE = "Makefile"

_DEPENDENCY = re.compile(
    r"^(?:Build)?(?:Requires|Recommends|Suggests|Supplements|Enhances|Conflicts|"
    r"Obsoletes|Provides|OrderWithRequires)(?:\([^)]*\))?\s*:\s*(?P<value>.*)$"
)
# A boolean dependency is one whose clause opens with "(", first or after a comma.
_BOOLEAN = re.compile(r"(?:^|,)\s*\(")
# What the spec's %if conditions are made of: numbers, comparisons, logic, parentheses.
_TOKEN = re.compile(r"\s*(\d+|==|!=|>=|<=|&&|\|\||[<>!()])")


class UnknownCondition(Exception):
    """A %if this script cannot evaluate where el7 would evaluate it."""


def evaluate(condition, rhel):
    """The truth of a %if *condition* on a build where %{?rhel} is *rhel*."""
    text = condition.replace("%{?rhel}", str(rhel))
    tokens, pos = [], 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip() == "":
                break
            raise UnknownCondition(condition)
        tokens.append(match.group(1))
        pos = match.end()
    if not tokens:
        raise UnknownCondition(condition)
    python = {"&&": " and ", "||": " or ", "!": " not "}
    expression = "".join(python.get(t, " {0} ".format(int(t)) if t.isdigit() else t)
                         for t in tokens)
    try:
        return bool(eval(expression, {"__builtins__": {}}, {}))  # pylint: disable=eval-used
    except SyntaxError:
        raise UnknownCondition(condition)


def boolean_dependencies(lines, rhel=7):
    """[(line number, line)] for each boolean dependency a *rhel* build parses."""
    found = []
    stack = []  # one entry per open %if: whether its current branch is taken
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("%changelog"):
            break
        active = all(stack)
        if re.match(r"%if\b", line):
            # A condition inside a branch rpm skips is never evaluated by rpm either.
            stack.append(evaluate(line[3:].strip(), rhel) if active else False)
            continue
        if re.match(r"%(ifarch|ifnarch|ifos|ifnos|elif)\b", line):
            if active:
                raise UnknownCondition(line)
            stack.append(False)
            continue
        if line.startswith("%else"):
            if not stack:
                raise UnknownCondition("%else without %if at line {0}".format(number))
            parent = all(stack[:-1])
            stack[-1] = parent and not stack[-1]
            continue
        if line.startswith("%endif"):
            if not stack:
                raise UnknownCondition("%endif without %if at line {0}".format(number))
            stack.pop()
            continue
        if not active:
            continue
        match = _DEPENDENCY.match(line)
        if match and _BOOLEAN.search(match.group("value")):
            found.append((number, line))
    if stack:
        raise UnknownCondition("{0} %if block(s) left open".format(len(stack)))
    return found


def missing_deps_bundles(spec_text, makefile_text):
    """DIST_VERSIONs a build needs deps from that `make source` does not build."""
    needed = {int(major) - 1 for major in
              re.findall(r"^\s*%define\s+next_major_ver\s+(\d+)", spec_text, re.M)}
    if not needed:
        raise UnknownCondition("the spec defines no next_major_ver")
    bundled = {int(n) for n in re.findall(r"DIST_VERSION=(\d+) _build_subpkg", makefile_text)}
    return sorted(needed - bundled)


def main():
    try:
        with open(SPEC) as fp:
            spec = fp.read()
        with open(MAKEFILE) as fp:
            makefile = fp.read()
        found = boolean_dependencies(spec.splitlines(), rhel=7)
        missing = missing_deps_bundles(spec, makefile)
    except UnknownCondition as e:
        print("ERROR: cannot evaluate {0}: {1}".format(SPEC, e), file=sys.stderr)
        return 2
    if found:
        print("ERROR: rpm 4.11 on el7 cannot parse boolean dependencies, and the el7 build"
              " parses these:", file=sys.stderr)
        for number, line in found:
            print("  {0}:{1}: {2}".format(SPEC, number, line), file=sys.stderr)
        print("Put each inside a %if that excludes el7.", file=sys.stderr)
    if missing:
        print("ERROR: `make source` in {0} bundles no deps for DIST_VERSION {1}, which the"
              " spec's builds copy in %build. Add a `DIST_VERSION=N _build_subpkg` line for"
              " each.".format(MAKEFILE, ", ".join(str(n) for n in missing)), file=sys.stderr)
    if found or missing:
        return 1
    print("The spec parses on el7 and every build's deps are bundled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
