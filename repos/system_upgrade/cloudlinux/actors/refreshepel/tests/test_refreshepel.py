import os

import pytest

from leapp import reporting
from leapp.libraries.actor import refreshepel
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, RPM

# The CloudLinux 9 file after 'dnf config-manager --set-disabled epel', which is
# what made rpm keep it and write the CloudLinux 10 one as epel.repo.rpmnew.
EL9_EDITED = """[epel]
name=Extra Packages for Enterprise Linux 9 - $basearch
metalink=https://mirrors.fedoraproject.org/metalink?repo=epel-9&arch=$basearch
enabled = 0
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-9

[epel-debuginfo]
name=Extra Packages for Enterprise Linux 9 - $basearch - Debug
metalink=https://mirrors.fedoraproject.org/metalink?repo=epel-debug-9&arch=$basearch
enabled = 1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-9
"""

EL10_RPMNEW = """[epel]
name=Extra Packages for Enterprise Linux $releasever_major - $basearch
metalink=https://mirrors.fedoraproject.org/metalink?repo=epel-$releasever_major&arch=$basearch
enabled=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-$releasever_major

[epel-debuginfo]
name=Extra Packages for Enterprise Linux $releasever_major - $basearch - Debug
metalink=https://mirrors.fedoraproject.org/metalink?repo=epel-debug-$releasever_major&arch=$basearch
enabled=0
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-$releasever_major
"""


class _Box:
    """The upgraded system as rpm sees it. Nothing here reaches a network:
    the Applications phase runs in the upgrade environment, which has none."""

    def __init__(self, version, verified):
        self.version = version
        self.verified = verified
        self.calls = []

    def run(self, cmd, **dummy):
        self.calls.append(cmd)
        if cmd[:2] == ['rpm', '-q'] and cmd[-1] == 'epel-release':
            if self.version is None:
                return {'exit_code': 1, 'stdout': 'package epel-release is not installed'}
            return {'exit_code': 0, 'stdout': self.version}
        if cmd[:2] == ['rpm', '-q']:
            return {'exit_code': 0 if cmd[-1] == 'epel-release-{}'.format(self.version) else 1, 'stdout': ''}
        if cmd[:2] == ['rpm', '-V']:
            return {'exit_code': 0 if self.verified else 1, 'stdout': ''}
        if cmd[:2] == ['rpm', '-e']:
            self.version = None
        return {'exit_code': 1, 'stdout': ''}


def _rpm(name):
    return RPM(name=name, epoch='0', packager='Fedora Project', version='9', release='10.el9',
               arch='noarch', pgpsig='RSA/SHA256, Key ID 8a3872bf3228467c')


def _setup(monkeypatch, tmp_path, files, version='10', verified=False, source_had_epel=True):
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    box = _Box(version, verified)
    msgs = [InstalledRPM(items=[_rpm('epel-release')] if source_had_epel else [])]
    monkeypatch.setattr(refreshepel, 'REPO_DIR', str(tmp_path))
    monkeypatch.setattr(refreshepel, 'run', box.run)
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(src_ver='9.8', dst_ver='10.0', msgs=msgs))
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    return box


def _destructive(box):
    return [c for c in box.calls if c[:2] == ['rpm', '-e'] or c[0] == 'dnf']


def test_an_edited_epel_repo_is_replaced_by_the_target_one_and_epel_survives(monkeypatch, tmp_path):
    """Both CloudLinux 9 to 10 test systems lost EPEL here: the edit made rpm -V
    fail, the actor erased epel-release and every epel*.repo, and its reinstall
    from dl.fedoraproject.org cannot resolve in the upgrade environment."""
    box = _setup(monkeypatch, tmp_path, {'epel.repo': EL9_EDITED, 'epel.repo.rpmnew': EL10_RPMNEW})

    refreshepel.process()

    assert _destructive(box) == []
    assert box.version == '10'
    repo = (tmp_path / 'epel.repo').read_text()
    assert 'RPM-GPG-KEY-EPEL-$releasever_major' in repo
    assert 'epel-9' not in repo
    assert not (tmp_path / 'epel.repo.rpmnew').exists()
    assert (tmp_path / 'epel.repo.leapp-backup').read_text() == EL9_EDITED


def test_each_section_keeps_the_enabled_state_it_had(monkeypatch, tmp_path):
    """Panels and admins toggle EPEL with config-manager; DirectAdmin enables it."""
    _setup(monkeypatch, tmp_path, {'epel.repo': EL9_EDITED, 'epel.repo.rpmnew': EL10_RPMNEW})

    refreshepel.process()

    repo = (tmp_path / 'epel.repo').read_text()
    epel, debuginfo = repo.split('[epel-debuginfo]')
    assert 'enabled=0' in epel and 'enabled=1' not in epel
    assert 'enabled=1' in debuginfo and 'enabled=0' not in debuginfo


def test_an_rpmnew_with_no_file_beside_it_is_moved_into_place(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {'epel-testing.repo.rpmnew': EL10_RPMNEW})

    refreshepel.process()

    assert (tmp_path / 'epel-testing.repo').read_text() == EL10_RPMNEW
    assert not (tmp_path / 'epel-testing.repo.rpmnew').exists()


@pytest.mark.parametrize('version', [None, '9'])
def test_epel_release_not_on_the_target_version_is_reported_not_fetched(monkeypatch, tmp_path, version):
    box = _setup(monkeypatch, tmp_path, {'epel.repo': EL9_EDITED}, version=version)

    refreshepel.process()

    assert _destructive(box) == []
    assert (tmp_path / 'epel.repo').read_text() == EL9_EDITED
    assert reporting.create_report.called == 1
    report = reporting.create_report.report_fields
    assert report['severity'] == reporting.Severity.HIGH
    assert 'epel-release-latest-10' in str(report)


def test_an_upgraded_untouched_epel_is_left_alone(monkeypatch, tmp_path):
    box = _setup(monkeypatch, tmp_path, {'epel.repo': EL10_RPMNEW}, verified=True)

    refreshepel.process()

    assert _destructive(box) == []
    assert (tmp_path / 'epel.repo').read_text() == EL10_RPMNEW
    assert reporting.create_report.called == 0


def test_a_system_that_never_had_epel_is_left_alone(monkeypatch, tmp_path):
    box = _setup(monkeypatch, tmp_path, {}, version=None, source_had_epel=False)

    refreshepel.process()

    assert _destructive(box) == []
    assert os.listdir(str(tmp_path)) == []
    assert reporting.create_report.called == 0
