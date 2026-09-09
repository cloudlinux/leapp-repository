# UTF-8 BOM at the start of repomaputils.py

- **Status:** candidate
- **Ours:** commit `cd57f88c`, `repos/system_upgrade/common/libraries/repomaputils.py`
- **Upstream target:** AlmaLinux only - the file does not exist at oamg
- **Checked against:** `AlmaLinux/almalinux-ng-0.24.0`

## What we carry

Removal of a UTF-8 byte order mark (`EF BB BF`) from the first line of
`repomaputils.py`.

## Why upstreamable

AlmaLinux still ships the BOM:

```bash
git show AlmaLinux/almalinux-ng-0.24.0:repos/system_upgrade/common/libraries/repomaputils.py \
  | head -c 12 | od -c
0000000 357 273 277   f   r   o   m       c   o   l   l
```

`357 273 277` is `EF BB BF`. The file is AlmaLinux-owned - `repomaputils.py` is
part of the ELevate `vendors.d` machinery and has no oamg counterpart - so
AlmaLinux is the only possible destination.

This is cosmetic in effect: both CPython 2.7 and 3.x accept a leading BOM in a
source file, so nothing is broken today. It is worth sending anyway because a BOM
in a Python source file is a latent trap - it defeats naive `grep '^from'`, breaks
tools that read the first line positionally, and any editor that strips it
produces a spurious one-line diff for the next contributor. Our own `make lint`
gained a check for exactly this class of problem (`utils/check-non-ascii.py`,
commit `cb7efd8d`), which is how it was noticed.

## Upstream form

A one-byte deletion. If it is worth a second commit, offer the non-ASCII lint
check alongside it - AlmaLinux carries the same Python 2.7 compatibility
constraint for as long as it supports an EL7 source, and that check is what keeps
non-ASCII characters out of files that must parse under 2.7.

## Scale

Small, and honestly labelled as such. It is on the list because it costs nothing
to include in a batch, not because it deserves its own PR.
