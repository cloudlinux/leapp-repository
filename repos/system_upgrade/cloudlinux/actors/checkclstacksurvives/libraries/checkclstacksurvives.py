"""Inhibit when the CloudLinux userland cannot survive the target transaction.

A CloudLinux 9 to 10 run on a stock no-panel box completed, booted, and arrived
with no lve-utils, no cagefs, no lvemanager and no lve-stats - lvectl and
cagefsctl were not on the machine. leapp itself asked for the right thing: its
transaction lists had all of them under to_upgrade and none under to_remove. dnf
erased them while resolving, under the allow_erasing the upgrade transaction
runs with.

The cause was one package. alt-common's el10 branch carried
alt-python-internal 3.11.12-2.el10 while the host ran 3.11.13-2.el9, and dnf
will not move a package backwards. Erasing it took cloudlinux-venv with it
(Requires alt-python-internal >= 3.11, < 3.12), and that took lve-utils, cagefs
and alt-python27-cllib, and those took lve-wrappers and lvemanager. Every other
package in the chain had an el10 build at the installed version.

That is a build gap rather than a code one, and nothing here can conjure a
package that has not been built. What this can do is refuse: an upgrade ending
with LVE and CageFS gone is worse than one that never starts, and the customer
has no way back from it.
"""

import re

import rpm

from leapp import reporting
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api, CalledProcessError, run
from leapp.models import InstalledRPM

# The CloudLinux userland whose loss makes the machine no longer a CloudLinux
# server, plus the substrate it rests on - the substrate is where the CLOS-7051
# regression actually was, so a list of only the user-facing packages would have
# named victims and missed the cause. Only packages actually installed are
# checked, so a no-panel box simply exercises fewer of them.
ESSENTIAL_PACKAGES = frozenset([
    # user-facing
    'cagefs',
    'lve-utils',
    'lvemanager',
    'lve-stats',
    'lve-stats3',
    'lve-wrappers',
    # LVE runtime
    'kmod-lve',
    'liblve',
    'lve',
    'pam_lve',
    # the python substrate the above rest on
    'alt-pylve',
    'alt-python-internal',
    'alt-python-internal-libs',
    'cloudlinux-venv',
])


def _is_target_build(release, target_major):
    """Whether an RPM release string belongs to the target major version.

    The target userspace's repoquery answers from the source repositories as
    well as the target ones, so the installed build comes back as "available".
    Left unfiltered the check compares a package against itself and can never
    fire. Match the dist tag instead: .el10, and .el10.cloudlinux, but not
    .el1 or .el100.
    """
    return re.search(r'\.el{0}(?![0-9])'.format(re.escape(str(target_major))),
                     release or '') is not None


def _evr(epoch, version, release):
    return '{0}:{1}-{2}'.format(epoch or '0', version, release)


def _repoquery(installroot, name):
    """Available (epoch, version, release) for `name` in the target repositories.

    An empty list means either nothing available or a failed query. The caller
    treats both as "no target build", which is the safe direction: it inhibits
    and names the package rather than letting a silent erase through.
    """
    cmd = [
        'dnf', '-q', 'repoquery',
        '--installroot={0}'.format(installroot),
        '--available',
        '--queryformat=%{epoch}|%{version}|%{release}\n',
        name,
    ]
    try:
        result = run(cmd, split=False)
    except (OSError, CalledProcessError) as exc:
        api.current_logger().warning(
            'repoquery for %s in %s failed: %s', name, installroot, exc
        )
        return []
    rows = []
    for line in (result.get('stdout') or '').splitlines():
        line = line.strip()
        if line.count('|') != 2:
            continue
        epoch, version, release = line.split('|')
        rows.append((epoch or '0', version, release))
    return rows


def find_unupgradable(installed_packages, query_fn, target_major=None):
    """Essential packages the target repositories cannot upgrade to.

    Returns a list of (name, installed EVR, best available EVR or None), in the
    order the packages were installed, for every essential package whose best
    available build is older than what is on the system. That is dnf's own rule,
    so this reports exactly the packages dnf would refuse to upgrade - and
    therefore, with allow_erasing, exactly the ones it would erase.
    """
    if target_major is None:
        target_major = get_target_major_version()

    offenders = []
    for pkg in installed_packages:
        if pkg.name not in ESSENTIAL_PACKAGES:
            continue

        installed = (pkg.epoch or '0', pkg.version, pkg.release)
        best = None
        for candidate in query_fn(pkg.name):
            if not _is_target_build(candidate[2], target_major):
                continue
            if best is None or rpm.labelCompare(candidate, best) > 0:
                best = candidate

        if best is None:
            offenders.append((pkg.name, _evr(*installed), None))
        elif rpm.labelCompare(installed, best) > 0:
            offenders.append((pkg.name, _evr(*installed), _evr(*best)))

    return offenders


def process(installroot):
    installed = []
    for rpms in api.consume(InstalledRPM):
        installed.extend(rpms.items)

    offenders = find_unupgradable(
        installed, lambda name: _repoquery(installroot, name)
    )
    if not offenders:
        return

    lines = []
    for name, installed_evr, best_evr in offenders:
        if best_evr is None:
            lines.append('    - {0}: installed {1}, no build in the target repositories'
                         .format(name, installed_evr))
        else:
            lines.append('    - {0}: installed {1}, best available {2}'
                         .format(name, installed_evr, best_evr))

    reporting.create_report([
        reporting.Title(
            'The CloudLinux software stack cannot be upgraded to the target system'
        ),
        reporting.Summary(
            'The target repositories offer no build of the following packages at or'
            ' above the version installed on this system:\n\n{0}\n\n'
            'RPM never moves a package backwards, so the upgrade transaction would'
            ' erase each of them instead - and everything depending on them. In the'
            ' case this check was written for, one such package took lve-utils,'
            ' cagefs, lvemanager and lve-stats with it, leaving a machine with'
            ' neither LVE nor CageFS and no way back.'
            .format('\n'.join(lines))
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.INHIBITOR]),
        reporting.Remediation(
            hint='Wait until the target repositories carry these packages at or above'
                 ' the installed versions, then run the upgrade again. If a package is'
                 ' genuinely discontinued on the target, remove it from this system'
                 ' first so the removal is a decision rather than a side effect.'
        ),
    ])
