# AlmaLinux ELevate 0.24.0: what it changed under CloudLinux

Merged as `almalinux-ng-0.24.0-1` for CLOS-7051. Five upstream changes each broke
CloudLinux silently - an actor crash with no report, or an upgrade that completed
while destroying content. Recorded because the next rebase will land the same
shapes again, and none of them is visible in a diff as a problem.

## 1. Trusted GPG keys moved to a per-distro path

`get_path_to_gpg_certs()` now returns
`common/files/distro/<distro>/rpm-gpg/<target major>`, where it was a
distro-agnostic `common/files/rpm-gpg/<target major>`. The old tree is gone.

Two consequences, one immediate and one delayed:

- `trusted_gpg_keys_scanner` raised `FileNotFoundError` on the missing directory.
  It now tolerates absence, but the keys have to be shipped at the new path.
- leapp-data installs keys there too, and its **target repository files still
  referenced the old path**. That surfaced only during a real upgrade, as
  `Curl error (37): Couldn't read a file:// file`, naming neither the repofile
  nor the package. The el9 file was affected as well, so this broke CloudLinux 8
  to 9 at the same time.

A `gpgkey=` is an unchecked string; leapp-data now validates every one against
the build tree.

## 2. `gpg-signatures.json` changed shape

The `keys` field went from a list to a mapping of short id to `gpg-pubkey` name.
`distribution_signed_rpm_scanner` raised `TypeError: list indices must be
integers` until the CloudLinux file was migrated.

## 3. `_DISTRO_REPOFILES_MAP` is new, and had no cloudlinux entry

`common/libraries/distro.py` gained a map of which repository files each distro
provides. Without an entry, `target_userspace_creator` fails with *"No known
distro provided repofiles mapped"*. The entry has to be per target major,
because what `cloudlinux-release` drops changed completely at 10 - see
`reference/cloudlinux-10-subsystem.md` if that file exists, otherwise: on 8 and 9
it ships the rebranded AlmaLinux repofiles, on 10 it ships only `cloudlinux.repo`
and `cloudlinux-rollout.repo`.

## 4. Version comparisons are strictly MAJOR.MINOR

`config/version.py::_validate_versions` accepts only `^([1-9]\d*)\.(\d+)$`. A
bare `"10"` target - which is what CloudLinux 10 actually is, with no minor
version - kills `pes_events_scanner` with *"Versions have to be in the form of
'<integer>.<integer>'"*. The upgrade path names the AlmaLinux minor instead.

## 5. python3-only syntax entered shared code

`system_upgrade/common` was shipped on el7, where leapp runs on python2.7. The
merge brought `yield from` and f-strings into files el7 loads. Rather than repair
that on every merge, CL7 to CL8 moved to the `cloudlinux-el7toel8` branch and
`cloudlinux` stopped building for el7; see `reference/el7toel8-retired-upstream.md`.

## What to do on the next rebase

Run the CloudLinux actor suites and a real CloudLinux 8 to 9 preupgrade, not only
the newest path. Most of the above affect 8 to 9 as much as 9 to 10, and three
produced no report at all - the actor simply crashed, or the
upgrade completed having quietly removed things.
