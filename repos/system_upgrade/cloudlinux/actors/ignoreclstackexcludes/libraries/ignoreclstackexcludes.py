import fnmatch
import os
import re

from leapp import reporting
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, TargetUserSpaceInfo

# CloudLinux packages a control panel holds back with a DNF exclude. DirectAdmin's
# custombuild excludes liblsapi, which its mod_lsapi build links, and the CRIU
# tooling liblsapi requires. Their builds for the source system cannot stay on the
# target - the CRIU ones need the source's Python - so the upgrade must replace them.
CL_STACK_PACKAGES = ('liblsapi', 'liblsapi-devel', 'crit-lve', 'criu-lve', 'criu-lve-devel',
                     'python-criu-lve', 'python3-criu-lve')

# Where copydnfconfintotargetuserspace puts the host's dnf.conf in the target userspace.
DNF_CONF = 'etc/dnf/dnf.conf'

_SECTION = re.compile(r'^\s*\[([^\]]+)\]\s*$')
_EXCLUDE = re.compile(r'^(\s*(?:exclude|excludepkgs)\s*=\s*)(.*?)\s*$')


def trim_excludes(text, installed):
    """`text` with the [main] exclude patterns that match a name in `installed` removed.

    Returns (new text, [removed patterns]). Everything else is kept verbatim.
    """
    lines, dropped, section = [], [], None
    for line in text.splitlines(True):
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
        else:
            match = _EXCLUDE.match(line)
            if match and section == 'main':
                patterns = [p for p in re.split(r'[\s,]+', match.group(2)) if p]
                gone = [p for p in patterns if any(fnmatch.fnmatchcase(n, p) for n in installed)]
                if gone:
                    dropped.extend(gone)
                    separator = ', ' if ',' in match.group(2) else ' '
                    line = '{}{}\n'.format(match.group(1), separator.join(p for p in patterns if p not in gone))
        lines.append(line)
    return ''.join(lines), dropped


def process():
    userspace = next(api.consume(TargetUserSpaceInfo), None)
    if userspace is None:
        return
    installed = set()
    for rpms in api.consume(InstalledRPM):
        installed.update(rpm.name for rpm in rpms.items if rpm.name in CL_STACK_PACKAGES)
    path = os.path.join(userspace.path, DNF_CONF)
    if not installed or not os.path.isfile(path):
        return

    with open(path) as f:
        text, dropped = trim_excludes(f.read(), installed)
    if not dropped:
        return
    with open(path, 'w') as f:
        f.write(text)

    api.current_logger().info('Dropped from the target userspace DNF excludes: {}'.format(dropped))
    reporting.create_report([
        reporting.Title('The upgrade ignores DNF excludes that hold back CloudLinux packages'),
        reporting.Summary(
            'The DNF configuration excludes {}, which hold back the installed CloudLinux packages {}.'
            ' Their builds for the current system cannot remain after the upgrade, so the upgrade'
            ' replaces them regardless. Only the upgrade ignores these entries: /etc/dnf/dnf.conf'
            ' is not changed, and they apply to dnf again on the upgraded system.'.format(
                ', '.join(dropped), ', '.join(sorted(installed)))
        ),
        reporting.Severity(reporting.Severity.INFO),
        reporting.Groups([reporting.Groups.REPOSITORY]),
        reporting.RelatedResource('file', '/etc/dnf/dnf.conf'),
    ])
