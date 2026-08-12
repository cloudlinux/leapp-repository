# target_userspace_creator: honour reposdir when placing repository files

**Status:** not yet proposed upstream.
**Touches:** `repos/system_upgrade/common/actors/targetuserspacecreator/libraries/userspacegen.py`
**Found via:** CLOS-4690, but not CloudLinux-specific.

## The bug

A system whose dnf configuration sets a non-default `reposdir` cannot be
upgraded. The run ends with the inhibitor *"There are no enabled target
repositories"* and the error *"Could not check for valid GPG keys: No
UsedTargetRepositories facts"*, even though the target repositories were
resolved correctly earlier in the run.

`userspacegen` writes repository files to a hardcoded `/etc/yum.repos.d` in
three places, but everything that later reads them is reposdir-aware:

* `_install_custom_repofiles()` copied into `/etc/yum.repos.d` of the scratch
  container - that is where `leapp_upgrade_repositories.repo`,
  `vendors.d/*.repo` and every `CustomTargetRepositoryFile` land.
* `_prep_repository_access()` used `<target_userspace>/etc/yum.repos.d` for the
  backup/restore dance and as the `copytree_from` destination.
* Discovery goes through `_get_all_available_repoids()` ->
  `repofileutils.get_parsed_repofiles()` -> `get_repodirs()`, which returns
  `dnf.base.Base().conf.reposdir`.

The scratch container is an overlay over the host root, and the target
userspace receives a copy of the host's `/etc/dnf/dnf.conf`, so in both the
container's dnf reads the host's `reposdir`. When that is not
`/etc/yum.repos.d`, leapp writes the repository files where neither its own
discovery nor the `--enablerepo` dnf calls will look.

This affects the stock `leapp_upgrade_repositories.repo` too, so it is not
limited to custom or vendor repositories.

## Reproducing without CloudLinux

On any el8 system with leapp configured for an upgrade:

```bash
mkdir -p /etc/yum.repos.alt.d
mv /etc/yum.repos.d/*.repo /etc/yum.repos.alt.d/
echo 'reposdir=/etc/yum.repos.alt.d' >> /etc/dnf/dnf.conf
leapp preupgrade
```

In `/var/log/leapp/leapp-preupgrade.log` the contradiction is visible directly:
a `Copying ... to /etc/yum.repos.d/...` line, then a
`find -L /etc/yum.repos.alt.d ... -name *.repo`, then an empty
`Gathered target repositories:`.

## The fix

Add `_get_container_repofile_dir()`, which returns the directory the
container's dnf actually reads - `/etc/yum.repos.d` when that is among the
configured `reposdir` entries (so standard systems are unaffected), otherwise
the configured one, sorted for a stable pick because `get_repodirs()` builds
its result from a set. Use it in `_install_custom_repofiles()` and throughout
`_prep_repository_access()`.

`_prep_repository_access()` additionally has to create the directory in the
freshly installed userspace: only the distro default exists there, so the
`mv` of the target directory fails with `FileNotFoundError` otherwise.

Fixing the write side rather than the discovery side is deliberate: it also
makes the repositories visible to the `--enablerepo` dnf calls inside the
container, which read `reposdir` and would still have missed files placed in
`/etc/yum.repos.d`.

### Approach that does not work

Stripping `reposdir` from the `dnf.conf` that
`copy_dnf_conf_into_target_userspace` copies in looks attractive - the
container is a fresh root whose repository files leapp manages itself - but it
cannot fix the gathering stage. `_gather_target_repositories()` runs *before*
`_create_target_userspace()` and operates on the scratch overlay, whose
`/etc/dnf/dnf.conf` is the host's file by virtue of the overlay, not by that
copy. It would also leave the `--enablerepo` calls broken.

Should anyone revisit that idea: the stripped copy must **not** be written to
`/etc/leapp/files/dnf.conf`, even though `copy_dnf_conf_into_target_userspace`
prefers that path, because `apply_custom_dnf_conf` later *moves* that file onto
the upgraded system (`run(["mv", CUSTOM_DNF_CONF_PATH, "/etc/dnf/dnf.conf"])`),
silently rewriting the host's own configuration after the upgrade.

## Open question

The backup/restore dance in `_prep_repository_access()` exists to preserve
repository files owned by RPMs. Those are installed to `/etc/yum.repos.d` by
the packages themselves regardless of `reposdir`, so pointing the dance at the
configured directory means the target distro's stock repository files are
neither preserved nor active on a custom-reposdir system. Harmless for the
upgrade transaction, which drives everything through explicit `--enablerepo`,
but it leaves such a system without the new distro's stock repository
definitions in an active location. Whether those should be copied across is
unresolved.

## Verification

Reproduced and fixed on a CloudLinux 8.10 VM with a relocated `reposdir`.
After the fix `leapp preupgrade` reaches zero inhibitors, `UsedTargetRepositories`
is populated, and the target userspace downloads metadata from every target
repository.
