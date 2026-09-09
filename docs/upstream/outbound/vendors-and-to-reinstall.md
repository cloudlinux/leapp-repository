# vendors.d and the to_reinstall mechanism

- **Status:** merged into AlmaLinux; still a candidate for oamg
- **Ours:** commit `6bd05ad9` (PR #28, 2022-12-09) for `to_reinstall`;
  `7344cee2` (PR #5) and follow-ups for `vendors.d`
- **Upstream:** AlmaLinux `6d4f9ea8` (shalal545@gmail.com, 2024-06-20),
  `AlmaLinux vendors.d functionaloty rebased on top of v0.19 (#114)`
- **Checked against:** `AlmaLinux/almalinux-ng-0.24.0`, oamg/main `65ca51d5`

## Why this entry exists

Not because there is work to do, but because it is the one worked example of this
process succeeding, and it establishes both the route and the shape.

`to_reinstall` lets the upgrade transaction reinstall packages whose version
string is identical across major versions but whose contents differ - the case
where dnf would otherwise leave the source-version binary in place. We introduced
it in 2022. AlmaLinux picked it up in June 2024 as part of PR #114, bundled with
the `vendors.d` machinery, and now carries it: `etc/leapp/transaction/to_reinstall`
in `almalinux-ng-0.24.0` is byte-identical to ours, and the mechanism is wired
through the same six files (`filterrpmtransactionevents`, `peseventsscanner`,
`rpmtransactionconfigtaskscollector`, `rhel_upgrade.py`, `dnfplugin.py`,
`rpmtransactiontasks.py`).

Two things this tells us:

- **The route that works is a bundle, not a trickle.** #114 carried the whole
  vendors.d feature set at once, rebased onto a current upstream release, by a
  CloudLinux engineer. That is the precedent for how to deliver the current
  batch.
- **Landing it in AlmaLinux is not the end of the road.** `to_reinstall` exists
  nowhere in oamg's history - `git log -S'to_reinstall' oamg/main` is empty - so
  Red Hat still lacks the mechanism, and it remains offerable there.

## Remaining candidate at oamg

`to_reinstall` on its own is a coherent, self-contained proposal for oamg: a new
`etc/leapp/transaction/` list plus the plumbing to honour it, matching the
existing `to_install` / `to_keep` / `to_remove` pattern exactly. It needs no
vendors.d support and no ELevate concepts.

Worth confirming first that Red Hat does not consider the case already handled by
PES events, which can express a package replacing itself. Our mechanism exists
because PES events are keyed on package *names* changing, and this case has the
same name and version on both sides.

`vendors.d` itself is a different question - it is ELevate's answer to
third-party content on non-RHEL systems, and Red Hat's equivalent concern is
served by RHUI and PES vendor data. Do not bundle the two for oamg.

## At rebase time

Nothing to drop. Our copy and AlmaLinux's are the same code; a rebase onto a ref
containing `6d4f9ea8` should absorb it cleanly. If it conflicts, that is a signal
we have drifted from what AlmaLinux merged and the two should be reconciled -
prefer theirs, so the shared version stays shared.
