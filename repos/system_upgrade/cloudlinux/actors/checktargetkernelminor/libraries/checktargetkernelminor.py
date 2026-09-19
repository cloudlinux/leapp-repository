"""
Detect a target-repository state where the available kernel's minor version
is greater than the available `cloudlinux-release`'s minor version.

This is the gradual-rollout-leak shape behind CLOS-3716 (ZD 268790): the CLN
package channel `cloudlinux-x86_64-server-9` resolves to the latest minor
available to a system's gradual-rollout slot, and a new minor's kernel is
typically promoted ahead of the rest of the userland.  During an in-flight
rollout, elevate can therefore pull a 9.7 kernel onto a 9.6 userland; the
matching kmod-lve is built per kernel minor, so the new default-boot kernel
fails to load kmodlve and breaks LVE.

The actor consuming this library inhibits at Checks phase whenever the
target repositories expose this mismatch, so the upgrade refuses to proceed
while rollout content is in flight.  This is defense in depth - it catches
the leak regardless of which CL repo (CLN channel, no-auth fallback, etc.)
ends up serving the newer-minor kernel.
"""

import re

from leapp import reporting
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import CalledProcessError, api, run


# CloudLinux/RHEL dist-tag with minor version: e.g.
#   611.5.1.el9_7              -> (9, 7)
#   570.12.1.el9_6.x86_64      -> (9, 6)
#   1.0-1.el8_10               -> (8, 10)
#   1.0-1.el8_6.cloudlinux     -> (8, 6)
_DIST_MINOR_RE = re.compile(r'\.el(\d+)_(\d+)(?:\.|$)')

# cloudlinux-release versions are "<major>.<minor>" - e.g. "9.6", "8.10".
_RELEASE_MINOR_RE = re.compile(r'^(\d+)\.(\d+)(?:\.|$)')


def parse_kernel_minor(release_str, target_major):
    """Return the minor version embedded in a kernel RPM release string,
    or None if not present or not for the target major.

    The target-major filter is critical: the target userspace's repoquery
    returns packages from both source (e.g. CL8) and target (e.g. CL9) repos,
    and dist-tagged minors must not be conflated across majors
    (e.g. `el8_10` minor 10 is meaningless when comparing against an
    `el9_*` kernel).
    """
    if not release_str:
        return None
    m = _DIST_MINOR_RE.search(release_str)
    if not m:
        return None
    if int(m.group(1)) != int(target_major):
        return None
    return int(m.group(2))


# CloudLinux 10 dropped minor versions: cloudlinux-release is version "10", not
# "10.2", and there is no per-minor channel. The skew this check guards against -
# the channel serving a kernel from a newer minor than the rest of the userland -
# cannot arise without minors. Without this the check still does nothing, because
# the release-minor parser finds no minor and bails, but it does so by accident.
_FIRST_MAJOR_WITHOUT_MINORS = 10


def _target_has_minor_versions(target_major):
    try:
        return int(target_major) < _FIRST_MAJOR_WITHOUT_MINORS
    except (TypeError, ValueError):
        # An unparseable major is not something to make a decision on; let the
        # rest of the check run and bail on its own terms.
        return True


def parse_release_minor(version_str, target_major):
    """Return the minor version from a cloudlinux-release RPM version field,
    or None if not present or not for the target major.

    See `parse_kernel_minor` for why the major-filter matters.
    """
    if not version_str:
        return None
    m = _RELEASE_MINOR_RE.match(version_str)
    if not m:
        return None
    if int(m.group(1)) != int(target_major):
        return None
    return int(m.group(2))


