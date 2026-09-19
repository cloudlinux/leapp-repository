import pytest

from leapp import reporting
from leapp.libraries.actor import checkclmysqltarget
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api
from leapp.models import InstalledMySqlTypes


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
