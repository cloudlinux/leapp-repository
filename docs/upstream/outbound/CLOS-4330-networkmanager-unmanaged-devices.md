# CLOS-4330 - NetworkManager configured to manage no device

- **Status:** candidate
- **Ours:** `repos/system_upgrade/cloudlinux/actors/checknetworkmanagerunmanaged/`
- **Upstream target:** oamg `repos/system_upgrade/el8toel9/actors/checkifcfg` (extend)
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30)

## What we carry

A `ChecksPhase` actor that inhibits the upgrade when a keyfile under
`/etc/NetworkManager/conf.d` sets `unmanaged-devices=*`.

## Why upstreamable

The gap is upstream's own. `el8toel9/actors/checkifcfg` already inhibits on
`NM_CONTROLLED=no` in ifcfg files, but never reads `conf.d`, where the same
"do not manage this device" intent can be expressed - and, since EL9 ships no
`network-scripts`, the ifcfg check is gated on a package that will not be there.

EL9 drops `network-scripts` entirely, so on RHEL and AlmaLinux the consequence is
identical to ours: nothing brings the interface up after the reboot and the host
is reachable only from the console. Nothing in the check is CloudLinux-specific.

## Upstream form

Fold into `checkifcfg`, or a sibling actor beside it, in `el8toel9`. Then:

- drop the `@run_on_cloudlinux` gate;
- drop our explicit `get_target_major_version()` guard - it exists only because
  `repos/system_upgrade/cloudlinux/` loads on *every* upgrade path, whereas
  `el8toel9/` is already scoped;
- keep the OpenNebula `one-context` provenance as an example, not as the premise.

## Note on why this one is offerable at all

It is upstreamable *because* the design reports rather than mutates. An earlier
revision renamed the offending file during `FinalizationPhase`. Upstream would
not accept an actor that silently edits network configuration, and that version
would have been fork-only forever. The auto-repair now lives in the elevate-qa
Ansible test setup, where deciding for the operator is appropriate.
