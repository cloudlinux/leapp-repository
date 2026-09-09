# CLOS-2816 - cap disk image size to the filesystem file size limit

- **Status:** supersedes-ours (inbound) - upstream capped image size differently, before we did; drop ours at the rebase
- **Ours:** commit `c719cca5` (2026-05-14), `repos/system_upgrade/common/libraries/overlaygen.py`
- **Upstream:** `cef28257` (mhecko@redhat.com, 2024-10-25),
  `lib(overlay): cap the max size of disk images`
- **Checked against:** oamg/main `65ca51d5` (0.25.0, 2026-07-30),
  `AlmaLinux/almalinux-ng-0.24.0`

## The bug we fixed

On a host with a very large partition - the reported case was `/home` on a SAN
with roughly 19 TB free - `target_userspace_creator` sized a sparse disk image to
match, exceeding the 16 TiB maximum file size of ext4 with 4K blocks, and `dd`
failed with exit code 1.

We added `_get_max_diskimage_size_mibs()`, which reads `PC_FILESIZEBITS` via
`os.pathconf()` to derive the filesystem's actual limit, and capped each image to
it.

## Why there is nothing to offer

Upstream had already fixed the same class of failure, seven months before our
patch and two months after our current base. `cef28257` introduced a flat
constant:

```python
_MAX_DISK_IMAGE_SIZE_MB = 2**20  # 1*TB
```

with a docstring that names the concern explicitly - that an image can otherwise
be "virtually larger than the maximum file size supported by the file system" -
and applies it in `_prepare_required_mounts()`. `AlmaLinux/almalinux-ng-0.24.0`
carries it too. Our tree does not, because our base predates it.

Upstream's fix is less precise than ours and better for it: 1 TB is below every
realistic filesystem limit, so it needs no `pathconf` probe, no fallback for when
the probe fails, and no per-filesystem reasoning. The sparse image only needs to
be large enough for the overlay, not proportional to the underlying partition, so
sizing it to a fraction of a 19 TB partition was never useful in the first place.

## At rebase time - drop ours

This is the case the whole directory exists to catch, and it is worth reading as
the worked example.

Once the fork's base includes `cef28257`, both caps will be present, and ours
becomes unreachable dead code: 1 TB is smaller than any value `PC_FILESIZEBITS`
will ever yield, so upstream's branch always fires first. Git will not warn
about this - the two changes are in the same function but not the same lines, so
there is no conflict to resolve. Nothing fails, no test breaks, and a reader a
year later finds two overlapping caps and no way to tell which one is load
bearing.

Delete `_get_max_diskimage_size_mibs()` and its call site, and drop the
`test_overlaygen` cases added by `c719cca5` and `4db4b99e`. Keep upstream's.

## Verifying the claim yourself

```bash
git log -S'_MAX_DISK_IMAGE_SIZE_MB' --format='%h|%ae|%ad|%s' --date=short \
  oamg/main -- repos/system_upgrade/common/libraries/overlaygen.py
git grep -c '_MAX_DISK_IMAGE_SIZE_MB' cloudlinux -- repos/system_upgrade/common/libraries/overlaygen.py
```
