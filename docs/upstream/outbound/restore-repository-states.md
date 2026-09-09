# Restore repository enabled/disabled states after the upgrade

- **Status:** candidate
- **Ours:** commit `392e6c86` (PR #69) -
  `repos/system_upgrade/cloudlinux/actors/restorerepositoryconfigurations/`, plus
  `enable_repository()` / `disable_repository()` / `_set_repository_state()` in
  `repos/system_upgrade/common/libraries/dnfconfig.py`
- **Upstream target:** oamg - new actor under `repos/system_upgrade/common/actors/`,
  helpers stay in `common/libraries/dnfconfig.py`
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30),
  `AlmaLinux/almalinux-ng-0.24.0`

## What we carry

An `ApplicationsPhaseTag.After` actor that compares the repositories present
before the upgrade (from `RepositoriesFacts`, gathered pre-upgrade) with the
repositories present after the main transaction, and for any repoid whose
`enabled` state changed, puts it back via `dnf config-manager
--set-enabled/--set-disabled`.

## Why upstreamable

The problem is not CloudLinux-specific: a `.repo` file replaced by an RPM update
during the upgrade transaction comes back with the packager's default `enabled`
value, silently discarding an administrator's deliberate choice to disable a
repository (or to enable one that ships disabled). The operator only finds out
later, when the next `dnf update` pulls from a repo they had switched off. This
is a plain in-place-upgrade fidelity bug and every leapp consumer has it.

The implementation only uses generic inputs: `RepositoriesFacts` (an upstream
model), `repofileutils.get_parsed_repofiles()` (an upstream library), and
`dnf config-manager`. It reads no CloudLinux paths and encodes no CloudLinux
assumptions.

## Upstream form

- Move the actor from `cloudlinux/` to `common/actors/` and drop the
  `@run_on_cloudlinux` decorator - that gate is the only CloudLinux-specific
  thing in the file.
- Fix `consumes = (RepositoriesFacts)` to `consumes = (RepositoriesFacts,)`. As
  written it is not a tuple; ours happens to work because the framework accepts
  a bare model, but upstream style is the tuple.
- The `dnfconfig` helpers can go up nearly unchanged, but tidy
  `_set_repository_state()` first: its `if`/`elif` on `new_state` has no `else`,
  so an unexpected value falls through to an `UnboundLocalError` on `cmd_flag`
  rather than a meaningful error. Only the two module-level wrappers call it
  today, so this is latent, not live - upstream will still want it closed.
- Expect a discussion about whether restoring should be reported. Upstream will
  likely want a report listing what was put back, since changing repo state
  after the transaction is invisible otherwise.

## Evidence upstream does not cover it

No comparable actor exists in either upstream tree - nothing matching `restor*`
under `repos/system_upgrade/common/actors/`, and `dnfconfig.py` upstream exposes
only `exclude_leapp_rpms()`:

```bash
git ls-tree -r --name-only oamg/main -- repos/system_upgrade/common/actors/ | grep -i restor
git show oamg/main:repos/system_upgrade/common/libraries/dnfconfig.py | grep -nE '^def '
```

## Travels with

`f4959c13` fixes `_prepare_config()` under Python 3.6 (`configparser` rejects
non-string values, and unset `metalink`/`mirrorlist` must be omitted rather than
written as `None`). That function is part of our `save_repofile()`, which
upstream does not have. If `save_repofile()` is not part of the offer, `f4959c13`
has nothing to attach to.
