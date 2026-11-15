# Only `dnf.conf` is copied into the target userspace, not `/etc/dnf/vars`

## What we do

`copydnfconfintotargetuserspace` copies `/etc/dnf/dnf.conf` and nothing else. Any
repository whose URL interpolates a dnf *variable* therefore cannot resolve
inside the target userspace, because the variable files are not there.

CloudLinux 10 serves the PHP, Python, Ruby and NodeJS Selectors from
subscription-gated repositories whose baseurls carry a token variable -
`$phpelstoken` and three siblings, all symlinks to a single JWT. We added an
actor that copies the token and those variables in via
`TargetUserSpacePreupgradeTasks`, because without them every such repository
returns 401 and the upgrade completes with that content stranded at its old
build, reporting success.

## Why it may be worth upstreaming

Nothing about this is CloudLinux-specific. Any distribution or vendor whose
repositories authenticate through a dnf variable - subscription tokens, mirror
credentials, region selectors - hits the same wall, and hits it *silently*: the
repository is skipped or 401s, packages from it are left at their source-major
builds, and no report names the cause.

Copying `/etc/dnf/vars` alongside `dnf.conf` would cover the general case. The
argument against is that the directory can hold host-specific values that should
not leak into the target container, so a narrower form - copying variables that
appear in an enabled target repository's URL - may be the better shape.

## Status

Not offered upstream yet. Our version is deliberately narrow (four named
variables, guarded on the token existing), so it is a local fix rather than the
general one; the general one is what would need proposing.
