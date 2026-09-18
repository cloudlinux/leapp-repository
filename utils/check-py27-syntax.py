#!/usr/bin/env python3
"""Reject Python 3-only syntax in source that must still parse under Python 2.7.

The CL7 -> CL8 upgrade runs the leapp framework under python2.7 on the source
system, so everything the el7toel8 RPM ships has to be valid Python 2.7:
`repos/system_upgrade/common`, `repos/system_upgrade/el7toel8`, our own
`repos/system_upgrade/cloudlinux` and `wp-toolkit`, and `commands`.

Upstream no longer guards this. Their unit-test matrix bottoms out at
python3.6, so f-strings, `yield from`, `raise ... from err` and PEP 484
annotations land in shared `common/` libraries freely - including
`common/libraries/config/version.py`, which nearly every actor imports. Those
are SyntaxErrors on CL7, and they arrive silently on every upstream merge.
This check is what turns that into a red build instead of a failed customer
upgrade.

`make lint` already runs `pylint --py3k`, but that is the opposite direction:
it finds python2 code that python3 would reject. This finds python3 code that
python2.7 cannot even parse.

The py2.7 grammar comes from parso 0.7.1 (later releases dropped it). parso
runs on python3, so no python2 interpreter is needed:

    pip install 'parso==0.7.1'

Two kinds of path are deliberately NOT scanned, because they never run under
python2.7 even on an el7 host:

  * `tests/` directories - the spec deletes them at install time.
  * `repos/system_upgrade/common/files/` - payloads copied into the *target*
    userspace and executed by its python3 (`rhel_upgrade.py` is the dnf
    plugin), not imported on the source system.

Used by `make lint-py27-syntax` (and therefore `make lint`) and by the
lint-cloudlinux GitHub Action so the two stay in sync.
"""

from __future__ import print_function

import ast
import io
import os
import re
import sys

# Relative to the repository root. See the module docstring for why each is
# exempt; both are matched as path prefixes after normalisation.
_EXCLUDED_PREFIXES = (
    os.path.join("repos", "system_upgrade", "common", "files"),
)

# parso's 2.7 grammar hardcodes `print` as a statement and does not honour
# `from __future__ import print_function`, so a legal py2.7 `print(x, file=f)`
# parses as an error. Where the future import IS present, `print` is an
# ordinary name, so we rename it to an equally long identifier before parsing:
# the call then parses as any other call, every other py3-only construct still
# errors, and the equal length keeps reported line/column numbers exact.
# Occurrences inside strings and comments are rewritten too, which is harmless
# because the rewritten source is only ever parsed, never executed or written.
_FUTURE_PRINT_RE = re.compile(r"^\s*from\s+__future__\s+import\s+.*\bprint_function\b", re.M)
_PRINT_CALL_RE = re.compile(r"\bprint(\s*\()")

# Constructs that the 2.7 grammar happily parses and that then fail at runtime, so
# the grammar check alone cannot see them. Imports inside a try/except are exempt:
# `try: import ConfigParser except ImportError: import configparser` is the correct
# way to write this and appears in our own actors.
_PY3_ONLY_MODULES = frozenset((
    'pathlib', 'typing', 'dataclasses', 'asyncio', 'concurrent', 'contextvars',
    'statistics', 'secrets', 'configparser', 'queue', 'unittest.mock',
))
_PY3_ONLY_CALLS = {
    'subprocess.run': 'subprocess.run() arrived in python3.5',
    'shutil.which': 'shutil.which() arrived in python3.3',
}
_PY3_ONLY_KWARGS = {
    'exist_ok': 'os.makedirs(exist_ok=...) arrived in python3.2',
}

_PARSO_HINT = (
    "This check needs parso 0.7.1, the last release carrying the Python 2.7\n"
    "grammar. Install it with:\n"
    "\n"
    "    pip install 'parso==0.7.1'\n"
)


def _load_grammar():
    try:
        import parso
    except ImportError:
        print("ERROR: parso is not installed.\n\n" + _PARSO_HINT, file=sys.stderr)
        return None
    try:
        return parso.load_grammar(version="2.7")
    except NotImplementedError:
        print(
            "ERROR: the installed parso ({}) has dropped the Python 2.7 "
            "grammar.\n\n".format(getattr(parso, "__version__", "unknown")) + _PARSO_HINT,
            file=sys.stderr,
        )
        return None


def _is_excluded(path):
    norm = os.path.normpath(path)
    if "tests" in norm.split(os.sep):
        return True
    return any(norm.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def _walk_paths(roots):
    for root in roots:
        if os.path.isfile(root):
            if root.endswith(".py") and not _is_excluded(root):
                yield root
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != "tests"]
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                if not _is_excluded(path):
                    yield path


def _imports_under_try(tree):
    """Return the set of import node ids that sit anywhere inside a try statement."""
    exempt = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    exempt.add(id(child))
    return exempt


def _check_runtime_constructs(path):
    """Return a list of (lineno, message) for python3-only runtime constructs."""
    with io.open(path, encoding="utf-8", errors="replace") as fp:
        source = fp.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # The grammar check reports this file already.
        return []

    hits = []
    exempt = _imports_under_try(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and id(node) not in exempt:
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                names = [node.module or ""]
            for name in names:
                if name.split(".")[0] in _PY3_ONLY_MODULES or name in _PY3_ONLY_MODULES:
                    hits.append((node.lineno, "{} is not in the python2.7 stdlib".format(name)))
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in _PY3_ONLY_KWARGS:
                    hits.append((node.lineno, _PY3_ONLY_KWARGS[keyword.arg]))
            dotted = _dotted_name(node.func)
            if dotted in _PY3_ONLY_CALLS:
                hits.append((node.lineno, _PY3_ONLY_CALLS[dotted]))
    return hits


def _dotted_name(node):
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return "{}.{}".format(prefix, node.attr) if prefix else ""
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _check_file(grammar, path):
    """Return a list of (lineno, message) for py2.7 syntax errors in path."""
    with io.open(path, encoding="utf-8", errors="replace") as fp:
        source = fp.read()
    if _FUTURE_PRINT_RE.search(source):
        source = _PRINT_CALL_RE.sub(r"pr1nt\1", source)
    module = grammar.parse(source)
    return [(err.start_pos[0], err.message) for err in grammar.iter_errors(module)]


def main(argv):
    paths = argv[1:]
    if not paths:
        print("usage: {} <path> [path ...]".format(argv[0]), file=sys.stderr)
        return 2
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        print("warning: no provided paths exist; nothing to scan", file=sys.stderr)
        return 0

    grammar = _load_grammar()
    if grammar is None:
        return 2

    bad = 0
    for path in _walk_paths(paths):
        findings = _check_file(grammar, path) + _check_runtime_constructs(path)
        for lineno, message in sorted(findings):
            print("{}:{}: {}".format(path, lineno, message))
            bad += 1

    if bad:
        print(
            "\nERROR: Python 3-only syntax found in source that must parse under "
            "Python 2.7 for the CL7 -> CL8 upgrade. Rewrite it: f-strings as "
            "'...'.format(...), 'yield from x' as a for loop, 'raise X from err' "
            "as a plain raise, and drop PEP 484 annotations. Also avoid "
            "python3-only stdlib (pathlib, typing) and keyword arguments such as "
            "os.makedirs(exist_ok=...), which parse cleanly but fail at runtime.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
