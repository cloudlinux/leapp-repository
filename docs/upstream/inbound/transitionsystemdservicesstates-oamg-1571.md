# oamg PR 1571 rewrites `transitionsystemdservicesstates`

- **Status:** hazard (inbound) - not merged upstream yet; re-check before rebasing
- **Theirs:** oamg PR **1571**, "transitionsystemdservicesstates: Fix reports
  containing incorrect services" - open, marked draft as of 2026-08-13
  ("keeping this as draft until we decide if it can go into the release")
- **Touches:** `repos/system_upgrade/common/actors/systemd/transitionsystemdservicesstates/`
  - both `libraries/transitionsystemdservicesstates.py` and its test file
- **Collides with:** our `3cf318e2` (honor the target preset for units absent on
  the source) and `451d923e` (keep excluding the libvirt group once that path
  exists), documented in
  [../outbound/CLOS-4518-cron-to-timer-preset-migration.md](../outbound/CLOS-4518-cron-to-timer-preset-migration.md)

## Do this at the rebase

Read PR 1571 first. If it has landed, **rebuild our two commits on top of theirs**
rather than merging past them - and re-run the actor's tests, not just the ones we
added, because their change is about which services end up in which report.

If it is still open, nothing to do beyond leaving this entry in place.

## Why it collides

Their fix is about membership of the 'newly enabled' and 'kept enabled' reports:
services whose source state, target state and target preset combine in particular
ways are currently reported in both, incorrectly. The example in their description
is a service that was not enabled on the source, is not enabled on the target, and
has a target preset of `enable`.

That is precisely the combination our new-unit path introduces and then acts on. We
changed `_get_desired_service_state()` to return `"enabled"` for a unit with no
source state at all, and guarded `_get_newly_enabled()` against the now-possible
missing source entry. Their rewrite reasons about the same function and the same
reports, from a different angle.

Unlike the `enablelogrotatetimer` case this one *will* produce a real merge
conflict, since we both edit the same lines - so it announces itself. It is
recorded anyway because the resolution is not mechanical: taking either side
wholesale is likely wrong, and the tests that would catch a bad merge are the ones
their PR is rewriting.
