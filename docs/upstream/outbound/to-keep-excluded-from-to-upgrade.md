# Should `to_keep` suppress upgrades, or only removals?

- **Status:** question - ask upstream before sending a patch
- **Ours:** commit `ec499c51`, in
  `repos/system_upgrade/common/actors/filterrpmtransactionevents/actor.py`
- **Upstream target:** oamg, the same file
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30)

## The difference

Upstream computes the upgrade set as:

```python
to_upgrade = installed_pkgs - (to_install | to_remove)
```

We compute:

```python
to_upgrade = installed_pkgs - (to_install | to_remove | to_keep | to_reinstall)
```

So a package listed in `etc/leapp/transaction/to_keep` is, upstream, still handed
to dnf as something to upgrade. Ours leaves it alone entirely.

## Why this is filed as a question and not a candidate

Because the intended meaning of `to_keep` upstream is genuinely unclear, and the
answer decides whether this is a bug fix or a behaviour change.

Upstream's own file says only *"List of packages (each on new line) to be kept in
the upgrade transaction"* and seeds it with leapp's own packages (`leapp`,
`python2-leapp`, `python3-leapp`, `leapp-repository`, `snactor`). The only other
use is `to_remove.difference_update(to_keep)`. Read one way, "kept" means "not
removed", and upgrading them is intended - leapp's own RPMs do get replaced by
their target-version builds during the transaction, so excluding them from
`to_upgrade` might be wrong for the very packages the file ships with. Read the
other way, a mechanism named "keep" that still rewrites the package is
surprising, and a downstream putting a third-party package in `to_keep` to pin it
would be silently overruled.

We changed it because the second reading is what we needed. That does not make
the first reading a defect.

`to_reinstall` is a separate matter: it is an ELevate-only mechanism (see
`vendors-and-to-reinstall.md`) that does not exist at oamg at all, so that term
of the expression cannot go there regardless.

## How to resolve it

Open a question on the oamg tracker rather than a PR: does `to_keep` mean "do not
remove" or "do not touch"? If the latter, our one-line change is the fix and the
docstring in `etc/leapp/transaction/to_keep` should say so. If the former, we
carry ours knowingly and this entry becomes `declined` - our behaviour is then a
deliberate downstream divergence, and it should be written down as one.
