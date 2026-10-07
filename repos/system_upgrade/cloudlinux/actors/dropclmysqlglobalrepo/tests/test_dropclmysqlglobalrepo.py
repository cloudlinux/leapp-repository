import os

import pytest

from leapp.libraries.actor import dropclmysqlglobalrepo as lib
from leapp.libraries.common.testutils import CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api

# What Governor's `mysql.type=auto` wrote on CloudLinux 9 (cl9/mysqlmeta/mysql-common.repo),
# as found on a box upgraded to CloudLinux 10: cl10 publishes no mysqlglobalrepo tree, so
# every dnf command failed on this file's 404.
CL9_AUTO_REPO = """[cl-mysql]
name=cl-mysql
baseurl=https://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/mysqlglobalrepo/$basearch/
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CloudLinux

[mysqclient]
name=mysqlclient
baseurl=https://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/mysqlclient/$basearch/
enabled=0
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CloudLinux
"""

MYSQCLIENT_ONLY = CL9_AUTO_REPO[CL9_AUTO_REPO.index('[mysqclient]'):]

# Governor with a managed database: cl10 has this tree, so the file must survive untouched.
CL_MYSQL_84_REPO = """[cl-mysql-meta]
name=cl-mysql-meta
baseurl=http://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/cl-mysql-8.4/$basearch/
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CloudLinux

[mysqclient]
name=mysqlclient
baseurl=http://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/mysqlclient/$basearch/
enabled=0
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CloudLinux
"""


def test_the_global_repo_section_is_dropped_and_the_rest_kept_verbatim():
    text, dropped = lib.drop_global_sections(CL9_AUTO_REPO)

    assert dropped == ['cl-mysql']
    assert text == MYSQCLIENT_ONLY


def test_a_file_without_the_global_repo_is_unchanged():
    assert lib.drop_global_sections(CL_MYSQL_84_REPO) == (CL_MYSQL_84_REPO, [])


def test_a_mirrorlist_pointing_at_the_global_repo_counts_too():
    text = '[g]\nmirrorlist=https://h/other/cl$releasever/mysqlmeta/mysqlglobalrepo/x\n\n' + MYSQCLIENT_ONLY

    assert lib.drop_global_sections(text) == (MYSQCLIENT_ONLY, ['g'])


def test_a_comment_mentioning_the_global_repo_does_not_drop_a_section():
    text = ('[keep]\n# was https://repo.cloudlinux.com/other/cl9/mysqlmeta/mysqlglobalrepo/ once\n'
            'baseurl=https://h/mysqlmeta/cl-mysql-8.4/x\n')

    assert lib.drop_global_sections(text) == (text, [])


def _system(monkeypatch, tmp_path, content, dst='10.0'):
    path = tmp_path / 'cl-mysql.repo'
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(lib, 'CL_MYSQL_REPO', str(path))
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(src_ver='9.6', dst_ver=dst))
    monkeypatch.setattr(lib.reporting, 'create_report', lambda *a, **k: None)
    return path


def test_on_a_cl10_target_the_file_is_rewritten_and_the_original_kept(monkeypatch, tmp_path):
    path = _system(monkeypatch, tmp_path, CL9_AUTO_REPO)

    lib.process()

    assert path.read_text() == MYSQCLIENT_ONLY
    assert (tmp_path / 'cl-mysql.repo.leapp-backup').read_text() == CL9_AUTO_REPO


@pytest.mark.parametrize('dst', ['8.10', '9.8'])
def test_targets_that_publish_the_global_repo_are_left_alone(monkeypatch, tmp_path, dst):
    """cl8 and cl9 do publish mysqlglobalrepo; the file is valid there."""
    path = _system(monkeypatch, tmp_path, CL9_AUTO_REPO, dst=dst)

    lib.process()

    assert path.read_text() == CL9_AUTO_REPO
    assert not (tmp_path / 'cl-mysql.repo.leapp-backup').exists()


def test_a_cl10_file_that_needs_nothing_is_not_rewritten(monkeypatch, tmp_path):
    path = _system(monkeypatch, tmp_path, CL_MYSQL_84_REPO)
    os.utime(str(path), (1000000000, 1000000000))

    lib.process()

    assert path.read_text() == CL_MYSQL_84_REPO
    assert os.stat(str(path)).st_mtime == 1000000000
    assert not (tmp_path / 'cl-mysql.repo.leapp-backup').exists()


def test_no_file_is_nothing_to_do(monkeypatch, tmp_path):
    path = _system(monkeypatch, tmp_path, None)

    lib.process()

    assert not path.exists()
