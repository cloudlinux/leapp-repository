# CLOS-3465 - inhibit when fstab uses _netdev without nofail

- **Status:** candidate
- **Ours:** commits `88a81e5f` (check) and `8ccb119d` (the `nofail` refinement),
  in `repos/system_upgrade/common/actors/checkmountoptions/`
- **Upstream target:** oamg `repos/system_upgrade/common/actors/checkmountoptions/`
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30),
  `AlmaLinux/almalinux-ng-0.24.0`

## What we carry

`check_netdev_mounts()` in the upstream-owned `checkmountoptions` actor. It
inhibits the upgrade when `/etc/fstab` has an entry with the `_netdev` mount
option and *without* `nofail`, listing the offending devices and mountpoints.

## Why upstreamable

This is the strongest candidate in the set: our change extends an actor upstream
already owns, along the axis that actor already documents ("Checks performed:"),
and the failure it prevents has nothing to do with CloudLinux.

The mechanism is generic to leapp itself: during the upgrade the system boots
into the upgrade initramfs with networking down, so a `_netdev` mount cannot be
satisfied, and without `nofail` systemd fails the boot. Any EL7/EL8/EL9 host with
an iSCSI, NFS, or SAN entry in fstab hits it. Nothing about the diagnosis,
the report, or the remediation references CloudLinux, CLN, or a control panel.

Two details that should survive review as-is:

- the `nofail` exemption - `nofail` tells systemd not to fail the boot when the
  mount fails, so those entries are genuinely harmless and inhibiting on them
  would be a false positive;
- the `LEAPP_DEVEL_INITRAM_NETWORK` early return - when the developer has asked
  for networking in the initramfs, the premise of the check does not hold, and
  upstream already uses that variable for exactly this purpose in
  `addupgradebootentry`.

## Upstream form

Essentially as written. `check_mount_options()` already loops over `StorageInfo`
and calls `check_noexec_on_var()`; ours adds a second call beside it. No gating
decorator to remove, no CloudLinux imports, and the actor docstring bullet is
already in the upstream style. The `reporting.Groups` pair
(`FILESYSTEM` + `NETWORK`) matches upstream conventions.

## Evidence upstream does not cover it

`_netdev` appears nowhere in either upstream tree:

```bash
git grep -nI '_netdev' oamg/main -- repos/                      # no output
git grep -nI '_netdev' AlmaLinux/almalinux-ng-0.24.0 -- repos/  # no output
```

Upstream's `checkmountoptions` library contains only the `noexec`-on-`/var`
family (`check_noexec_on_var`, `inhibit_upgrade_due_var_with_noexec`).
