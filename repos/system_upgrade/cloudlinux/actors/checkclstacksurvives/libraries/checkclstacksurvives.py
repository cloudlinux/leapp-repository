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


from leapp import reporting
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.common.targetrepoquery import query_available
from leapp.libraries.stdlib import api, CalledProcessError
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

    Returns None when the query could not be answered, which is not the same as
    an empty list: an empty list is a real absence, None is ignorance. The
    distinction matters because a single unrelated repository can break the
    whole query - on the box this was validated against, a stale cl-mysql
    repofile whose baseurl interpolates $releasever 404d on the target and made
    every query exit 1. Read as "no build", that named all fourteen essential
    packages when one was genuinely behind.

    query_available keeps such a repository from taking the query down in the
    first place; None is what is left when something else does.
    """
    try:
        stdout = query_available(installroot, '%{epoch}|%{version}|%{release}\n', name)
    except (OSError, CalledProcessError) as exc:
        api.current_logger().warning(
            'repoquery for %s in %s failed: %s', name, installroot, exc
        )
        return None
    rows = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.count('|') != 2:
            continue
        epoch, version, release = line.split('|')
        rows.append((epoch or '0', version, release))
    return rows


def find_unupgradable(installed_packages, query_fn, target_major=None):
    """The offenders alone; see evaluate() for the indeterminate ones too."""
    return evaluate(installed_packages, query_fn, target_major)[0]


def evaluate(installed_packages, query_fn, target_major=None):
    """Essential packages the target repositories cannot upgrade to.

    Returns (offenders, indeterminate).

    `offenders` is a list of (name, installed EVR, None) for every essential
    package with **no target build at all**. Such a package cannot be carried
    over: leapp marks it for upgrade, nothing satisfies the job, and
    allow_erasing turns that into an uninstall.

    A target build that is merely *older* is deliberately not an offender. leapp
    sets allowdowngrade and issues a distupgrade job - one real run performed 33
    downgrades - so it moves packages backwards across the major boundary as a
    matter of course. Measured: with alt-python-internal-3.11.13-2.el9 installed
    and only 3.11.12-2.el10 available, the solver took the el10 build and the
    whole CloudLinux stack came through. An earlier version of this check
    inhibited on that and would have blocked every such upgrade.

    `indeterminate` names the packages whose query could not be answered at all.
    Those are not offenders: a failed query is a statement about the query.
    """
    if target_major is None:
        target_major = get_target_major_version()

    offenders = []
    indeterminate = []
    for pkg in installed_packages:
        if pkg.name not in ESSENTIAL_PACKAGES:
            continue

        installed = (pkg.epoch or '0', pkg.version, pkg.release)
        available = query_fn(pkg.name)
        if available is None:
            indeterminate.append(pkg.name)
            continue

        if not any(_is_target_build(candidate[2], target_major) for candidate in available):
            offenders.append((pkg.name, _evr(*installed), None))

    return offenders, indeterminate


def process(installroot):
    installed = []
    for rpms in api.consume(InstalledRPM):
        installed.extend(rpms.items)

    offenders, indeterminate = evaluate(
        installed, lambda name: _repoquery(installroot, name)
    )
    if indeterminate:
        api.current_logger().warning(
            'Could not determine target availability for: %s. Those packages are'
            ' not covered by this check.', ', '.join(sorted(indeterminate))
        )
    if not offenders:
        return

    lines = []
    for name, installed_evr, best_evr in offenders:
        if best_evr is None:
            lines.append('    - {0}: installed {1}'.format(name, installed_evr))
        else:
            lines.append('    - {0}: installed {1}, best available {2}'
                         .format(name, installed_evr, best_evr))

    reporting.create_report([
        reporting.Title(
            'The CloudLinux software stack cannot be upgraded to the target system'
        ),
        reporting.Summary(
            'The target repositories offer no build at all of the following'
            ' packages:\n\n{0}\n\n'
            'leapp marks each installed package for upgrade; with nothing to satisfy'
            ' that job, allow_erasing turns it into an uninstall instead - silently,'
            ' and taking everything that depends on it. A CloudLinux 9 to 10 run'
            ' lost lve-utils, cagefs, lvemanager and lve-stats that way and still'
            ' reported success.'
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
