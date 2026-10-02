import os

import pytest

from leapp.libraries.actor import repinelsrepofiles as lib
from leapp.libraries.common.testutils import CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api

# As els-php-release-1.1.0-6.el10 left it on a CL9 -> CL10 upgrade: its %post ran
# `rpm -E %{rhel}` inside the transaction, got 9, and wrote it over $releasever.
PHP_ELS_LEFT_ON_EL9 = """[php-els]
name = PHP Extended Lifecycle Support by TuxCare
baseurl = https://$phpelstoken:@repo.alt.tuxcare.com/alt-php-els/rpm/el/9/stable/$basearch/
enabled=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-TuxCare
gpgcheck=1
"""


def test_a_url_left_on_the_source_major_is_moved_to_the_target():
    text, changed = lib.repin(PHP_ELS_LEFT_ON_EL9, '9', '10')

    assert changed == 1
    assert 'alt-php-els/rpm/el/10/stable/$basearch/' in text
    assert '/el/9/' not in text
    assert text.replace('/el/10/', '/el/9/') == PHP_ELS_LEFT_ON_EL9, 'nothing else may change'


@pytest.mark.parametrize('key', ['baseurl', 'mirrorlist', 'metalink'])
def test_every_url_key_counts(key):
    text, changed = lib.repin('[r]\n{0} = https://h/x/rpm/el/8/$basearch/\n'.format(key), '8', '9')

    assert changed == 1
    assert '/el/9/' in text


@pytest.mark.parametrize('url', [
    'https://h/x/rpm/el/10/stable/$basearch/',     # already on the target
    'https://h/x/rpm/el/90/stable/$basearch/',     # a different number entirely
    'https://h/x/rpm/el/9.6/stable/$basearch/',    # a minor, not the bare major
    'https://h/x/rpm/el/$releasever/$basearch/',   # never pinned
])
def test_a_url_not_on_the_bare_source_major_is_left_alone(url):
    original = '[r]\nbaseurl = {0}\n'.format(url)

    assert lib.repin(original, '9', '10') == (original, 0)


def test_only_url_lines_are_rewritten():
    original = '[r]\nname = mirror of /el/9/ trees\nbaseurl = https://h/rpm/el/9/x/\n'

    text, changed = lib.repin(original, '9', '10')

    assert changed == 1
    assert 'name = mirror of /el/9/ trees' in text


def test_every_section_of_a_rollout_file_is_rewritten():
    original = ''.join('[slot-{0}]\nbaseurl = https://r/slot-{0}/rpm/el/9/$basearch/\n\n'.format(n)
                       for n in range(1, 4))

    text, changed = lib.repin(original, '9', '10')

    assert changed == 3
    assert '/el/9/' not in text


def _system(monkeypatch, tmp_path, owners, files, src='9.6', dst='10.0'):
    """A fake target system: `owners` maps package name -> the repo files it owns,
    `files` maps repo file name -> content, all under tmp_path."""
    for name, content in files.items():
        tmp_path.joinpath(name).write_text(content)

    def fake_run(cmd, split=False, **dummy):
        if cmd[:2] == ['rpm', '-qa']:
            lines = list(owners)
        elif cmd[:2] == ['rpm', '-ql']:
            lines = [os.path.join(str(tmp_path), f) for f in owners[cmd[2]]]
        else:
            raise AssertionError('unexpected command {0}'.format(cmd))
        # leapp's run hands back stdout as a list of lines when split=True
        return {'stdout': lines if split else ''.join(line + '\n' for line in lines)}

    monkeypatch.setattr(lib, 'run', fake_run)
    monkeypatch.setattr(lib, 'REPO_DIR', str(tmp_path))
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(src_ver=src, dst_ver=dst))


def test_files_of_the_els_release_packages_are_repinned(monkeypatch, tmp_path):
    _system(monkeypatch, tmp_path,
            owners={'els-php-release': ['php-els.repo'],
                    'alt-common-release': ['alt-common-els.repo']},
            files={'php-els.repo': PHP_ELS_LEFT_ON_EL9,
                   'alt-common-els.repo': '[alt-common]\nbaseurl = https://h/alt-common/rpm/el/9/stable/x/\n'})

    lib.process()

    assert '/el/10/' in tmp_path.joinpath('php-els.repo').read_text()
    assert '/el/10/' in tmp_path.joinpath('alt-common-els.repo').read_text()


def test_repo_files_of_other_packages_are_left_alone(monkeypatch, tmp_path):
    unrelated = '[x]\nbaseurl = https://h/rpm/el/9/x/\n'
    _system(monkeypatch, tmp_path,
            owners={'els-php-release': ['php-els.repo'], 'some-vendor-release': ['vendor.repo']},
            files={'php-els.repo': PHP_ELS_LEFT_ON_EL9, 'vendor.repo': unrelated,
                   'unowned.repo': unrelated})

    lib.process()

    assert tmp_path.joinpath('vendor.repo').read_text() == unrelated
    assert tmp_path.joinpath('unowned.repo').read_text() == unrelated


def test_a_file_already_on_the_target_is_not_rewritten(monkeypatch, tmp_path):
    good = PHP_ELS_LEFT_ON_EL9.replace('/el/9/', '/el/10/')
    _system(monkeypatch, tmp_path, owners={'els-php-release': ['php-els.repo']},
            files={'php-els.repo': good})
    path = tmp_path.joinpath('php-els.repo')
    os.utime(str(path), (1000000000, 1000000000))

    lib.process()

    assert path.read_text() == good
    assert os.stat(str(path)).st_mtime == 1000000000, 'an unchanged file must not be written'


def test_the_cl8_to_cl9_path_is_covered_too(monkeypatch, tmp_path):
    _system(monkeypatch, tmp_path, owners={'alt-common-release': ['alt-common-els.repo']},
            files={'alt-common-els.repo': '[alt-common]\nbaseurl = https://h/rpm/el/8/stable/x/\n'},
            src='8.10', dst='9.8')

    lib.process()

    assert '/el/9/' in tmp_path.joinpath('alt-common-els.repo').read_text()


def test_only_the_packages_repo_files_are_touched(monkeypatch, tmp_path):
    """A release package owns more than its repo files - docs, keys, a template.
    Only the .repo files in the repository directory are the actor's."""
    template = '[t]\nbaseurl = https://h/rpm/el/9/x/\n'
    docs = tmp_path.joinpath('doc')
    docs.mkdir()
    docs.joinpath('php-els.repo').write_text(template)
    _system(monkeypatch, tmp_path,
            owners={'els-php-release': ['php-els.repo', 'php-els.repo.example', 'doc/php-els.repo']},
            files={'php-els.repo': PHP_ELS_LEFT_ON_EL9, 'php-els.repo.example': template})

    lib.process()

    assert '/el/10/' in tmp_path.joinpath('php-els.repo').read_text()
    assert tmp_path.joinpath('php-els.repo.example').read_text() == template
    assert docs.joinpath('php-els.repo').read_text() == template
