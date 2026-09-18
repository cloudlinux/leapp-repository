# Upstream `common/` is no longer python2.7-parseable

- **Status:** hazard (inbound) - recurring; re-measure at every merge from upstream
- **Theirs:** `repos/system_upgrade/common/` on `AlmaLinux/almalinux-ng-*`, and the
  oamg code it tracks
- **Measured against:** `AlmaLinux/almalinux-ng-0.24.0-1` `e3d2303b` (2026-09-07)

## What arrives

Upstream's unit-test matrix (`.github/workflows/unit-tests.yml`) bottoms out at
**python3.6** - there is no python2.7 job at all, and has not been one for about two
years. oamg deleted `repos/system_upgrade/el7toel8/` in `b6e84f79` (2025-06-04) and
AlmaLinux followed, so upstream has nothing left that runs under python2.7 and no
reason to keep `common/` parseable by it.

We still ship CL7 -> CL8 (`leapp-upgrade-el7toel8-0.20.0-11`, 2026-09-01), where the
framework runs under **python2.7 on the source system**. Every python3-only construct
upstream puts in `common/` is therefore a SyntaxError on a CL7 box.

At `0.24.0-1` the measured damage was **21 files**: f-strings, `yield from`,
`raise ... from err`, and PEP 484 annotations. Three of them are shared libraries that
sit on the el7 load path, and one of those is the worst possible case -
`common/libraries/config/version.py`, which nearly every actor imports:

```
libraries/config/version.py:105    yield from self.data
libraries/grub.py:385              ) from err
libraries/efi.py                   f-strings throughout
```

Beyond syntax there are python3-only imports and keyword arguments, which parse
cleanly under the 2.7 grammar and fail at runtime instead:
`scanthirdpartytargetpythonmodules` imports `pathlib`, `checknvme` imports `typing`,
and `mount_unit_generator` calls `os.makedirs(..., exist_ok=True)`.

## Action at a merge

Run `make lint-py27-syntax` after resolving conflicts and before pushing. It is a
prerequisite of `make lint` and has its own job in the lint-cloudlinux workflow, so a
merge that reintroduces this goes red rather than reaching a customer.

Repairs are mechanical: f-string to `'...'.format(...)`, `yield from x` to a `for`
loop, `raise X from err` to a plain `raise X`, drop the annotations, and replace the
python3-only stdlib with `os.path` equivalents. Keep the repairs in the merge commit
or in one follow-up commit on top of it, so a future `git log` on the file shows why
our line differs from upstream's.

## Why we do not simply take upstream's side

Two other routes were considered and rejected when this was first measured
(CLOS-7051, 2026-09-18):

- **Drop `el7toel8` like upstream did.** CL7 -> CL8 is live product with fixes
  landing in the last few months. Keeping the directory stays reversible; deleting it
  and re-deriving CL7 fixes across two branches does not.
- **Let `make lint`'s existing `pylint --py3k` catch it.** It runs only when the lint
  venv is python2.7, and it looks the other way: it finds python2 code that python3
  would reject, not python3 code python2.7 cannot parse.

The checker is `utils/check-py27-syntax.py`. It uses parso pinned to **0.7.1**, the
last release carrying the python2.7 grammar - 0.8.x raises `NotImplementedError` for
`version='2.7'`. parso runs on python3, so no python2 interpreter is needed.

One quirk worth knowing before trusting a result: parso's 2.7 grammar hardcodes
`print` as a statement and ignores `from __future__ import print_function`, so a
legal `print(x, file=sys.stderr)` is reported as a SyntaxError. The checker rewrites
`print(` to an equally long identifier in files carrying that future import. Two of
our own files (`commands/list_runs/__init__.py`,
`cloudlinux/actors/replacerpmnewconfigs/actor.py`) are the reason that workaround
exists.

See `reference/el7toel8-retired-upstream.md` for the deletion this follows from.
