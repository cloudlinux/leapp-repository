import os

from leapp import reporting
from leapp.libraries.actor import restoremysqldata
from leapp.libraries.common import backup
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api


def _setup(monkeypatch, tmp_path, backed_up):
    """Lay out a backup directory holding `backed_up` and a live /etc/container."""
    backup_dir = tmp_path / 'cl_backup'
    backup_dir.mkdir()
    container = tmp_path / 'container'
    container.mkdir()
    files = [str(container / name) for name in ('dbuser-map', 've.cfg', 'mysql-governor.xml')]
    for name in backed_up:
        (backup_dir / name).write_text(u'backed up ' + name)

    monkeypatch.setattr(backup, 'BACKUP_DIR', str(backup_dir))
    monkeypatch.setattr(backup, 'CLSQL_BACKUP_FILES', files)
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    return container


def test_backed_up_files_are_restored(monkeypatch, tmp_path):
    container = _setup(monkeypatch, tmp_path, ['dbuser-map', 've.cfg', 'mysql-governor.xml'])

    restoremysqldata.process()

    assert (container / 've.cfg').read_text() == u'backed up ve.cfg'
    assert reporting.create_report.called == 0


def test_a_file_the_source_never_had_is_not_reported_as_a_restore_failure(monkeypatch, tmp_path):
    """backup_my_sql_data copies only the files that exist. A box without, say,
    /etc/container/dbuser-map has nothing to restore, and used to get a HIGH
    'Failed to restore backed up configuration files' report for it."""
    container = _setup(monkeypatch, tmp_path, ['ve.cfg', 'mysql-governor.xml'])

    restoremysqldata.process()

    assert reporting.create_report.called == 0
    assert api.current_logger.errmsg == []
    assert not os.path.exists(str(container / 'dbuser-map'))
    assert (container / 've.cfg').read_text() == u'backed up ve.cfg'


def test_a_backup_that_cannot_be_restored_is_reported(monkeypatch, tmp_path):
    container = _setup(monkeypatch, tmp_path, ['ve.cfg'])
    container.rmdir()

    restoremysqldata.process()

    assert reporting.create_report.called == 1
    report = reporting.create_report.report_fields
    assert report['severity'] == reporting.Severity.HIGH
    assert str(container / 've.cfg') in report['summary']
    assert str(container / 'dbuser-map') not in report['summary']
