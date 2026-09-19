import pytest

from leapp.libraries.actor import checkcgroupstunedprofile as lib


@pytest.mark.parametrize(
    ('profile', 'expected'),
    [
        ('cloudlinux-default-cgv1', 'cloudlinux-default-cgv2'),
        ('cloudlinux-latency-performance-cgv1', 'cloudlinux-latency-performance-cgv2'),
        # Already on v2, or not a paired profile at all: nothing to suggest.
        ('cloudlinux-default-cgv2', None),
        ('cloudlinux-default', None),
        ('virtual-guest', None),
        ('', None),
        (None, None),
    ],
)
def test_cgv2_counterpart(profile, expected):
    assert lib.cgv2_counterpart(profile) == expected


def test_kernel_uses_cgroups_v1():
    """Same condition upstream's inhibit_cgroupsv1 tests, read from the cmdline."""
    assert lib.kernel_uses_cgroups_v1(
        ['systemd.unified_cgroup_hierarchy=0', 'systemd.legacy_systemd_cgroup_controller']) is True
    assert lib.kernel_uses_cgroups_v1(['systemd.unified_cgroup_hierarchy=false']) is True
    # The default since RHEL 9 is the unified hierarchy.
    assert lib.kernel_uses_cgroups_v1(['ro', 'quiet']) is False
    assert lib.kernel_uses_cgroups_v1(['cgroup_no_v1=all']) is False
    assert lib.kernel_uses_cgroups_v1(['systemd.unified_cgroup_hierarchy=1']) is False


def test_reports_only_when_both_conditions_hold(monkeypatch):
    """The advice is specific to a cgv1 tuned profile, not to cgroups-v1 generally.

    A host on cgroups-v1 without a CloudLinux tuned profile is upstream's case and
    upstream's remediation works there, so saying anything would be noise.
    """
    calls = []
    monkeypatch.setattr(lib.reporting, 'create_report', lambda parts: calls.append(parts))

    monkeypatch.setattr(lib, 'get_active_tuned_profile', lambda: 'virtual-guest')
    lib.check(['systemd.unified_cgroup_hierarchy=0'])
    assert calls == []

    monkeypatch.setattr(lib, 'get_active_tuned_profile', lambda: 'cloudlinux-default-cgv1')
    lib.check(['cgroup_no_v1=all'])
    assert calls == []

    monkeypatch.setattr(lib, 'get_active_tuned_profile', lambda: 'cloudlinux-default-cgv1')
    lib.check(['systemd.unified_cgroup_hierarchy=0'])
    assert len(calls) == 1
    summary = next(p.value for p in calls[0] if isinstance(p, lib.reporting.Summary))
    assert 'cloudlinux-default-cgv2' in summary
    assert 'grubby' in summary          # says why the stock remediation does nothing
    assert 'tuned' in summary

    commands = str(calls[0])
    assert 'tuned-adm profile cloudlinux-default-cgv2' in commands
