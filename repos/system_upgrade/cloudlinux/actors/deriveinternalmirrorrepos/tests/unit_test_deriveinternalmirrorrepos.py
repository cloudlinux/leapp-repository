import pytest

from leapp.libraries.actor import deriveinternalmirrorrepos
from leapp.models import (
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RepositoriesFacts,
    RepositoryData,
    RepositoryFile,
)

MIRROR = 'https://mirror.example.internal/repos/upstream/cr'

# Baseurls shaped like a real internal mirror's, with the host replaced.
MIRROR_REPOS = {
    'cloudlinux-os': MIRROR + '/cloudlinux/$releasever/$basearch/os',
    'almalinux-BaseOS': MIRROR + '/almalinux/$releasever/$basearch/BaseOS',
    'almalinux-AppStream': MIRROR + '/almalinux/$releasever/$basearch/AppStream',
    'almalinux-PowerTools': MIRROR + '/almalinux/$releasever/$basearch/PowerTools',
    'cloudlinux-ea4': MIRROR + '/cloudlinux/EA4/$releasever/updates/$basearch',
}


def _repo(repoid, baseurl, enabled=True):
    return RepositoryData(repoid=repoid, name=repoid, baseurl=baseurl, enabled=enabled)


def _facts(repos, path='/etc/yum.repos.local.d/mirror.repo'):
    return RepositoriesFacts(repositories=[RepositoryFile(file=path, data=repos)])


