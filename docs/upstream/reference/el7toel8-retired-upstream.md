# Anything el7toel8-only has no upstream home

- **Status:** mapped (reference) - not upstreamable; closes a whole class, not a single change
- **Upstream:** oamg `b6e84f79` (2025-06-04), `Drop el7toel8 leapp repository`
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30),
  `AlmaLinux/almalinux-ng-0.24.0`

## The fact

`repos/system_upgrade/el7toel8/` no longer exists in either upstream. oamg deleted
it on 2025-06-04 and AlmaLinux followed it in their next rebase:

```bash
git ls-tree -r --name-only oamg/main -- repos/system_upgrade/el7toel8/                      # 0 files
git ls-tree -r --name-only AlmaLinux/almalinux-ng-0.24.0 -- repos/system_upgrade/el7toel8/  # 0 files
git ls-tree -r --name-only AlmaLinux/almalinux-ng       -- repos/system_upgrade/el7toel8/   # 366 files (2024-08 ref)
```

RHEL 7 is past end of maintenance, so upstream retired the path. CloudLinux still
supports CL7 to CL8 upgrades commercially, and from 0.24.0 that support lives on its
own branch, `cloudlinux-el7toel8`, cut at `f0a12da4` (0.20.0-13, 2026-10-02) in this
repo and at `e6477677` (0.3-9) in leapp-data. `cloudlinux` builds for CL8 and CL9
only.

Carrying CL7 on `cloudlinux` past the 0.24.0 merge meant keeping shared code
loadable by python2.7 and the leapp CLI by leapp-framework 6.0, both of which
upstream had stopped doing; each merge from them would have broken it again.
`repos/system_upgrade/el7toel8/` is still on `cloudlinux`, unbuilt, until a cleanup
removes it together with the spec's el7 branches.

## What it closes

Any fix that only applies to the EL7 to EL8 path is unupstreamable by
construction - there is no upstream branch to target. It goes to
`cloudlinux-el7toel8` instead. This is not a judgement about
quality. Two examples found in the 2026-07-31 sweep, both of which would
otherwise have been worth sending:

- **CLOS-2132** (`c134cccc`, `2c31a5c3`) - detects an active
  `unix_socket_directories` setting in `postgresql.conf` before upgrading.
  RHEL 7's PostgreSQL 9.2 accepts the plural parameter name via a Red Hat
  back-port; the unpatched 9.2 binary in RHEL 8's `postgresql-upgrade` package
  rejects it, so `postgresql-setup --upgrade` fails after the upgrade and
  PostgreSQL will not start. That is a defect in Red Hat's own packaging, found on
  CloudLinux hosts, affecting every RHEL 7 to 8 upgrade with that line
  uncommented - and there is no longer an `el7toel8/actors/postgresqlcheck/`
  upstream to fix. Neither upstream has the check
  (`git grep -nI 'unix_socket_director'` is empty in both), and neither ever
  will.
- **`3bd823d1`, `23c52335`** - make `NetworkManagerUpdateConnections` emit a
  report instead of dying on `CalledProcessError`. The actor is el7toel8-only.

## Before filing something here

Check whether the same condition also applies to the 8 to 9 path. If it does, the
el8toel9 half *is* upstreamable and should get its own entry - only the el7toel8
half is closed. CLOS-2132 is genuinely el7-specific (it turns on a 9.2-versus-9.2
packaging difference), but that is a conclusion to reach per change, not a
default.

## Consequence for merges

A merge from any current upstream ref presents `repos/system_upgrade/el7toel8/` as
deleted upstream. On `cloudlinux` that deletion can now be taken: nothing builds it.
Nothing merged from upstream needs to stay python2.7-parseable or load on
leapp-framework 6.0 either - that is what moving CL7 to its own branch bought.
