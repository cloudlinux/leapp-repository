import os

import pytest

from leapp.libraries.common import cl_repofileutils, repofileutils
from leapp.libraries.common.testutils import logger_mocked


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(cl_repofileutils.api, 'current_logger', logger_mocked())


@pytest.mark.parametrize(
    'repodirs,expected',
    (
        # Standard system.
        (['/etc/yum.repos.d'], '/etc/yum.repos.d'),
        # The default wins whenever dnf reads it, wherever it sits in the list.
        (['/etc/distro.repos.d', '/etc/yum.repos.d'], '/etc/yum.repos.d'),
        # Relocated reposdir.
        (['/etc/yum.repos.local.d'], '/etc/yum.repos.local.d'),
        # get_repodirs() builds its list from a set, so its order means
        # nothing: the pick must not depend on it.
        (['/etc/b.repos.d', '/etc/a.repos.d'], '/etc/a.repos.d'),
        (['/etc/a.repos.d', '/etc/b.repos.d'], '/etc/a.repos.d'),
        # Nothing usable reported.
        ([], '/etc/yum.repos.d'),
    ),
)
def test_primary_repo_dir(monkeypatch, repodirs, expected):
    monkeypatch.setattr(repofileutils, 'get_repodirs', lambda: list(repodirs))

    assert cl_repofileutils.get_primary_repo_dir() == expected


def test_primary_repo_dir_recognises_a_symlinked_default(monkeypatch, tmpdir):
    real = tmpdir.mkdir('real-repos.d')
    link = tmpdir.join('yum.repos.d')
    link.mksymlinkto(real)
    monkeypatch.setattr(cl_repofileutils, 'REPO_DIR', str(link))
    monkeypatch.setattr(repofileutils, 'get_repodirs', lambda: [os.path.realpath(str(link))])

    assert cl_repofileutils.get_primary_repo_dir() == str(link)


def test_repo_dirs_fall_back_to_the_default_when_dnf_fails(monkeypatch):
    def broken():
        raise OSError('no dnf')

    monkeypatch.setattr(repofileutils, 'get_repodirs', broken)

    assert cl_repofileutils.get_repo_dirs() == ['/etc/yum.repos.d']
    assert cl_repofileutils.get_primary_repo_dir() == '/etc/yum.repos.d'
