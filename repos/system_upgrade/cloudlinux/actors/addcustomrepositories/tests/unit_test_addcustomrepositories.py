import os

from leapp.libraries.actor import addcustomrepositories


class _Log(object):
    def debug(self, *args, **kwargs):
        pass


def test_repofiles_go_to_the_directory_dnf_reads(monkeypatch, tmpdir):
    """A host that relocates reposdir (e.g. /etc/yum.repos.local.d) never reads
    /etc/yum.repos.d, so a repofile copied there would be invisible."""
    custom = tmpdir.mkdir('custom-repos')
    custom.join('a.repo').write('[a]\n')
    custom.join('b.repo').write('[b]\n')
    copied = []

    monkeypatch.setattr(addcustomrepositories.api, 'get_common_folder_path', lambda folder: str(custom))
    monkeypatch.setattr(addcustomrepositories.cl_repofileutils, 'get_primary_repo_dir',
                        lambda: '/etc/yum.repos.local.d')
    # Recorded rather than performed, so nothing is written outside tmpdir.
    monkeypatch.setattr(addcustomrepositories.shutil, 'copy', lambda src, dst: copied.append((src, dst)))

    addcustomrepositories.add_custom(_Log())

    assert sorted(copied) == [
        (os.path.join(str(custom), 'a.repo'), '/etc/yum.repos.local.d'),
        (os.path.join(str(custom), 'b.repo'), '/etc/yum.repos.local.d'),
    ]


def test_nothing_is_copied_when_there_are_no_custom_repofiles(monkeypatch, tmpdir):
    custom = tmpdir.mkdir('custom-repos')
    copied = []
    monkeypatch.setattr(addcustomrepositories.api, 'get_common_folder_path', lambda folder: str(custom))
    monkeypatch.setattr(addcustomrepositories.shutil, 'copy', lambda src, dst: copied.append((src, dst)))

    addcustomrepositories.add_custom(_Log())

    assert copied == []