@pytest.fixture(autouse=True)
def silence_logger(monkeypatch):
    class _Logger(object):
        def debug(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

    monkeypatch.setattr(deriveinternalmirrorrepos.api, 'current_logger', lambda: _Logger())


@pytest.fixture
def produced(monkeypatch):
    """Capture api.produce() and stub out the on-disk repofile copy."""
    out = []
    monkeypatch.setattr(deriveinternalmirrorrepos.api, 'produce', lambda *models: out.extend(models))
    monkeypatch.setattr(
        deriveinternalmirrorrepos, 'create_leapp_repofile_copy',
        lambda repofile_data, repo_name: '/var/lib/leapp/yum_custom_repofiles/{}_leapp_custom.repo'.format(repo_name)
    )
    return out


def _run(monkeypatch, repos, target_major='9'):
    monkeypatch.setattr(deriveinternalmirrorrepos.api, 'consume', lambda model: iter([_facts(repos)]))
    monkeypatch.setattr(deriveinternalmirrorrepos, 'get_target_major_version', lambda: target_major)
    deriveinternalmirrorrepos.process()


def _custom_repos(produced):
    return [m for m in produced if isinstance(m, CustomTargetRepository)]


@pytest.mark.parametrize(
    'source_repoid,expected_baseurl',
    (
        ('cloudlinux-os', MIRROR + '/cloudlinux/9/$basearch/os'),
        ('almalinux-BaseOS', MIRROR + '/almalinux/9/$basearch/BaseOS'),
        ('almalinux-AppStream', MIRROR + '/almalinux/9/$basearch/AppStream'),
        # $releasever sits mid-path here, not in the final segment.
        ('cloudlinux-ea4', MIRROR + '/cloudlinux/EA4/9/updates/$basearch'),
    ),
)
def test_releasever_is_retargeted(monkeypatch, produced, source_repoid, expected_baseurl):
    _run(monkeypatch, [_repo(source_repoid, MIRROR_REPOS[source_repoid])])

    repos = _custom_repos(produced)
    assert len(repos) == 1
    assert repos[0].baseurl == expected_baseurl
    # $basearch must survive untouched - dnf expands it in the target container.
    assert '$releasever' not in repos[0].baseurl


def test_powertools_is_renamed_to_crb(monkeypatch, produced):
    """el8 PowerTools becomes CRB at el9; the host's repo file still says PowerTools."""
    _run(monkeypatch, [_repo('almalinux-PowerTools', MIRROR_REPOS['almalinux-PowerTools'])])

    repos = _custom_repos(produced)
    assert len(repos) == 1
    assert repos[0].baseurl == MIRROR + '/almalinux/9/$basearch/CRB'


def test_rename_only_touches_the_final_segment(monkeypatch, produced):
    """A component name appearing earlier in the path must not be rewritten."""
    baseurl = MIRROR + '/PowerTools/$releasever/$basearch/BaseOS'
    _run(monkeypatch, [_repo('almalinux-BaseOS', baseurl)])

    assert _custom_repos(produced)[0].baseurl == MIRROR + '/PowerTools/9/$basearch/BaseOS'


def test_target_repoid_is_suffixed_to_avoid_clashing_with_source(monkeypatch, produced):
    _run(monkeypatch, [_repo('cloudlinux-os', MIRROR_REPOS['cloudlinux-os'])])

    assert _custom_repos(produced)[0].repoid == 'cloudlinux-os-9'


def test_derived_repo_is_enabled_even_if_source_repo_is_disabled_elsewhere(monkeypatch, produced):
    _run(monkeypatch, [_repo('cloudlinux-os', MIRROR_REPOS['cloudlinux-os'])])

    assert _custom_repos(produced)[0].enabled is True


def test_a_repofile_is_produced_so_the_container_can_see_the_repos(monkeypatch, produced):
    """CustomTargetRepository alone is not enough: userspacegen only accepts a
    custom repoid that is actually available in the container."""
    _run(monkeypatch, [_repo('cloudlinux-os', MIRROR_REPOS['cloudlinux-os'])])

    repofiles = [m for m in produced if isinstance(m, CustomTargetRepositoryFile)]
    assert len(repofiles) == 1
    assert repofiles[0].file.endswith('.repo')


def test_full_mirror_repo_set(monkeypatch, produced):
    _run(monkeypatch, [_repo(rid, url) for rid, url in MIRROR_REPOS.items()])

    assert sorted(r.repoid for r in _custom_repos(produced)) == [
        'almalinux-AppStream-9',
        'almalinux-BaseOS-9',
        'almalinux-PowerTools-9',
        'cloudlinux-ea4-9',
        'cloudlinux-os-9',
    ]


# --- guards against affecting other systems -------------------------------

def test_unknown_repoids_are_ignored(monkeypatch, produced):
    """Deriving arbitrary third-party repos would make them *required* target
    repos and inhibit the upgrade when the vendor has no el9 content."""
    _run(monkeypatch, [
        _repo('patchmon', MIRROR + '/patchmon/$releasever/x86_64/'),
        _repo('zenetys', MIRROR + '/zenetys/$releasever/$basearch/'),
    ])

    assert produced == []


def test_repo_without_releasever_is_ignored(monkeypatch, produced):
    """A pinned baseurl cannot be retargeted, so guessing would be wrong."""
    _run(monkeypatch, [_repo('cloudlinux-os', MIRROR + '/cloudlinux/8/$basearch/os')])

    assert produced == []


def test_disabled_source_repo_is_ignored(monkeypatch, produced):
    _run(monkeypatch, [_repo('cloudlinux-os', MIRROR_REPOS['cloudlinux-os'], enabled=False)])

    assert produced == []


def test_repo_without_baseurl_is_ignored(monkeypatch, produced):
    """Mirrorlist/metalink-driven repos have no baseurl to retarget."""
    _run(monkeypatch, [_repo('cloudlinux-os', None)])

    assert produced == []


def test_stock_cloudlinux_system_is_untouched(monkeypatch, produced):
    """Regression guard: a normal CL box must be completely unaffected."""
    _run(monkeypatch, [
        _repo('cloudlinux-x86_64-server-8', 'https://repo.cloudlinux.com/cloudlinux/$releasever/BaseOS/x86_64/os/'),
        _repo('epel', 'https://download.example/pub/epel/$releasever/Everything/x86_64/'),
    ])

    assert produced == []
