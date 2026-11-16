from leapp.libraries.actor import replacerpmnewconfigs
from leapp.libraries.common.testutils import logger_mocked


def _setup(monkeypatch, tmpdir, configured=None):
    """first stands for /etc/yum.repos.d - the tests must never touch the real
    one - and second for a relocated directory. configured is what dnf reads:
    by default both, plus a directory that does not exist."""
    first = tmpdir.mkdir('yum.repos.d')
    second = tmpdir.mkdir('yum.repos.local.d')
    if configured is None:
        configured = [str(first), str(second), str(tmpdir.join('does-not-exist'))]
    else:
        configured = [str(tmpdir.join(name)) for name in configured]
    monkeypatch.setattr(replacerpmnewconfigs.cl_repofileutils, 'REPO_DIR', str(first))
    monkeypatch.setattr(replacerpmnewconfigs.cl_repofileutils, 'get_repo_dirs', lambda: list(configured))
    monkeypatch.setattr(replacerpmnewconfigs.api, 'current_logger', logger_mocked())
    return first, second


def test_rpmnew_is_applied_in_every_configured_directory(monkeypatch, tmpdir):
    """An .rpmnew in a configured directory other than /etc/yum.repos.d is
    applied too."""
    first, second = _setup(monkeypatch, tmpdir)
    second.join('cloudlinux.repo').write('old\n')
    second.join('cloudlinux.repo.rpmnew').write('new\n')

    deleted, renamed = replacerpmnewconfigs.replace_rpmnew_configs()

    assert second.join('cloudlinux.repo').read() == 'new\n'
    assert not second.join('cloudlinux.repo.rpmnew').exists()
    assert deleted == ['cloudlinux.repo']
    assert renamed == []


def test_rpmnew_of_other_repositories_is_left_alone(monkeypatch, tmpdir):
    first, second = _setup(monkeypatch, tmpdir)
    second.join('epel.repo').write('old\n')
    second.join('epel.repo.rpmnew').write('new\n')

    deleted, renamed = replacerpmnewconfigs.replace_rpmnew_configs()

    assert second.join('epel.repo').read() == 'old\n'
    assert second.join('epel.repo.rpmnew').exists()
    assert (deleted, renamed) == ([], [])


def test_leapp_backups_are_disabled_in_every_configured_directory(monkeypatch, tmpdir):
    first, second = _setup(monkeypatch, tmpdir)
    backup = second.join('imunify.repo' + replacerpmnewconfigs.LEAPP_BACKUP_SUFFIX)
    backup.write('[imunify]\nname=Imunify\nenabled=1\n')

    replacerpmnewconfigs.replace_rpmnew_configs()

    assert backup.read() == '[imunify]\nname=Imunify\nenabled = 0\n'


def test_rpmnew_in_the_standard_directory_is_applied_on_a_relocated_host(monkeypatch, tmpdir):
    """rpm writes an .rpmnew beside the packaged path, which for repofiles is
    /etc/yum.repos.d - also on a host whose reposdir leaves that directory out.
    Scanning only the configured directories would leave it unapplied."""
    first, second = _setup(monkeypatch, tmpdir, configured=['yum.repos.local.d'])
    first.join('cloudlinux.repo').write('old\n')
    first.join('cloudlinux.repo.rpmnew').write('new\n')

    deleted, renamed = replacerpmnewconfigs.replace_rpmnew_configs()

    assert first.join('cloudlinux.repo').read() == 'new\n'
    assert not first.join('cloudlinux.repo.rpmnew').exists()
    assert deleted == ['cloudlinux.repo']

