# CLOS-6911 - SysV runlevel links that shadow a real unit survive the upgrade

- **Status:** candidate (outbound)
- **Ours:**
  - `repos/system_upgrade/cloudlinux/actors/removestalesysvlinks/`
    (merged in PR #72 as `79137c8c`, reworked by `1bf24540` and `f1ac70f9`)
- **Upstream target:** oamg - `common/`, as a new FinalizationPhase.After actor.
  Nothing it relies on is version-pair or distro specific.
- **Checked against:** oamg/main `439ab177` (2026-09-01),
  AlmaLinux `almalinux-ng` `8c776416` (2024-08-22). Neither carries anything for
  SysV or chkconfig leftovers: grepping both for `rc[0-9].d|chkconfig|sysv` across
  `repos/` returns three files, all false positives (`sysv` as a filesystem type
  in `overlaygen.py`, `sysvipc` in `dnfplugin.py`, a test fixture).

## What we carry

One FinalizationPhase.After actor. It removes `/etc/rc.d/rc*.d/[SK]NNname` links
whose service has a real unit on the target, enables that unit first when a start
link existed, and leaves everything else alone.

## Why it is a problem at all

The runlevel links `chkconfig` created on the source belong to **no package**, so
nothing removes them during the upgrade. On the target, `systemd-sysv-generator`
turns a surviving link back into an LSB compatibility unit that races the real
one. `cl-MariaDB103-server` is the case that surfaced it: it ships
`/etc/init.d/mysql` on EL9 too, the EL8 links survive, and MariaDB ends up started
by `mysqld_safe` outside `mariadb.service` - so `systemctl start mariadb` fails
against a server that is already running, and the init script is itself broken on
EL9 where `log_success_msg` no longer exists.

## Why upstreamable

This is the third face of one upstream blind spot, and the first two are already
in this register. `common/libraries/systemd.py` scans with

    _SYSTEMCTL_CMD_OPTIONS = ['--type=service', '--all', '--plain', '--no-legend']

so the whole systemd-state mechanism sees only `.service` units.
[CLOS-4518](CLOS-4518-cron-to-timer-preset-migration.md) is the `.timer` half.
This is the SysV half, and it is worse than invisible: these are not units at all
but files under `/etc/rc.d/rc*.d`, so no unit-based scan can ever reach them.

Nothing about it is CloudLinux-specific in principle. Any distribution with a
package shipping both an init script and a unit can hit it. Independent evidence
that it is not ours alone: Plesk's own `almalinux8to9` converter carries
`StopStartServices(["logrotate.timer"], disable_on_prep=False)` - a tool-level
workaround for the `.timer` half, on AlmaLinux, added 2026-08-21.

## Two properties an upstream version has to keep

Both were found by driving real conversions, and an earlier revision had each
of them wrong.

1. **It cannot run on FirstBoot.** By then `systemd-sysv-generator` has already
   read the links and started the service, so removal takes effect only one boot
   later - and on a Plesk conversion the finish stage fails before that boot.

2. **It cannot run in FinalizationPhase *Main* either.** `set_systemd_services_state`
   applies its disables in that stage, and leapp orders actors within a stage only
   by produce/consume edges (`PhaseActors._sort`); an actor that consumes nothing
   and produces only a `Report` is unordered against it. Measured 19 of 20
   workflow constructions with ours first, and then:

       21:38:55.163 remove_stale_sysv_links:    systemctl enable  mariadb.service
       21:38:55.891 set_systemd_services_state: systemctl disable mariadb.service

   The enable is undone, the S links are already gone, and nothing starts the
   database at boot. `FinalizationPhaseTag.After` is the fix.

That second point also explains a detail of the original incident that looked
inexplicable: the EL9 `cl-MariaDB103-server` `%posttrans` recreates the
`mysql.service` / `mysqld.service` alias links and enables `mariadb.service`
unconditionally, so the transition sees the unit enabled against a disable preset
and emits `to_disable=[mariadb.service]`. Applying that disable removes the
WantedBy link **and both alias symlinks** - which is what lets the generator build
a `mysql.service` from the init script in the first place.

## Do not verify it from the end state of a converted host

On a Plesk conversion the finish stage re-enables and starts the database, so a
host whose actor did nothing useful still ends up with `mariadb.service` active
and enabled. The ticket symptom disappears while the defect is intact - it cost a
full run's verification here. The evidence that distinguishes them is the
`WantedBy` symlink's mtime against `uptime -s`: written during Finalization it
predates the boot; written by the panel's finish stage it does not.