def _repoquery(installroot, pkg):
    """Query the target userspace container for available versions of `pkg`.

    Returns a list of (version, release) tuples.  Empty list on error or
    nothing available - callers treat absence as "cannot determine" rather
    than as evidence of safety.
    """
    cmd = [
        'dnf', '-q', 'repoquery',
        '--installroot={}'.format(installroot),
        # The target userspace inherits the source system's repofiles, and one
        # stale entry - cl-mysql, whose baseurl interpolates $releasever and
        # 404s on the target - makes dnf exit 1 for every query. Without this
        # the caller then reads an empty list, logs "could not determine both
        # minors" and returns, switching the CLOS-3716 guard off on exactly the
        # kind of untidy box most likely to need it.
        '--setopt=*.skip_if_unavailable=1',
        '--available',
        '--queryformat=%{version}|%{release}\n',
        pkg,
    ]
    try:
        result = run(cmd, split=False)
    except (OSError, CalledProcessError) as exc:
        api.current_logger().warning(
            'repoquery for %s in %s failed: %s', pkg, installroot, exc
        )
        return []
    rows = []
    for line in (result.get('stdout') or '').splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        version, release = line.split('|', 1)
        rows.append((version, release))
    return rows


def _max_kernel_minor(rows, target_major):
    """Highest minor across kernel rows for the target major; None if no row matches."""
    minors = [parse_kernel_minor(release, target_major) for _, release in rows]
    minors = [m for m in minors if m is not None]
    return max(minors) if minors else None


def _max_release_minor(rows, target_major):
    """Highest minor across cloudlinux-release rows for the target major; None if no row matches."""
    minors = [parse_release_minor(version, target_major) for version, _ in rows]
    minors = [m for m in minors if m is not None]
    return max(minors) if minors else None


def _report_inhibitor(target_major, kernel_minor, release_minor):
    reporting.create_report([
        reporting.Title(
            'CloudLinux target repositories are mid gradual-rollout: kernel newer than userland'
        ),
        reporting.Summary(
            'The target CloudLinux repositories currently offer a kernel from minor el{major}_{kminor}'
            ' while the newest available cloudlinux-release is for minor {major}.{rminor}.'
            ' CloudLinux gradual-rollouts typically promote the kernel ahead of the rest of the'
            ' userland, and running the upgrade now would install a kernel newer than the matching'
            ' kmod-lve and other per-kernel-minor packages.  On reboot the new default-boot kernel'
            ' would fail to load kmodlve, breaking LVE.'.format(
                major=target_major, kminor=kernel_minor, rminor=release_minor,
            )
        ),
        reporting.Remediation(
            hint='Re-run the upgrade once the new CloudLinux minor has finished its gradual rollout'
                 ' (target repositories should then offer a cloudlinux-release matching the kernel'
                 ' minor).  Alternatively, pin the target repositories to a single, fully-released minor.'
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([
            reporting.Groups.INHIBITOR,
            reporting.Groups.KERNEL,
            reporting.Groups.REPOSITORY,
            reporting.Groups.UPGRADE_PROCESS,
        ]),
    ])


def process(installroot, query_fn=None, target_major=None):
    """Inhibit when newest available kernel's minor exceeds newest available
    cloudlinux-release's minor in the target userspace's repositories.
    """
    if query_fn is None:
        query_fn = _repoquery
    if target_major is None:
        target_major = get_target_major_version()

    if not _target_has_minor_versions(target_major):
        api.current_logger().info(
            'Skipping kernel-minor check: CloudLinux %s has no minor versions,'
            ' so a kernel cannot be ahead of the userland by one.', target_major,
        )
        return

    kernel_rows = query_fn(installroot, 'kernel-core')
    release_rows = query_fn(installroot, 'cloudlinux-release')

    k_minor = _max_kernel_minor(kernel_rows, target_major)
    r_minor = _max_release_minor(release_rows, target_major)

    if k_minor is None or r_minor is None:
        api.current_logger().info(
            'Skipping kernel-minor check: could not determine both minors'
            ' (kernel=%s, release=%s)', k_minor, r_minor,
        )
        return

    api.current_logger().info(
        'Target userspace: newest kernel-core minor=el%s_%s, newest cloudlinux-release minor=%s.%s',
        target_major, k_minor, target_major, r_minor,
    )
    if k_minor > r_minor:
        _report_inhibitor(target_major, k_minor, r_minor)
