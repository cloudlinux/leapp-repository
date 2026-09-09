# Preset template instances always expand to `.service`

- **Status:** candidate
- **Ours:** commit `b3d4fd5e`, in
  `repos/system_upgrade/common/libraries/systemd.py` (`_parse_preset_entry`)
- **Upstream target:** oamg, the same file
- **Checked against:** oamg/main `4963bc98` (2026-07-29),
  AlmaLinux `almalinux-ng-0.24.0` `3227e763` (2026-07-10) - both unfixed

## The difference

When a preset entry names instances of a template unit, upstream builds the
instance name with a hardcoded suffix:

```python
service_name = unit_file[:unit_file.index('@') + 1] + instance + '.service'
```

So `enable backup@.timer daily` yields `backup@daily.service` - a name that does
not exist. Ours takes the suffix from the template that actually matched:

```python
unit_type = os.path.splitext(unit_file)[1]
unit_name = unit_file[:unit_file.index('@') + 1] + instance + unit_type
```

## Why upstreamable

It is a plain defect in shared code, with no CloudLinux dimension: the parser
already globs unit files of every type out of the load path (the `TODO` above it
says as much), so a `.timer`, `.socket` or `.path` template can reach this branch
and be attributed to a unit name of the wrong type.

Harmless while presets were consumed only for services - a bogus `.service` key
simply never matched anything. It stops being harmless the moment presets are read
per unit type, which is what `get_system_unit_presets()` does, so upstream will
want it whenever they generalize the preset handling (see
`CLOS-4518-cron-to-timer-preset-migration.md`).

## Honesty about reach

No EL8 or EL9 preset policy declares template instances for a non-service unit.
On a stock CL 9.7 the only `@` entries anywhere under
`/usr/lib/systemd/system-preset/` and `/etc/systemd/system-preset/` are
`enable getty@.service` and `enable getty@tty1.service`, and there are no
template-with-instance-names entries at all. So this fixes nothing observable
today on any supported path - it is a latent correctness fix, and should be
offered as one rather than dressed up as a bug with user impact.

## Upstream form

Take the diff as-is; it is three lines and a comment. The test fixture matters
more than the code: add a `.timer` template to
`common/libraries/tests/test_systemd_files/` and a parametrized
`_parse_preset_entry` case, and remember that adding a fixture to that directory
changes the expectations of the `disable *` case and of `test_parse_preset_files`,
because both glob the whole directory.

## What we did not take

The review that surfaced this (PR #69, finding 3) also asked for
preset-declared *instances* to be included in candidate selection, on the grounds
that `systemctl list-unit-files` may not list an unenabled instance. We declined:
template instances have no unit file at all, so they are outside anything built on
`list-unit-files`, and covering them means enumerating instances from preset files
themselves. That is a larger change with no current driver - see the reach note
above. If upstream generalizes preset handling they will have to decide this
anyway; flag it to them rather than solving it here.
