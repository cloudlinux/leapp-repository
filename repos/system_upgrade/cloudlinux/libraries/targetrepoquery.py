"""The repoquery the CloudLinux checks run against the target repositories.

Those checks run before the upgrade transaction, inside the target userspace,
to predict what the transaction will be able to install. A prediction is only
worth something if the query reads the repositories the transaction will read,
and two settings decide that.

--releasever is the target version, which is what the DNF plugin gives the
transaction. The CloudLinux channel is cloudlinux-x86_64-server-$releasever,
and without the option dnf takes $releasever from the target userspace's
release package instead - "9" on CloudLinux 9. cloudlinux-x86_64-server-9 is
frozen with 9.0-era content and has no lve-stats3 at all, while
cloudlinux-x86_64-server-9.8, which the transaction reads, carries fourteen
builds of it. Reading the first, the essential-package check inhibited every
CloudLinux 8 to 9 upgrade over a package the transaction would install.

skip_if_unavailable keeps one unreachable repository from failing every query.
The target userspace inherits the source system's repofiles, and a stale one -
cl-mysql, whose baseurl interpolates $releasever and 404s on the target - makes
dnf exit 1 for any query at all.
"""

from leapp.libraries.common.config.version import get_target_version


def repoquery_cmd(installroot, queryformat, name):
    """The argv for querying the available builds of `name`."""
    return [
        'dnf', '-q', 'repoquery',
        '--installroot={0}'.format(installroot),
        '--releasever={0}'.format(get_target_version()),
        '--setopt=*.skip_if_unavailable=1',
        '--available',
        '--queryformat={0}'.format(queryformat),
        name,
    ]
