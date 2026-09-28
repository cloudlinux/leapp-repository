import pytest

from leapp import reporting
from leapp.libraries.actor import checkclmysqltarget
from leapp.libraries.common import clmysql
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api
from leapp.models import FilteredRpmTransactionTasks, InstalledMySqlTypes, InstalledRPM, RPM


@pytest.mark.parametrize('clmysql_type', [
    'mariadb106', 'mariadb1011', 'mariadb1104', 'mariadb1108', 'mysql80', 'mysql84',
])
def test_series_published_for_cl10_are_not_inhibited(monkeypatch, clmysql_type):
    """The six series CloudLinux 10 publishes must pass."""
    _setup(monkeypatch, clmysql_type, target='10')

    checkclmysqltarget.process()

    assert not reporting.create_report.called


@pytest.mark.parametrize('clmysql_type', [
    'mariadb55', 'mariadb100', 'mariadb101', 'mariadb102', 'mariadb103',
    'mariadb104', 'mariadb105', 'mariadb107', 'mariadb108',
    'mysql55', 'mysql56', 'mysql57', 'percona56',
])
def test_series_dropped_in_cl10_inhibit(monkeypatch, clmysql_type):
    """
    Every series CloudLinux 9 carries and CloudLinux 10 does not must inhibit.

    The upgrade would otherwise reach the target transaction with a cl-mysql
    repository that 404s, leaving the database packages unreplaced on a system
    whose base OS has already moved.
    """
    _setup(monkeypatch, clmysql_type, target='10')

    checkclmysqltarget.process()

    assert reporting.create_report.called == 1
    report = reporting.create_report.report_fields
    assert reporting.Groups.INHIBITOR in report['groups']
    assert clmysql_type in report['summary']


def test_governor_short_spelling_is_recognised(monkeypatch):
    """
    Governor re-derives the token from the RPM version and drops the zero padding,
    so the same MariaDB 11.4 installation is spelled mariadb1104 or mariadb114
    (CLOS-6809). Both are published on 10 and neither may inhibit.
    """
    _setup(monkeypatch, 'mariadb114', target='10')

    checkclmysqltarget.process()

    assert not reporting.create_report.called


def test_no_inhibitor_for_targets_that_publish_every_series(monkeypatch):
    """8 and 9 carry the full set, so nothing is checked there."""
    for target in ('8', '9'):
        _setup(monkeypatch, 'mariadb55', target=target)
        checkclmysqltarget.process()
        assert not reporting.create_report.called


def test_unparseable_type_does_not_inhibit(monkeypatch):
    """
    An unrecognised token is not evidence of an unsupported series - it is
    evidence the token is unrecognised. Inhibiting on it would block upgrades
    over a spelling this code has not seen.
    """
    _setup(monkeypatch, 'somethingelse', target='10')

    checkclmysqltarget.process()

    assert not reporting.create_report.called
    assert any('somethingelse' in msg for msg in api.current_logger().warnmsg)


def test_no_clmysql_installed_does_not_inhibit(monkeypatch):
    """A host with no Governor-managed database has nothing to check."""
    _setup(monkeypatch, None, target='10')

    checkclmysqltarget.process()

    assert not reporting.create_report.called


def _setup(monkeypatch, clmysql_type, target):
    types = ['cl-mysql'] if clmysql_type else []
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(
        api, 'current_actor',
        CurrentActorMocked(
            dst_ver='{0}.0'.format(target),
            msgs=[InstalledMySqlTypes(types=types, version=clmysql_type)],
        )
    )


# --- the distribution's own database server -------------------------------------


def _rpm(name, version):
    return RPM(name=name, epoch='1', packager='CloudLinux Packaging Team', version=version,
               release='1.el9_8.cloudlinux.1', arch='x86_64', pgpsig='DSA/SHA256, Key ID 8c55a6628608cb71')


