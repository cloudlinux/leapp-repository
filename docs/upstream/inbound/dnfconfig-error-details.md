# Surface dnf output when setting the dnf configuration fails

- **Status:** supersedes-ours (inbound) - upstream implemented the same thing, better, on 2026-04-24; take theirs
- **Ours:** commit `e6895c85` (dshibut@cloudlinux.com, 2025-01-10), in
  `repos/system_upgrade/common/libraries/dnfconfig.py`
- **Upstream:** `bcc445b1` (pstodulk@redhat.com, 2026-04-24),
  `dnflibs.dnfconfig: Raise proper exceptions and add tests`
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30)

## What we carry

In `_set_excluded_pkgs()`, a failed `dnf config-manager` call raises a
`StopActorExecutionError` carrying the command, the exception, and the captured
`stdout` and `stderr`, instead of logging one line and re-raising the bare
`CalledProcessError`.

## Why there is nothing to offer

Upstream reached the same conclusion and went further. `bcc445b1` introduced
dedicated exception types - `CannotObtainDNFConfig`, `InvalidDNFConfig`,
`CannotUpdateDNFConfig` - each raised with
`details={'stdout': e.stdout, 'stderr': e.stderr}`, and added tests. That is a
strictly better version of our change: callers can distinguish *which* dnf step
failed, where ours only distinguishes it by message text.

We had the fix roughly fifteen months earlier and never offered it. That is the
concrete cost of not having kept this list before now, and the reason the list
exists: convergence is the likely outcome for any generic fix we sit on, and we
get none of the credit and all of the rebase work.

## At rebase time

Take upstream's. Our `_set_excluded_pkgs()` hunk will conflict with `bcc445b1`;
resolve by deleting ours. Two related notes for the same file:

- Upstream has moved the module to
  `repos/system_upgrade/common/libraries/dnflibs/dnfconfig.py` (`9e165750`,
  2026-03-10), leaving a thin shim at the old path. **This is the trap the README
  warns about, and it caught this very entry:** grepping the old path shows a
  shim with no error handling at all, which reads as "upstream does not do this."
  Search the tree by content, not by path.
- Our copy of `_get_main_dump()` lacks the blank-line skip and assigns
  `output_data[key]` outside the `try`. That is upstream's *older* code, fixed
  upstream by `9b06998b` (pmocary@redhat.com, 2025-11-10, `fix parsing of dnf
  config dump`). We are behind, not diverged - do not offer it back, and take
  upstream's on rebase. In our copy, a line that fails `_strip_split()` currently
  re-stores the *previous* iteration's key/value pair.

Only the `_set_excluded_pkgs()` half of `e6895c85` is covered here. The same
error shape also appears in our `_set_repository_state()`, which is our own
function and travels with `../outbound/restore-repository-states.md`.
