"""The distribution's own MySQL/MariaDB is a variant too, found by package name.

It has no repository file of its own, so the repofile loop never saw it: on a
CloudLinux 9 box with the default MySQL the actor logged "No installed
MySQL/MariaDB detected" and the backup recommendation never appeared.
"""
import pytest

from leapp import reporting
from leapp.libraries.actor import clmysqlrepositorysetup
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import InstalledMySqlTypes, InstalledRPM, RPM


def _rpm(name):
    return RPM(name=name, epoch='1', packager='CloudLinux Packaging Team', version='8.0.46',
               release='1.el9_8.cloudlinux.1', arch='x86_64', pgpsig='DSA/SHA256, Key ID 8c55a6628608cb71')


def _run(monkeypatch, packages):
    monkeypatch.setattr(clmysqlrepositorysetup.os, 'listdir', lambda path: [])
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(
        src_ver='9.8', dst_ver='10.2', msgs=[InstalledRPM(items=[_rpm(p) for p in packages])],
        src_distro='cloudlinux', dst_distro='cloudlinux'))
    monkeypatch.setattr(api, 'produce', produce_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    clmysqlrepositorysetup.MySqlRepositorySetupLibrary().process()
    types = [m for m in api.produce.model_instances if isinstance(m, InstalledMySqlTypes)]
    titles = [r['title'] for r in reporting.create_report.reports]
    return (types[0].types if types else None), titles


@pytest.mark.parametrize('server', ['mysql-server', 'mariadb-server'])
def test_distro_server_is_detected_and_backup_recommended(monkeypatch, server):
    types, titles = _run(monkeypatch, [server, 'bash'])
    assert types == ['distro']
    assert 'MySQL database backup recommended' in titles


@pytest.mark.parametrize('packages', [['bash'], ['cl-MySQL80-server'], ['mysql-community-server']])
def test_other_packages_are_not_the_distro_variant(monkeypatch, packages):
    types, _ = _run(monkeypatch, packages)
    assert 'distro' not in (types or [])


def test_distro_packages_come_from_the_shared_definition():
    from leapp.libraries.common import clmysql
    assert clmysqlrepositorysetup.DISTRO_DB_SERVERS is clmysql.DISTRO_DB_SERVERS
