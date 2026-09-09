# CLOS-2610 - grub `grub_real_boot_time` symbol not found

- **Status:** mapped (reference) - not upstreamable; the fix is upstream's own, cherry-picked here
- **Ours:** nothing of our own; `982f3b7c` is a cherry-pick
- **Upstream:** `982f3b7c` here, from upstream `ea6cd791`
  (mhecko@redhat.com, [RHEL-3341](https://issues.redhat.com/browse/RHEL-3341)),
  landed in our fork 2024-06-13

## What the ticket was actually about

The summary names the boot-time symptom, but the failure was earlier and
different. `update_grub_core` ran `grub2-install /dev/sda` during `RPMUpgrade`
and it refused:

    grub2-install: warning: your core.img is unusually large. It won't fit in
    the embedding area.
    grub2-install: error: will not proceed with blocklists.

The disk's first partition started below 1MiB, leaving too small an MBR gap for
the EL8 `core.img`. `grub2-install` aborted, so the MBR kept the EL7 core while
`/boot/grub2` got EL8 modules - and that mismatch is what produces
`symbol 'grub_real_boot_time' not found` at the next boot.

## Why there is nothing to offer

Upstream already inhibits on the precondition, in
`repos/system_upgrade/el7toel8/actors/checkfirstpartitionoffset`. We carry it as
a cherry-pick, not as our own work. The only subsequent CloudLinux commits
touching those files are mechanical rebase adaptations - `fcacc53b` (core-changes
update) and `a07d42a9` (`reporting.Tags` to `reporting.Groups`) - so there is no
CloudLinux delta to send either.

## Two process lessons

- The ticket carries the `leapp_provide_to_upstream` label, which is how it
  reached the retired filter 21880. The label was applied at triage, before the
  fix path was known - **a label added on intake is a question, not a
  conclusion.** Entries in this directory are judgements and should not inherit
  intake guesses.
- Grepping history for `CLOS-2610` finds nothing, because the commit that fixes
  it references the *upstream* ticket. Absence of our key is not evidence that
  nothing was done.

## At rebase time

Once the fork's base includes upstream `ea6cd791`, drop the cherry-pick rather
than resolving a conflict against it. Note that the actor lives under
`el7toel8/`, which upstream has since deleted wholesale - see
`el7toel8-retired-upstream.md`, which supersedes this instruction: the actor is
ours to keep now, because upstream no longer has a copy to converge with.
