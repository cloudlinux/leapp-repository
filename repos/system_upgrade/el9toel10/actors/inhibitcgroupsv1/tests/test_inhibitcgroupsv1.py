import pytest

from leapp import reporting
from leapp.libraries.actor import inhibitcgroupsv1
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked
from leapp.libraries.stdlib import api
from leapp.models import KernelCmdline, KernelCmdlineArg


@pytest.mark.parametrize(
    "cmdline_params", (
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="0")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="false")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="False")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="no")]),
        (
            [
                KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="0"),
                KernelCmdlineArg(key="systemd.legacy_systemd_cgroup_controller", value="0"),
            ]
        ), (
            [
                KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="0"),
                KernelCmdlineArg(key="systemd.legacy_systemd_cgroup_controller", value="1"),
            ]
        )
    )
)
def test_inhibit_should_inhibit(monkeypatch, cmdline_params):
    curr_actor_mocked = CurrentActorMocked(msgs=[KernelCmdline(parameters=cmdline_params)])
    monkeypatch.setattr(api, "current_actor", curr_actor_mocked)
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())

    inhibitcgroupsv1.process()

    assert reporting.create_report.called == 1
    report = reporting.create_report.reports[0]
    assert "cgroups-v1" in report["title"]
    assert reporting.Groups.INHIBITOR in report["groups"]

    command = [r for r in report["detail"]["remediations"] if r["type"] == "command"][0]
    assert "systemd.unified_cgroup_hierarchy" in command['context'][2]
    if len(cmdline_params) == 2:
        assert "systemd.legacy_systemd_cgroup_controller" in command['context'][2]


@pytest.mark.parametrize(
    "cmdline_params", (
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="1")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="true")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="True")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="yes")]),
        ([KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value=None)]),
        (
            [
                KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="1"),
                KernelCmdlineArg(key="systemd.legacy_systemd_cgroup_controller", value="1"),
            ]
        ), (
            [
                KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="1"),
                KernelCmdlineArg(key="systemd.legacy_systemd_cgroup_controller", value="0"),
            ]
        ),
    )
)
def test_inhibit_should_not_inhibit(monkeypatch, cmdline_params):
    curr_actor_mocked = CurrentActorMocked(msgs=[KernelCmdline(parameters=cmdline_params)])
    monkeypatch.setattr(api, "current_actor", curr_actor_mocked)
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())

    inhibitcgroupsv1.process()

    assert not reporting.create_report.called


def test_cloudlinux_keeps_cgroups_v1_without_inhibiting(monkeypatch):
    """CloudLinux does not force the move to cgroups-v2.

    The upstream inhibitor states that cgroups-v1 support "is removed in RHEL
    10". Measured on a CloudLinux 10.2 box booted with
    systemd.unified_cgroup_hierarchy=0: it is deprecated and off by default, not
    removed. The el10 kernel carries CONFIG_MEMCG_V1=y and CONFIG_CPUSETS_V1=y,
    /proc/cgroups lists controllers on real v1 hierarchies, kmod-lve registers
    ("lve driver register status 0" - it autodetects the hierarchy and keeps a
    full v1 path), and LVE and CageFS enforce exactly as they do under v2.

    So the inhibitor is upstream policy rather than a kernel limit, and keeping
    software working across a major upgrade is the product's purpose. LVE on
    cgroups-v2 is also the less proven of the two today, so forcing the switch
    costs stability and buys nothing.

    A report still goes out, because the deprecation is real and an admin should
    know - but it does not block the upgrade.
    """
    cmdline_params = [
        KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="0"),
        KernelCmdlineArg(key="systemd.legacy_systemd_cgroup_controller", value="1"),
    ]
    curr_actor_mocked = CurrentActorMocked(
        msgs=[KernelCmdline(parameters=cmdline_params)], release_id='cloudlinux'
    )
    monkeypatch.setattr(api, "current_actor", curr_actor_mocked)
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())

    inhibitcgroupsv1.process()

    assert reporting.create_report.called == 1
    report = reporting.create_report.reports[0]
    assert reporting.Groups.INHIBITOR not in report["groups"]
    assert "cgroups-v1" in report["title"]


def test_other_distros_still_inhibit(monkeypatch):
    """The divergence is CloudLinux-only; nothing changes for anyone else."""
    cmdline_params = [KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="0")]
    curr_actor_mocked = CurrentActorMocked(
        msgs=[KernelCmdline(parameters=cmdline_params)], release_id='almalinux'
    )
    monkeypatch.setattr(api, "current_actor", curr_actor_mocked)
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())

    inhibitcgroupsv1.process()

    assert reporting.Groups.INHIBITOR in reporting.create_report.reports[0]["groups"]


def test_uses_the_shared_cgroups_predicate(monkeypatch):
    """Guard: the v1 decision is made in leapp.libraries.common.cgroups, nowhere else."""
    params = [KernelCmdlineArg(key="systemd.unified_cgroup_hierarchy", value="0")]
    monkeypatch.setattr(api, "current_actor", CurrentActorMocked(msgs=[KernelCmdline(parameters=params)]))
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())
    monkeypatch.setattr(inhibitcgroupsv1, "requests_legacy_hierarchy", lambda parameters: False)

    inhibitcgroupsv1.process()

    assert reporting.create_report.called == 0
