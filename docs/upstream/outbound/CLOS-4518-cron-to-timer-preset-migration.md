# CLOS-4518 - timers left disabled by a cron-to-timer migration

- **Status:** candidate (outbound) - and see the inbound hazard below, which is the urgent half
- **Ours:**
  - `repos/system_upgrade/cloudlinux/models/systemdtimers.py`
  - `repos/system_upgrade/cloudlinux/actors/scansystemdtimerssource/`
  - `repos/system_upgrade/cloudlinux/actors/enablemigratedtimers/`
  - `repos/system_upgrade/common/actors/systemd/transitionsystemdservicesstates/`
    (commit `3cf318e2` - honor the target preset for units absent on the source;
    `451d923e` - keep excluding the libvirt group once that path exists)
- **Upstream target:** oamg - `common/` for the transition change, and our timer
  pair as a **replacement for** `el8toel9/actors/enablelogrotatetimer`
- **Checked against:** oamg/main `4963bc98` (2026-07-29),
  AlmaLinux `almalinux-ng-0.24.0` `3227e763` (2026-07-10)

## What we carry

Three things, of which only the first is CloudLinux-shaped:

1. `scansystemdtimerssource` (FactsPhase) records the source system's timer unit
   inventory into `SystemdTimersInfoSource`; `enablemigratedtimers` (FirstBoot)
   enables a timer only when it is **absent on the source, `disabled` on the
   target, and preset-enabled on the target**.
2. `transitionsystemdservicesstates` stops dropping units that do not exist on
   the source, and applies the target vendor preset to them.
3. `systemd.get_system_unit_presets(suffix)`, because
   `get_system_service_preset_files()` is `.service`-only and model-bound.

## Why upstreamable

The mechanism is upstream's, end to end, and nothing about it is CloudLinux-specific:

- A package that already exists on the source and *gains* a unit on the target
  never gets that unit's preset applied, because `%systemd_post` is guarded by
  `[ $1 -eq 1 ]` - initial install only.
- leapp's own systemd state transition cannot compensate, because
  `common/libraries/systemd.py` scans with `_SYSTEMCTL_CMD_OPTIONS =
  ['--type=service', ...]` and `get_system_service_preset_files()` emits presets
  only for names ending in `.service`. Timers, sockets and paths are structurally
  invisible to the whole mechanism.

On EL8 -> EL9 that silently breaks **two** packages, not one. A package-level diff
of EL8 (AlmaLinux 8.10) against CL 9.7 unit inventories and preset policy, across
all 14 EL8 packages shipping cron entries, found exactly these:

| Package | EL8 | EL9 | Consequence |
|---|---|---|---|
| `logrotate` | `/etc/cron.daily/logrotate` | `logrotate.timer`, preset `enable` | nothing rotates logs |
| `mdadm` | `/etc/cron.d/raid-check`, active by default (`0 1 * * Sun`) | `raid-check.timer`, preset `enable` - a **new** line in the EL9 policy | the weekly software-RAID consistency scrub never runs |

`raid-check` is the one worth leading with upstream: there is no disk-full symptom
to notice, so latent sector errors accumulate silently until an array rebuild hits
an unrecoverable read error. No fallback exists - `mdcheck_start.timer`,
`mdcheck_continue.timer` and `mdmonitor-oneshot.timer` are all disabled by default.

Everything else came out clean: `rear` -> `rear.timer` is not preset-enabled (a
fresh EL9 leaves it off too); `logwatch` ships both a cron entry and a timer;
cronie / cyrus-imapd / man-db-cron / rpm-cron / opa-fastfabric keep their cron
entries; mailman / PackageKit-cron / rhn-virtualization-host do not exist in EL9.

## Upstream already solved the narrow case - and that is the problem

oamg PR **1501** (merged 2026-03-03, Jira RHEL-17361) added
`el8toel9/actors/enablelogrotatetimer`: a FinalizationPhase actor whose entire
body is

```python
LOGROTATE_TIMER = 'logrotate.timer'
def process():
    try:
        enable_unit(LOGROTATE_TIMER)
```

Ours is a strict superset on three axes, and the differences are the argument:

- **Coverage.** Theirs names one timer. It misses `raid-check.timer` - the same
  gap a hardcoded list of ours had, which is why we replaced the list with a rule.
- **Administrator intent.** Theirs is unconditional: it re-enables
  `logrotate.timer` even where the administrator deliberately disabled it on the
  source. Ours cannot, by construction - a unit absent from the source inventory
  is the only thing it will touch, and `logrotate.timer` is absent on EL8 exactly
  because EL8 has no such unit.
- **Generality.** Any future cron-to-timer migration is covered by the rule
  without a code change; theirs needs a new hardcoded actor each time.

So the offer to upstream is "replace `enablelogrotatetimer` with the general
rule", not "add another timer actor beside it".

## Two inbound hazards come out of this

Both have their own entries, because the action belongs where a rebase looks:

- [../inbound/enablelogrotatetimer.md](../inbound/enablelogrotatetimer.md) -
  their narrow actor arrives as a clean add and silently voids the
  administrator-intent guarantee described above. Delete it at the rebase.
- [../inbound/transitionsystemdservicesstates-oamg-1571.md](../inbound/transitionsystemdservicesstates-oamg-1571.md) -
  an open upstream PR rewrites the same library our `3cf318e2` / `451d923e`
  change. Rebuild ours on top of theirs if it lands.

## Upstream form

- The transition-actor change goes to `common/` unmodified; it is already
  generic and has no CloudLinux gate.
- The timer pair needs the `@run_on_cloudlinux` gates dropped, and is better
  placed as one actor pair in `common/` (source scan + FirstBoot apply) than in
  `el8toel9/`, since the mechanism is version-pair-independent - it is a property
  of RPM scriptlet semantics, not of 8->9.
- The cleanest upstream shape is arguably to stop treating this as a timer
  problem at all: extend the systemd scan and preset emitter to every unit type
  and let the existing transition handle timers, sockets and paths uniformly. We
  deliberately did **not** do that here - it touches shared scan + preset code
  used by every upgrade, and the regression surface was not worth it for a
  customer-facing fix. Upstream is the right place to take that on, and if they
  do, our pair becomes obsolete rather than upstreamed. Say so when offering.
