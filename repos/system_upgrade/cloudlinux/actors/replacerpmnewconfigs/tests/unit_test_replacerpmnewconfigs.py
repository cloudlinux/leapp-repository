from leapp.libraries.actor import replacerpmnewconfigs
from leapp.libraries.common.testutils import logger_mocked


def _setup(monkeypatch, tmpdir):
    first = tmpdir.mkdir('yum.repos.d')
    second = tmpdir.mkdir('yum.repos.local.d')
    monkeypatch.setattr(replacerpmnewconfigs.cl_repofileutils, 'get_repo_dirs',
                        lambda: [str(first), str(second), str(tmpdir.join('does-not-exist'))])
    monkeypatch.setattr(replacerpmnewconfigs.api, 'current_logger', logger_mocked())
    return first, second


def test_rpmnew_is_applied_in_every_configured_directory(monkeypatch, tmpdir):
    """The upgraded cloudlinux-release drops its .rpmnew beside whichever repofile
    it owns - in /etc/yum.repos.local.d on such a host - and leaving it unapplied keeps
    the el8 repository definition on the el9 system."""
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
