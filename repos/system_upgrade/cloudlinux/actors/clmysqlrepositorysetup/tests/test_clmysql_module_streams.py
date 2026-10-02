"""Governor databases come from DNF module streams on 8 and 9, and plain packages on 10.

The cl8/cl9 cl-mysql-meta repositories carry modules metadata; the cl10 ones carry
none, and neither does anything else on CloudLinux 10. Requesting a stream there
did nothing - the dnf plugin logs "requested to be enabled, but they are
unavailable" and moves on - so it only produced a misleading report.
"""
from leapp import reporting
from leapp.libraries.actor import clmysqlrepositorysetup
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, RPM, RpmTransactionTasks

DERIVED = 'CloudLinux database module stream was derived automatically'


def _rpm(name):
    return RPM(name=name, epoch='0', packager='CloudLinux Packaging Team', version='8.0.46',
               release='1.module_el9.8.0+341+e1292deb.cloudlinux', arch='x86_64',
               pgpsig='DSA/SHA256, Key ID 8c55a6628608cb71')


def _finalize(monkeypatch, src_ver, dst_ver, clmysql_type, baseurl, packages):
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(
        src_ver=src_ver, dst_ver=dst_ver, msgs=[InstalledRPM(items=[_rpm(p) for p in packages])],
        src_distro='cloudlinux', dst_distro='cloudlinux'))
    monkeypatch.setattr(api, 'produce', produce_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    lib = clmysqlrepositorysetup.MySqlRepositorySetupLibrary()
    lib.mysql_types.add('cloudlinux')
    lib.clmysql_type = clmysql_type
    lib.clmysql_meta_baseurl = baseurl
    lib.finalize()
    tasks = [m for m in api.produce.model_instances if isinstance(m, RpmTransactionTasks)]
    return tasks, [r['title'] for r in reporting.create_report.reports]


MYSQL80_URL = 'http://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/cl-mysql-8.0/$basearch/'
MYSQL80_PKGS = ['cl-MySQL80-server', 'cl-MySQL80-client', 'cl-MySQL80-libs', 'bash']
MARIADB1108_URL = 'http://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/cl-mariadb-11.08/$basearch/'


def test_cl10_target_upgrades_governor_packages_without_module_streams(monkeypatch):
    tasks, _ = _finalize(monkeypatch, '9.8', '10.2', 'mysql80', MYSQL80_URL, MYSQL80_PKGS)
    assert len(tasks) == 1
    assert tasks[0].modules_to_enable == []
    assert sorted(tasks[0].to_upgrade) == ['cl-MySQL80-client', 'cl-MySQL80-libs', 'cl-MySQL80-server']


def test_cl9_target_still_enables_the_governor_stream(monkeypatch):
    tasks, _ = _finalize(monkeypatch, '8.10', '9.6', 'mysql80', MYSQL80_URL, MYSQL80_PKGS)
    assert [(m.name, m.stream) for m in tasks[0].modules_to_enable] == [('mysql', 'cl-MySQL80')]
    assert 'cl-MySQL80-server' in tasks[0].to_upgrade


def test_cl10_target_raises_no_derived_stream_report(monkeypatch):
    # MariaDB 11.8 has no MODULE_STREAMS entry, so on 9 its stream is derived and
    # reported. On 10 there is no stream to derive at all.
    tasks, titles = _finalize(monkeypatch, '9.8', '10.2', 'mariadb1108', MARIADB1108_URL,
                              ['cl-MariaDB1108-server', 'cl-MariaDB1108-client'])
    assert DERIVED not in titles
    assert tasks[0].modules_to_enable == []
    assert 'cl-MariaDB1108-server' in tasks[0].to_upgrade


def test_cl9_target_still_reports_a_derived_stream(monkeypatch):
    _, titles = _finalize(monkeypatch, '8.10', '9.6', 'mariadb1108', MARIADB1108_URL,
                          ['cl-MariaDB1108-server'])
    assert DERIVED in titles
