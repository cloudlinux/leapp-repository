from leapp.libraries.common import mounting, targetrepoquery
from leapp.libraries.common.testutils import CurrentActorMocked
from leapp.libraries.stdlib import api


def _query(monkeypatch):
    seen = {}

    def fake_run(cmd, **dummy):
        seen['cmd'] = cmd
        return {'stdout': ''}

    monkeypatch.setattr(mounting, 'run', fake_run)
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(dst_ver='9.8'))
    targetrepoquery.query_available('/installroot', '%{version}\n', 'lve-stats3')
    return seen['cmd']


def test_the_query_keeps_its_own_metadata_cache(monkeypatch):
    """dnf reuses cached metadata whatever release the client now reports - a
    cache filled as a "CloudLinux 8.10" client answers el8 builds to a 9.x one -
    so a query on the userspace's shared default cache reads whatever another
    dnf call left there."""
    cachedirs = [arg for arg in _query(monkeypatch) if arg.startswith('--setopt=cachedir=')]

    assert len(cachedirs) == 1
    assert cachedirs[0].split('=', 2)[2] not in ('/var/cache/dnf', '/var/cache/dnf/')


def _query_env(monkeypatch, dst_ver):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen['env'] = kwargs.get('env')
        return {'stdout': ''}

    monkeypatch.setattr(mounting, 'run', fake_run)
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(dst_ver=dst_ver))
    targetrepoquery.query_available('/installroot', '%{version}\n', 'lve-stats3')
    return seen['env'] or {}


def test_on_a_cl8_source_the_container_may_start_threads(monkeypatch):
    """systemd 239's nspawn filters clone3, which the el9 glibc uses for threads,
    so in the el9 userspace dnf cannot start libcurl's resolver thread: every
    repository failed, skip_if_unavailable hid it, and all fourteen essential
    packages read as having no target build. dnfplugin and the initramfs
    generator lift the filter for a target of 9; this query has to as well."""
    assert _query_env(monkeypatch, '9.8').get('SYSTEMD_SECCOMP') == '0'


def test_the_filter_stays_on_where_dnfplugin_keeps_it(monkeypatch):
    assert 'SYSTEMD_SECCOMP' not in _query_env(monkeypatch, '10')
