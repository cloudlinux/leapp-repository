import pytest

from leapp import reporting
from leapp.exceptions import StopActorExecutionError
from leapp.libraries.actor import settargetkernelargs as lib
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, KernelCmdline, KernelCmdlineArg, RPM, TargetKernelCmdlineArgTasks

# The el9-era arguments the first el10 boot actually ran with on a CloudLinux 9
# box on the cloudlinux-default-cgv1 profile - taken from its journal.
CGV1 = [
    ('ro', None), ('selinux', '0'), ('cgroup.memory', 'nokmem'),
    ('systemd.unified_cgroup_hierarchy', '0'), ('systemd.legacy_systemd_cgroup_controller', None),
]
CGV2 = [('ro', None), ('selinux', '0'), ('cgroup.memory', 'nokmem'), ('cgroup_no_v1', 'all')]

IBT_OFF = ('ibt', 'off')
LEGACY_FORCE = ('SYSTEMD_CGROUP_ENABLE_LEGACY_FORCE', '1')


def _rpm(name):
    return RPM(name=name, epoch='0', packager='CloudLinux Packaging Team', version='2.1',
               release='76.el9', arch='x86_64', pgpsig='RSA/SHA256, Key ID 8c55a6628608cb71')


def _setup(monkeypatch, params, packages=('kmod-lve',), src_ver='9.8', dst_ver='10.2', cmdline=True):
    msgs = [InstalledRPM(items=[_rpm(p) for p in packages])]
    if cmdline:
        msgs.append(KernelCmdline(parameters=[KernelCmdlineArg(key=k, value=v) for k, v in params]))
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(
        src_ver=src_ver, dst_ver=dst_ver, msgs=msgs, src_distro='cloudlinux', dst_distro='cloudlinux'))
    monkeypatch.setattr(api, 'produce', produce_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())


def _added():
    tasks = [m for m in api.produce.model_instances if isinstance(m, TargetKernelCmdlineArgTasks)]
    assert len(tasks) <= 1
    return {(a.key, a.value) for t in tasks for a in t.to_add}


def test_cgroups_v1_source_gets_both(monkeypatch):
    _setup(monkeypatch, CGV1)
    lib.process()
    assert _added() == {IBT_OFF, LEGACY_FORCE}


def test_cgroups_v2_source_gets_only_ibt(monkeypatch):
    _setup(monkeypatch, CGV2)
    lib.process()
    assert _added() == {IBT_OFF}


def test_ibt_off_is_for_lve_only(monkeypatch):
    """IBT is a hardening feature; it is turned off only because kmodlve needs it off."""
    _setup(monkeypatch, CGV1, packages=('bash',))
    lib.process()
    assert _added() == {LEGACY_FORCE}


def test_nothing_to_add_produces_nothing(monkeypatch):
    _setup(monkeypatch, CGV2, packages=('bash',))
    lib.process()
    assert api.produce.called == 0
    assert reporting.create_report.called == 0


@pytest.mark.parametrize(('src_ver', 'dst_ver'), [('8.10', '9.6'), ('7.9', '8.10')])
def test_only_for_a_cloudlinux_10_target(monkeypatch, src_ver, dst_ver):
    _setup(monkeypatch, CGV1, src_ver=src_ver, dst_ver=dst_ver)
    lib.process()
    assert api.produce.called == 0


def test_arguments_already_present_are_not_repeated(monkeypatch):
    _setup(monkeypatch, CGV1 + [IBT_OFF, LEGACY_FORCE])
    lib.process()
    assert api.produce.called == 0


def test_report_names_each_argument_and_why(monkeypatch):
    _setup(monkeypatch, CGV1)
    lib.process()
    assert reporting.create_report.called == 1
    report = reporting.create_report.reports[0]
    assert report['severity'] == reporting.Severity.INFO
    assert 'ibt=off' in report['summary']
    assert 'kmod-lve' in report['summary']
    assert 'SYSTEMD_CGROUP_ENABLE_LEGACY_FORCE=1' in report['summary']
    assert 'cgroups-v1' in report['summary']


def test_missing_kernel_cmdline_is_an_error(monkeypatch):
    # Upstream's own consumers of KernelCmdline treat this as fatal too.
    _setup(monkeypatch, [], cmdline=False)
    with pytest.raises(StopActorExecutionError):
        lib.process()


def test_uses_the_shared_cgroups_predicate(monkeypatch):
    """Guard: the v1 decision is made in leapp.libraries.common.cgroups, nowhere else."""
    _setup(monkeypatch, CGV2)
    monkeypatch.setattr(lib, 'requests_legacy_hierarchy', lambda params: True)
    lib.process()
    assert LEGACY_FORCE in _added()
