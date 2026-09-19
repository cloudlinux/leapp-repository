"""Inhibit when the host's database series has no build for the target."""

from leapp import reporting
from leapp.libraries.common.clmysql import parse_clmysql_type
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import InstalledMySqlTypes

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
