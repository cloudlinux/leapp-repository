# Preset files are ordered by path, not by filename

- **Status:** mapped (reference) - upstream defect, deliberately not patched here; nothing to drop at a rebase
- **Ours:** nothing. Deliberately not patched - see below.
- **Upstream target:** oamg `repos/system_upgrade/common/libraries/systemd.py`
  (`_get_system_preset_files`)
- **Checked against:** oamg/main `4963bc98` (2026-07-29),
  AlmaLinux `almalinux-ng-0.24.0` `3227e763` (2026-07-10),
  `almalinux-ng-0.24.0-1`, `almalinux` - identical in every one

## The defect

```python
preset_files = _join_presets_resolving_overrides(etc_files, usr_files)
preset_files.sort()
```

`sort()` runs on absolute paths, so **every** `/etc/systemd/system-preset/` file
sorts before **every** `/usr/lib/systemd/system-preset/` file. `systemd.preset(5)`
instead sorts by *filename* across all directories, and uses the directory
precedence only to resolve two files of the **same** name.

Since `_parse_preset_files()` is first-occurrence-wins, the order decides the
answer. Concretely, with

- `/usr/lib/systemd/system-preset/10-vendor.preset`: `disable foo.timer`
- `/etc/systemd/system-preset/99-local.preset`: `enable foo.timer`

systemd resolves `disable` (10 before 99); leapp resolves `enable` (`/etc` before
`/usr`). The two disagree, and leapp then acts on its answer.

Note the direction is not consistently "safe": with the numbering reversed the
divergence flips, so this can equally cause leapp to enable a unit systemd would
have left alone, or leave alone one systemd would have enabled.

## `/run` is a separate, deliberate omission

The same function ignores `/run/systemd/system-preset` entirely. That one is
**documented on purpose** - the docstring reads *"Entries in /run/systemd/system
are ignored."* It still diverges from `systemd.preset(5)`, which reads all three
directories, but it is a known simplification rather than an oversight, and should
be raised as a question about intent rather than reported as a bug.

## Why upstreamable

Nothing here touches CloudLinux. The function is shared code, the semantics it is
meant to implement are specified by `systemd.preset(5)`, and the deviation is
original to the implementation: only two commits have ever touched this file
upstream - `fac07e2a` ("Provide common information about systemd", which
introduced it) and `dc43277d` (which moved unrelated `enable_unit` helpers in).
The preset logic has never been revised since it was written, and no open oamg PR
or issue mentions preset ordering.

## Why we did not patch it

Because the fix cannot be scoped to the caller that surfaced it.
`get_system_service_preset_files()` and `get_system_unit_presets()` share
`_get_system_preset_files()` and `_parse_preset_files()` - deliberately, so that
override and first-match-wins semantics stay identical between them. Correcting the
ordering inside one caller would leave services and timers disagreeing about the
same preset files, which is worse than the current consistent-but-wrong behaviour.

Fixing it properly therefore **changes the enable/disable decision for services on
every upgrade**, which is far beyond the scope of a customer-facing timer fix and
needs its own validation. That is exactly why it belongs upstream rather than in a
fork patch.

## Upstream form

Sort by `os.path.basename()` and keep `_join_presets_resolving_overrides()` for
same-name resolution, which is already correct. Tests need preset files whose name
order and directory order disagree - the existing fixtures
(`00-test.preset`, `01-test.preset`) are same-directory, so they cannot catch this.
Handle `/run` in the same change or explicitly decline it, but do not leave the
docstring claiming an omission that has silently become a bug.

## Provenance

Found by the automated reviewer on our PR #69 (finding 2), 2026-08-11. The
reviewer was right about the mechanism; the disagreement was only about where the
fix belongs.
