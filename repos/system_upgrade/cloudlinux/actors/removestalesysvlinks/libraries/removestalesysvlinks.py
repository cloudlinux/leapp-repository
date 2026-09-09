import os
import re

from leapp import reporting
from leapp.libraries.common import systemd
from leapp.libraries.stdlib import api, CalledProcessError

FMT_LIST_SEPARATOR = '\n    - '

RC_DIR_GLOB = '/etc/rc.d/rc{}.d'
RUNLEVELS = range(0, 7)

# Where a real unit can be shipped or administratively placed. Deliberately NOT
# /run/systemd: that is where systemd-sysv-generator writes the units it makes
# FROM the very links this actor removes. Asking a booted system
# 'is there a <name>.service?' therefore always answers yes for any SysV service
# with an init script, which makes the check circular and the answer worthless.
UNIT_DIRS = ['/usr/lib/systemd/system', '/etc/systemd/system']

# S64mysql / K36mysql -> ('S', 'mysql')
_LINK_RE = re.compile(r'^(?P<action>[SK])(?P<order>[0-9]{2})(?P<name>.+)$')


def _rc_dirs():
    return [RC_DIR_GLOB.format(runlevel) for runlevel in RUNLEVELS]


def parse_link_name(filename):
    """
    Split a SysV runlevel link name into its start/stop action and service name.

    :return: (action, service name), or None when the name is not a runlevel link
    :rtype: tuple[str, str] | None
    """
    match = _LINK_RE.match(filename)
    if not match:
        return None
    return match.group('action'), match.group('name')


def collect_sysv_links(rc_dirs=None):
    """
    Find the SysV runlevel links present on the system.

    :return: Dictionary mapping a service name to the list of link paths, and a
             set of the service names that have at least one start link
    :rtype: tuple[dict[str, list[str]], set[str]]
    """
    links = {}
    started_at_boot = set()
    for rc_dir in rc_dirs if rc_dirs is not None else _rc_dirs():
        try:
            entries = os.listdir(rc_dir)
        except OSError:
            continue
        for entry in entries:
            path = os.path.join(rc_dir, entry)
            if not os.path.islink(path):
                continue
            parsed = parse_link_name(entry)
            if parsed is None:
                continue
            action, name = parsed
            links.setdefault(name, []).append(path)
            if action == 'S':
                started_at_boot.add(name)
    return links, started_at_boot


def scan_unit_providers(unit_dirs=None):
    """
    Map every service name a real unit file provides to the unit providing it.

    A unit provides its own name, and also every name it lists as an Alias in
    its [Install] section - which is how the name a SysV script uses reaches a
    differently named unit. cl-MariaDB103-server is exactly this shape: it ships
    /etc/init.d/mysql and mariadb.service, no mysql.service, and mariadb.service
    carries 'Alias=mysql.service'.

    :return: Dictionary mapping a provided service name to the unit file name
    :rtype: dict[str, str]
    """
    providers = {}
    for unit_dir in unit_dirs if unit_dirs is not None else UNIT_DIRS:
        try:
            entries = sorted(os.listdir(unit_dir))
        except OSError:
            continue
        for entry in entries:
            if not entry.endswith('.service'):
                continue
            path = os.path.join(unit_dir, entry)
            if os.path.islink(path):
                # An alias symlink an earlier 'systemctl enable' created. The
                # unit that actually provides the name is its target.
                providers.setdefault(entry[:-len('.service')],
                                     os.path.basename(os.readlink(path)))
                continue
            if not os.path.isfile(path):
                continue
            providers.setdefault(entry[:-len('.service')], entry)
            for alias in _parse_aliases(path):
                providers.setdefault(alias, entry)
    return providers


def _parse_aliases(path):
    """Return the service names a unit file declares as [Install] Alias."""
    aliases = []
    section = None
    try:
        with open(path) as unit_file:
            for line in unit_file:
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    section = line[1:-1].lower()
                    continue
                if section != 'install' or not line.lower().startswith('alias'):
                    continue
                _, _, value = line.partition('=')
                for name in value.split():
                    if name.endswith('.service'):
                        aliases.append(name[:-len('.service')])
    except (OSError, UnicodeDecodeError):
        return []
    return aliases


def select_shadowed_services(links, providers):
    """
    Keep only the services whose SysV links are shadowed by a real unit.

    A SysV link is only stale when the target system has a real unit to take
    over. Where it does not, the init script is the only way that service runs
    and the links must be left alone.

    :return: Dictionary mapping service name to (link paths, unit to enable)
    :rtype: dict[str, tuple[list[str], str]]
    """
    return {
        name: (paths, providers[name])
        for name, paths in links.items()
        if name in providers
    }


def process():
    links, started_at_boot = collect_sysv_links()
    if not links:
        return

    shadowed = select_shadowed_services(links, scan_unit_providers())
    if not shadowed:
        return

    removed = []
    enabled = []
    for name, (paths, unit) in sorted(shadowed.items()):
        # The SysV link was what started this service at boot, so hand that
        # intent to the real unit before taking the link away. Without this the
        # service would simply stop being started.
        #
        # The unit, never '<name>.service': on the name a SysV script uses,
        # 'systemctl enable' finds no native unit, reports 'redirecting to
        # systemd-sysv-install' and calls chkconfig, which RE-CREATES the very
        # links being removed. Enabling is idempotent, so this does not need to
        # know whether the unit was already enabled - which cannot be read
        # reliably against a target that is not running yet.
        if name in started_at_boot:
            try:
                systemd.enable_unit(unit)
                enabled.append(unit)
            except CalledProcessError as err:
                api.current_logger().warning(
                    'Failed to enable {}, leaving the SysV links for {} in place: {}'.format(unit, name, err)
                )
                continue

        for path in sorted(paths):
            try:
                os.unlink(path)
            except OSError as err:
                api.current_logger().warning(
                    'Failed to remove stale SysV link {}: {}'.format(path, err)
                )
                continue
            removed.append(path)

    if not removed:
        return

    api.current_logger().info('Removed stale SysV runlevel links: {}'.format(', '.join(removed)))

    summary = (
        'The following SysV runlevel links were left over from the previous major version'
        ' while the upgraded system provides a native systemd unit for the same service.'
        ' systemd-sysv-generator turns such a link back into a unit, which then races the'
        ' real one - the service ends up started outside its own unit, and'
        ' "systemctl start <name>" fails against a server that is already running.'
        ' They have been removed:{}{}'.format(FMT_LIST_SEPARATOR, FMT_LIST_SEPARATOR.join(removed))
    )
    if enabled:
        summary += (
            '\n\nThe native units below were enabled first, so the services keep starting'
            ' at boot as their SysV links used to arrange:{}{}'.format(
                FMT_LIST_SEPARATOR, FMT_LIST_SEPARATOR.join(sorted(enabled))
            )
        )

    reporting.create_report([
        reporting.Title('Stale SysV runlevel links were removed'),
        reporting.Summary(summary),
        reporting.Severity(reporting.Severity.MEDIUM),
        reporting.Groups([reporting.Groups.SERVICES]),
    ])
