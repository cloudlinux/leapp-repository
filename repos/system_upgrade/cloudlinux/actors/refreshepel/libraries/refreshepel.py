import os
import re

from leapp import reporting
from leapp.libraries.common.backup import backup_file_in_place, LEAPP_BACKUP_SUFFIX
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.common.rpms import has_package
from leapp.libraries.stdlib import api, run
from leapp.models import InstalledRPM

REPO_DIR = '/etc/yum.repos.d'
RPMNEW = '.rpmnew'
EPEL_RELEASE = 'epel-release'
EPEL_RELEASE_URL = 'https://dl.fedoraproject.org/pub/epel/epel-release-latest-{}.noarch.rpm'

_SECTION = re.compile(r'^\s*\[([^\]]+)\]\s*$')
_ENABLED = re.compile(r'^\s*enabled\s*=\s*(\S+)\s*$')


def _enabled_by_section(text):
    states, section = {}, None
    for line in text.splitlines():
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
            continue
        match = _ENABLED.match(line)
        if match and section is not None:
            states[section] = match.group(1)
    return states


def _carry_enabled(text, states):
    lines, section = [], None
    for line in text.splitlines(True):
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
        elif section in states and _ENABLED.match(line):
            line = 'enabled={}\n'.format(states[section])
        lines.append(line)
    return ''.join(lines)


def _replace_with_rpmnew():
    """
    Put the target epel-release's repo files in place of the source system's.

    rpm keeps a repo file that was edited (dnf config-manager --set-enabled is
    enough) and writes the target one beside it as .rpmnew. The kept file still
    names the source release's repositories and GPG key. The admin's choice of
    enabled repositories is carried over; the old file is kept as .leapp-backup.
    """
    replaced = []
    for name in sorted(os.listdir(REPO_DIR)):
        if not (name.startswith('epel') and name.endswith('.repo' + RPMNEW)):
            continue
        rpmnew = os.path.join(REPO_DIR, name)
        path = rpmnew[:-len(RPMNEW)]
        with open(rpmnew) as f:
            text = f.read()
        if os.path.exists(path):
            with open(path) as f:
                text = _carry_enabled(text, _enabled_by_section(f.read()))
            backup_file_in_place(path)
        with open(path, 'w') as f:
            f.write(text)
        os.unlink(rpmnew)
        replaced.append(path)
    return replaced


def _installed_version():
    result = run(['rpm', '-q', '--queryformat', '%{VERSION}', EPEL_RELEASE], checked=False)
    return result['stdout'].strip() if result['exit_code'] == 0 else None


def process():
    if not has_package(InstalledRPM, EPEL_RELEASE):
        return

    target = get_target_major_version()
    version = _installed_version()
    if version != target:
        # This runs in the upgrade environment, which has no network to fetch
        # the right package from; leave the system's EPEL as it is and say so.
        url = EPEL_RELEASE_URL.format(target)
        reporting.create_report([
            reporting.Title('EPEL was not upgraded to the new system version'),
            reporting.Summary(
                'The epel-release package {} the upgrade, so the EPEL repositories still'
                ' belong to the previous system version, or are missing.'.format(
                    'was removed during' if version is None else 'was not upgraded by')
            ),
            reporting.Severity(reporting.Severity.HIGH),
            reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.POST]),
            reporting.Remediation(hint='Install the EPEL release package for this system version.',
                                  commands=[['dnf', 'install', '-y', url]]),
            reporting.RelatedResource('package', EPEL_RELEASE),
        ])
        return

    replaced = _replace_with_rpmnew()
    if replaced:
        api.current_logger().info('EPEL repository files replaced by the target ones: {}'.format(replaced))
        reporting.create_report([
            reporting.Title('EPEL repository files replaced by the new system version'),
            reporting.Summary(
                'These EPEL repository files had been edited, so the upgrade installed the new'
                ' versions beside them as .rpmnew. They are now in place, with each repository'
                ' enabled or disabled as before; the old files are kept with the {} suffix: {}'.format(
                    LEAPP_BACKUP_SUFFIX, ', '.join(replaced))
            ),
            reporting.Severity(reporting.Severity.INFO),
            reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.POST]),
        ])
