# CLOS-2565 - shared mount points during overlay creation

- **Status:** candidate
- **Ours:** commit `09a1b399`, touching `repos/system_upgrade/common/libraries/mounting.py`
  and `repos/system_upgrade/common/libraries/overlaygen.py`
- **Upstream target:** oamg, the same two files
- **Checked against:** not re-verified in the 2026-07-31 sweep (see below)

## What we carry

Forces creation of shared mount points during target userspace overlay creation.

## Why upstreamable

Both files are upstream-owned and the change is about generic overlay/mount
propagation during target userspace creation, with no CloudLinux-specific
premise. Carried over from the retired Jira filter 21880.

## Before offering

Confirm it still applies to current upstream. `overlaygen.py` has been reworked
upstream since our base - `pstodulk`'s overlay redesign plus `mhecko`'s disk
image size cap - and this fix may have been superseded there the same way
`CLOS-2816` was. The 2026-07-31 sweep did not settle this one, because it
predates the sweep window and was inherited from the filter rather than found in
the log. Treat the `candidate` status as provisional until someone diffs
`09a1b399` against current `oamg/main`.
