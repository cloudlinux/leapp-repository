#!/usr/bin/env python3
"""Reject undeclared non-ASCII bytes in Python source.

Python 2.7 source is ASCII-only unless the file declares its encoding via
PEP 263 (a `# -*- coding: <name> -*-` or `# coding=<name>` comment on the
first or second line). This script enforces that rule on the paths given
as positional arguments: any *.py file that contains a byte > 0x7F and
does NOT carry a PEP 263 declaration is reported and the script exits 1.

Used both by `make lint-non-ascii` (and therefore `make lint`) and by
the lint-cloudlinux GitHub Action so the two stay in sync.
"""

from __future__ import print_function

import os
import re
import sys


# PEP 263: an encoding declaration must appear on line 1 or 2 and match
# the regex below. https://peps.python.org/pep-0263/
_CODING_RE = re.compile(rb"^[ \t\f]*#.*?coding[=:][ \t]*([-_.a-zA-Z0-9]+)")


def _file_has_encoding_declaration(data):
    head = data.split(b"\n", 2)[:2]
    return any(_CODING_RE.match(line) for line in head)


def _scan_file(path):
    """Return a list of (lineno, decoded_line) for lines with non-ASCII
    bytes. Empty list means the file is clean OR has a PEP 263 declaration.
    """
    with open(path, "rb") as fp:
        data = fp.read()
    if not any(b > 0x7F for b in bytearray(data)):
        return []
    if _file_has_encoding_declaration(data):
        return []
    hits = []
    for i, line in enumerate(data.splitlines(), start=1):
        if any(b > 0x7F for b in bytearray(line)):
            hits.append((i, line.decode("utf-8", "replace")))
    return hits


def _walk_paths(roots):
    for root in roots:
        if os.path.isfile(root):
            if root.endswith(".py"):
                yield root
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def main(argv):
    paths = argv[1:]
    if not paths:
        print("usage: {} <path> [path ...]".format(argv[0]), file=sys.stderr)
        return 2
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        print("warning: no provided paths exist; nothing to scan", file=sys.stderr)
        return 0

    bad = 0
    for path in _walk_paths(paths):
        hits = _scan_file(path)
        for lineno, text in hits:
            print("{}:{}:{}".format(path, lineno, text))
            bad += 1

    if bad:
        print(
            "\nERROR: Non-ASCII bytes found in Python source without a PEP 263 "
            "encoding declaration. Replace em-dashes (U+2014), smart quotes, "
            "ellipsis, etc. with ASCII equivalents, or add "
            "'# -*- coding: utf-8 -*-' on line 1 or 2 if the non-ASCII content "
            "is intentional.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
