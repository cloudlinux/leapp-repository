import os
import re

from leapp import reporting
from leapp.libraries.common import systemd
from leapp.libraries.stdlib import api, CalledProcessError

FMT_LIST_SEPARATOR = '\n    - '

RC_DIR_GLOB = '/etc/rc.d/rc{}.d'
RUNLEVELS = range(0, 7)

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


def select_shadowed_services(links, service_files):
    """
    Keep only the services whose SysV links are shadowed by a native unit.

    A SysV link is only stale when the target system has a real
    '<name>.service' to take over. Where it does not, the init script is the
    only way that service runs and the links must be left alone.

    :return: Dictionary mapping service name to (link paths, unit state)
    :rtype: dict[str, tuple[list[str], str]]
    """
    states = {
        os.path.basename(service_file.name)[:-len('.service')]: service_file.state
        for service_file in service_files
        if service_file.name.endswith('.service')
    }
    return {
        name: (paths, states[name])
        for name, paths in links.items()
        if name in states
    }


def process():
    links, started_at_boot = collect_sysv_links()
    if not links:
        return

    shadowed = select_shadowed_services(links, systemd.get_service_files())
    if not shadowed:
        return

    removed = []
    enabled = []
    for name, (paths, state) in sorted(shadowed.items()):
        # The SysV link was what started this service at boot, so hand that
        # intent to the native unit before taking the link away. Without this
        # the service would simply stop being started.
        if name in started_at_boot and state != 'enabled':
            try:
                systemd.enable_unit('{}.service'.format(name))
                enabled.append(name)
            except CalledProcessError as err:
                api.current_logger().warning(
                    'Failed to enable {}.service, leaving its SysV links in place: {}'.format(name, err)
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
