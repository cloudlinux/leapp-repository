"""The repoquery the CloudLinux checks run against the target repositories.

Those checks run before the upgrade transaction, to predict what the
transaction will be able to install. A prediction is only worth something if
the query reads the repositories the transaction will read, and the query
therefore runs where the transaction does: inside the target userspace.

The CloudLinux mirrorlist decides that, not the repofile. It answers by the
client's own release, which it reads from dnf's User-Agent, not by the channel
the URL names. dnf on a CloudLinux 8 source sends "CloudLinux 8.10", so
.../cloudlinux-x86_64-server-9.8 comes back as the 8.10 channel; dnf inside the
target userspace sends "CloudLinux 9.8" and gets 9.8. Run through the source
system's dnf with --installroot, the essential-package check saw only el8
builds of lve-stats3 and inhibited every CloudLinux 8 to 9 upgrade over a
package the transaction installs.

--releasever is the target version, as the DNF plugin gives the transaction.
skip_if_unavailable keeps one unreachable repository from failing every query:
the target userspace inherits the source system's repofiles, and a stale one -
cl-mysql, whose baseurl interpolates $releasever and 404s on the target - makes
dnf exit 1 for any query at all.
"""

from leapp.libraries.common import mounting
from leapp.libraries.common.config.version import get_target_version


def query_available(installroot, queryformat, name):
    """stdout of a repoquery for the available builds of `name`.

    Raises what leapp's run raises - CalledProcessError when dnf fails, OSError
    when it cannot be started - for the caller to read as "could not answer".
    """
    cmd = [
        'dnf', '-q', 'repoquery',
        '--releasever={0}'.format(get_target_version()),
        '--setopt=*.skip_if_unavailable=1',
        '--available',
        '--queryformat={0}'.format(queryformat),
        name,
    ]
    with mounting.NspawnActions(base_dir=installroot) as context:
        result = context.call(cmd, split=False)
    return result.get('stdout') or ''