def _run_distro(monkeypatch, installed, to_remove=(), to_install=(), with_tasks=True, target='10.2'):
    msgs = [InstalledRPM(items=[_rpm(n, v) for n, v in installed])]
    if with_tasks:
        msgs.append(FilteredRpmTransactionTasks(to_remove=list(to_remove), to_install=list(to_install)))
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(
        src_ver='9.8', dst_ver=target, msgs=msgs, src_distro='cloudlinux', dst_distro='cloudlinux'))
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    checkclmysqltarget.process()
    return reporting.create_report.reports


# What the 9 -> 10 transaction actually planned for a CloudLinux 9 box with the
# default MySQL: the whole family removed, nothing installed in its place.
MYSQL_REMOVED = ['mysql', 'mysql-common', 'mysql-errmsg', 'mysql-libs', 'mysql-server']


def test_distro_mysql_removed_without_successor_inhibits(monkeypatch):
    reports = _run_distro(monkeypatch, [('mysql-server', '8.0.46')], to_remove=MYSQL_REMOVED)
    assert len(reports) == 1
    report = reports[0]
    assert reporting.Groups.INHIBITOR in report['groups']
    assert 'mysql-server' in report['summary'] and '8.0.46' in report['summary']
    assert 'MySQL' in report['title']


def test_distro_a_successor_in_the_transaction_means_it_is_carried(monkeypatch):
    # The mysql:8.4 module case: PES renames mysql-server to mysql8.4-server.
    reports = _run_distro(monkeypatch, [('mysql-server', '8.4.8')],
                          to_remove=MYSQL_REMOVED, to_install=['mysql8.4-server', 'mysql8.4'])
    assert reports == []


def test_distro_mariadb_removed_without_successor_inhibits_too(monkeypatch):
    reports = _run_distro(monkeypatch, [('mariadb-server', '10.5.29')], to_remove=['mariadb-server'])
    assert len(reports) == 1
    assert 'MariaDB' in reports[0]['title'] and '10.5.29' in reports[0]['summary']


def test_distro_a_successor_from_the_other_family_does_not_count(monkeypatch):
    # Installing MariaDB is not carrying MySQL across - a different database.
    reports = _run_distro(monkeypatch, [('mysql-server', '8.0.46')],
                          to_remove=MYSQL_REMOVED, to_install=['mariadb-server'])
    assert len(reports) == 1


@pytest.mark.parametrize('name', ['cl-MySQL80-server', 'mysql-community-server', 'MariaDB-server'])
def test_distro_governor_and_vendor_variants_are_not_this_check(monkeypatch, name):
    # Their own checks own them; this one is about the distribution's packages.
    reports = _run_distro(monkeypatch, [(name, '8.0.46')], to_remove=[name])
    assert reports == []


def test_distro_a_server_that_stays_is_fine(monkeypatch):
    # 9 -> 10 with the default MariaDB: carried by name, nothing removed.
    assert _run_distro(monkeypatch, [('mariadb-server', '10.5.29')], to_remove=[]) == []


def test_distro_no_transaction_tasks_no_report(monkeypatch):
    assert _run_distro(monkeypatch, [('mysql-server', '8.0.46')], with_tasks=False) == []


def test_distro_mysql_on_9_to_10_gets_the_verified_route(monkeypatch):
    # Verified on CloudLinux 9.8: the mysql:8.4 module stream is what the upgrade
    # renames to CloudLinux 10's mysql8.4-server, and 8.4 aborts on
    # default-authentication-plugin until the configuration is changed.
    report = _run_distro(monkeypatch, [('mysql-server', '8.0.46')], to_remove=MYSQL_REMOVED)[0]
    hint = str(report['detail']['remediations'])
    assert 'dnf module switch-to mysql:8.4' in hint
    assert 'mysql_native_password=ON' in hint and 'default-authentication-plugin' in hint


def test_distro_mariadb_gets_no_mysql_route(monkeypatch):
    report = _run_distro(monkeypatch, [('mariadb-server', '10.5.29')], to_remove=['mariadb-server'])[0]
    assert 'mysql:8.4' not in str(report['detail']['remediations'])


def test_distro_packages_are_defined_once_for_both_actors():
    """Guard: detection and this check read the same definition, in the shared library."""
    assert checkclmysqltarget.DISTRO_DB_SERVERS is clmysql.DISTRO_DB_SERVERS
