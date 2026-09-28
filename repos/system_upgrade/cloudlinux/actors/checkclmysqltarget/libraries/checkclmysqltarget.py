"""Inhibit when the installed database cannot be carried to the target.

Two variants are decided here, each by its own rule: a Governor-managed series
by whether CloudLinux publishes it for the target, and the operating system's
own server by whether the settled transaction removes it with no successor.
Vendor MySQL/MariaDB is decided earlier, in cl_mysql_repository_setup, where
its repository URL is known. A variant is never swapped for another.
"""

import re

from leapp import reporting
from leapp.libraries.common.clmysql import DISTRO_DB_SERVERS, parse_clmysql_type
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import FilteredRpmTransactionTasks, InstalledMySqlTypes, InstalledRPM

# The series published under repo.cloudlinux.com/other/cl<major>/mysqlmeta/,
# as (family, major, minor). CloudLinux 8 and 9 carry the same nineteen; 10
# carries six. Absent majors are treated as "publishes everything", so a new
# target does not start inhibiting before anyone has looked at what it ships.
_PUBLISHED_SERIES = {
    '10': frozenset([
        ('mariadb', 10, 6),
        ('mariadb', 10, 11),
        ('mariadb', 11, 4),
        ('mariadb', 11, 8),
        ('mysql', 8, 0),
        ('mysql', 8, 4),
    ]),
}


def target_publishes_series(clmysql_type, target_major_version):
    """Whether *clmysql_type* has a cl-mysql repository on the target.

    True when the target is not one whose published set is known, so the check
    only ever speaks about a target somebody has enumerated.
    """
    published = _PUBLISHED_SERIES.get(target_major_version)
    if published is None:
        return True

    version = parse_clmysql_type(clmysql_type)
    if version is None:
        # Not a token this code recognises. That is a statement about the
        # token, not about the series, so it must not inhibit - Governor
        # spellings have changed before (CLOS-6809).
        api.current_logger().warning(
            'Could not parse the CloudLinux MySQL type {0!r}; not checking whether'
            ' CloudLinux {1} publishes it.'.format(clmysql_type, target_major_version)
        )
        return True

    return version in published


def process():
    check_governor_series()
    check_distro_server()


def check_governor_series():
    for mysql_types in api.consume(InstalledMySqlTypes):
        clmysql_type = mysql_types.version
        if not clmysql_type:
            continue

        target_major_version = get_target_major_version()
        if target_publishes_series(clmysql_type, target_major_version):
            continue

        reporting.create_report([
            reporting.Title(
                'The installed database has no CloudLinux {0} build'
                .format(target_major_version)
            ),
            reporting.Summary(
                'This system runs the Governor-managed database series {0}, and'
                ' CloudLinux {1} does not publish it: there is no'
                ' cl-mysql repository for it under'
                ' repo.cloudlinux.com/other/cl{1}/mysqlmeta/.\n\n'
                'CloudLinux {1} publishes MariaDB 10.6, 10.11, 11.4 and 11.8,'
                ' and MySQL 8.0 and 8.4. Percona is not published at all.\n\n'
                'Upgrading regardless would move the operating system while'
                ' leaving the database packages behind, on a host whose'
                ' database repository no longer resolves.'
                .format(clmysql_type, target_major_version)
            ),
            reporting.Severity(reporting.Severity.HIGH),
            reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.INHIBITOR]),
            reporting.Remediation(
                hint='Move the database to a series CloudLinux {0} publishes before'
                     ' upgrading, then run the upgrade again.'.format(target_major_version)
            ),
        ])


# --- the operating system's own server --------------------------------------

# A successor of the same family, possibly renamed by version: mysql8.4-server.
_SERVER_RE = re.compile(r'^(?P<family>mysql|mariadb)[0-9.]*-server$')

# A route verified end to end, keyed by (package, target major). On CloudLinux 9.8
# the mysql:8.4 module stream is what the upgrade renames to mysql8.4-server, and
# 8.4 refuses to start until default-authentication-plugin is replaced.
_ROUTES = {
    ('mysql-server', '10'): (
        ' On CloudLinux 9, MySQL 8.4 is available as the mysql:8.4 module stream, and'
        ' the upgrade carries it to CloudLinux 10. MySQL 8.4 refuses to start while'
        ' default-authentication-plugin is set, so first replace'
        ' "default-authentication-plugin=mysql_native_password" in the MySQL'
        ' configuration with "mysql_native_password=ON", which keeps accounts that use'
        ' native passwords working. Then run "dnf module switch-to mysql:8.4", start'
        ' the database and check it before upgrading.'
    ),
}


def _family(name):
    match = _SERVER_RE.match(name)
    return match.group('family') if match else None


def removed_without_successor(tasks):
    """Distribution DB servers the transaction removes with nothing of their family installed."""
    installing = {_family(name) for name in tasks.to_install} - {None}
    return [
        name for name in sorted(DISTRO_DB_SERVERS)
        if name in tasks.to_remove and _family(name) not in installing
    ]


def _installed_version(name):
    for installed in api.consume(InstalledRPM):
        for pkg in installed.items:
            if pkg.name == name:
                return pkg.version
    return 'unknown'


def _report_distro_server(name, version, target):
    product = DISTRO_DB_SERVERS[name]
    reporting.create_report([
        reporting.Title('The installed {0} server cannot be upgraded to CloudLinux {1}'.format(product, target)),
        reporting.Summary(
            'This system runs {product} {version} from the operating system repositories'
            ' (package {name}). CloudLinux {target} provides no successor for it, so the'
            ' upgrade would remove {name} and install nothing in its place, leaving the'
            ' system without a database server. The data in /var/lib/mysql would be kept,'
            ' but nothing would run it.\n\n'
            'Leapp does not switch the database to a different variant, such as a'
            ' CloudLinux MySQL Governor build, on its own.'.format(
                product=product, version=version, name=name, target=target)
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([reporting.Groups.SERVICES, reporting.Groups.INHIBITOR]),
        reporting.Remediation(
            hint='Before upgrading, either move {product} to a version that CloudLinux {target}'
                 ' provides as an operating system package, or remove the {name} package.'
                 '{route}'.format(product=product, target=target, name=name,
                                  route=_ROUTES.get((name, target), ''))
        ),
        reporting.RelatedResource('package', name),
    ])


def check_distro_server():
    tasks = next(api.consume(FilteredRpmTransactionTasks), None)
    if not tasks:
        return
    target = get_target_major_version()
    for name in removed_without_successor(tasks):
        _report_distro_server(name, _installed_version(name), target)
