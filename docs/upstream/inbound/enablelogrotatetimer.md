# `el8toel9/actors/enablelogrotatetimer` arrives and overrides our rule

- **Status:** hazard (inbound) - act at the next rebase
- **Theirs:** `repos/system_upgrade/el8toel9/actors/enablelogrotatetimer/`
  (oamg PR 1501, merged 2026-03-03, Jira RHEL-17361)
- **Present in:** `AlmaLinux/almalinux-ng-0.24.0` `3227e763` (2026-07-10),
  oamg/main `4963bc98` (2026-07-29). **Absent from our tree** - which is why
  CLOS-4518 reproduced here at all.
- **Collides with:** [../outbound/CLOS-4518-cron-to-timer-preset-migration.md](../outbound/CLOS-4518-cron-to-timer-preset-migration.md)

## Do this at the rebase

**Delete `el8toel9/actors/enablelogrotatetimer/` and its tests**, unless our timer
pair has been upstreamed by then - in which case theirs is already gone and there
is nothing to do.

## Why - and why git will not tell you

Their actor is, in full:

```python
LOGROTATE_TIMER = 'logrotate.timer'
def process():
    try:
        enable_unit(LOGROTATE_TIMER)
```

FinalizationPhase, hardcoded to one timer, and **unconditional** - no check of the
unit's current state, its vendor preset, or whether it existed on the source.

Ours (`enablemigratedtimers`) enables a timer only when it is absent on the source,
disabled on the target, and preset-enabled there. The absent-on-source condition is
the whole point: a unit that never existed on the source cannot have been disabled
by the administrator, so acting on it is safe. Theirs has no such guard, so on a
host where the administrator deliberately disabled `logrotate.timer`, theirs
re-enables it and ours would not have.

Theirs also runs *earlier* (FinalizationPhase, pre-reboot) than ours (FirstBoot),
and ours never disables anything, so ours will not undo it. The net effect of
inheriting their actor is that our administrator-intent guarantee silently stops
holding for `logrotate.timer`, while continuing to hold for every other timer.

The file is new upstream and absent here, so it arrives as a **clean add**: no
conflict, no prompt, nothing for a reviewer to notice. That is exactly the class of
change this register exists to catch.

## If you are tempted to keep both

Do not. Two mechanisms acting on one unit, with different conditions, is how you
get a behaviour nobody can explain later. If ours has not been upstreamed and you
want upstream's coverage, the honest options are to drop ours and lose the guard,
or to keep ours and drop theirs - not to run both and hope the phase ordering
stays as it is today.
