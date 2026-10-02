import pytest

from leapp import reporting
from leapp.libraries.actor import transitionsystemdservicesstates
from leapp.libraries.common.config import version
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import (
    SystemdServiceFile,
    SystemdServicePreset,
    SystemdServicesInfoSource,
    SystemdServicesInfoTarget,
    SystemdServicesPresetInfoSource,
    SystemdServicesPresetInfoTarget,
    SystemdServicesTasks
)


@pytest.mark.parametrize(
    "state_source, preset_source, preset_target, expected",
    (
        ["enabled", "disable", "enable", "enabled"],
        ["enabled", "disable", "disable", "enabled"],
        ["disabled", "disable", "disable", "disabled"],
        ["disabled", "disable", "enable", "enabled"],
        ["masked", "disable", "enable", "masked"],
        ["masked", "disable", "disable", "masked"],
        ["enabled", "enable", "enable", "enabled"],
        ["enabled", "enable", "disable", "enabled"],
        ["masked", "enable", "enable", "masked"],
        ["masked", "enable", "disable", "masked"],
        ["disabled", "enable", "enable", "disabled"],
        ["disabled", "enable", "disable", "disabled"],
        # Unit absent on the source system (new on target): apply the target
        # preset, replicating what a fresh package install would do.
        [None, "disable", "enable", "enabled"],
        [None, "disable", "disable", None],
    ),
)
def test_get_desired_service_state(
    state_source, preset_source, preset_target, expected
):
    target_state = transitionsystemdservicesstates._get_desired_service_state(
        state_source, preset_source, preset_target
    )

    assert target_state == expected


@pytest.mark.parametrize(
    "desired_state, state_target, expected",
    (
        ("enabled", "enabled", SystemdServicesTasks()),
        ("enabled", "disabled", SystemdServicesTasks(to_enable=["test.service"])),
        ("disabled", "enabled", SystemdServicesTasks(to_disable=["test.service"])),
        ("disabled", "disabled", SystemdServicesTasks()),
    ),
)
def test_get_service_task(monkeypatch, desired_state, state_target, expected):
    def _get_desired_service_state_mocked(*args):
        return desired_state

    monkeypatch.setattr(
        transitionsystemdservicesstates,
        "_get_desired_service_state",
        _get_desired_service_state_mocked,
    )

    tasks = SystemdServicesTasks()
    transitionsystemdservicesstates._get_service_task(
        "test.service", desired_state, state_target, tasks
    )
    assert tasks == expected


def test_filter_irrelevant_services_services_filtered():
    services_source = {
        "test2.service": "static",
        "test3.service": "masked",
        "test4.service": "indirect",
        "test5.service": "indirect",
        "test6.service": "masked-runtime",
    }
    services_target = [
        SystemdServiceFile(name="test2.service", state="masked"),
        SystemdServiceFile(name="test3.service", state="indirect"),
        SystemdServiceFile(name="test4.service", state="static"),
        SystemdServiceFile(name="test5.service", state="generated"),
        # Enable-able target state, but masked-runtime on the source -> filtered
        SystemdServiceFile(name="test6.service", state="enabled"),
    ]

    filtered = transitionsystemdservicesstates._filter_irrelevant_services(
        services_source, services_target
    )

    assert not filtered


def test_filter_irrelevant_services_keeps_new_target_units():
    # Units absent on the source but in an enable/disable-able state are new on
    # the target and must be kept so the target preset can be applied to them.
    services_source = {}
    services_target = [
        SystemdServiceFile(name="new-enabled.service", state="enabled"),
        SystemdServiceFile(name="new-disabled.timer", state="disabled"),
        SystemdServiceFile(name="new-static.service", state="static"),
    ]

    filtered = transitionsystemdservicesstates._filter_irrelevant_services(
        services_source, services_target
    )

    assert [s.name for s in filtered] == ["new-enabled.service", "new-disabled.timer"]


def test_filter_irrelevant_services_drops_ignored_units():
    # Ignored units are removed from the source inventory, which must not make
    # them look new on the target - otherwise the target preset gets applied to
    # a unit that was deliberately excluded from handling.
    services_source = {}
    services_target = [
        SystemdServiceFile(name="virtqemud.service", state="disabled"),
        SystemdServiceFile(name="new-disabled.timer", state="disabled"),
    ]

    filtered = transitionsystemdservicesstates._filter_irrelevant_services(
        services_source, services_target, ignored_services={"virtqemud.service"}
    )

    assert [s.name for s in filtered] == ["new-disabled.timer"]


def test_filter_irrelevant_services_services_not_filtered():
    services_source = {
        "test1.service": "enabled",
        "test2.service": "disabled",
        "test3.service": "static",
        "test4.service": "indirect",
    }
    services_target = [
        SystemdServiceFile(name="test1.service", state="enabled"),
        SystemdServiceFile(name="test2.service", state="disabled"),
        SystemdServiceFile(name="test3.service", state="enabled-runtime"),
        SystemdServiceFile(name="test4.service", state="enabled"),
    ]

    filtered = transitionsystemdservicesstates._filter_irrelevant_services(
        services_source, services_target
    )

    assert len(filtered) == len(services_target)


@pytest.mark.parametrize(
    "presets",
    [
        dict(),
        {"other.service": "enable"},
    ],
)
def test_service_preset_missing_presets(presets):
    preset = transitionsystemdservicesstates._get_service_preset(
        "test.service", presets
    )
    assert preset == "disable"


def test_tasks_produced_reports_created(monkeypatch):
    services_source = [
        SystemdServiceFile(name="rsyncd.service", state="enabled"),
        SystemdServiceFile(name="test.service", state="enabled"),
        SystemdServiceFile(name="newly_enabled.service", state="disabled"),
    ]
    service_info_source = SystemdServicesInfoSource(service_files=services_source)

    presets_source = [
        SystemdServicePreset(service="rsyncd.service", state="enable"),
        SystemdServicePreset(service="test.service", state="enable"),
        SystemdServicePreset(service="newly_enabled.service", state="disable"),
    ]
    preset_info_source = SystemdServicesPresetInfoSource(presets=presets_source)

    services_target = [
        SystemdServiceFile(name="rsyncd.service", state="disabled"),
        SystemdServiceFile(name="test.service", state="enabled"),
        SystemdServiceFile(name="newly_enabled.service", state="enabled"),
    ]
    service_info_target = SystemdServicesInfoTarget(service_files=services_target)

    presets_target = [
        SystemdServicePreset(service="rsyncd.service", state="enable"),
        SystemdServicePreset(service="test.service", state="enable"),
        SystemdServicePreset(service="newly_enabled.service", state="enable"),
    ]
    preset_info_target = SystemdServicesPresetInfoTarget(presets=presets_target)

    monkeypatch.setattr(
        api,
        "current_actor",
        CurrentActorMocked(
            msgs=[
                service_info_source,
                service_info_target,
                preset_info_source,
                preset_info_target,
            ]
        ),
    )
    monkeypatch.setattr(api, "produce", produce_mocked())
    created_reports = create_report_mocked()
    monkeypatch.setattr(reporting, "create_report", created_reports)

    expected_tasks = SystemdServicesTasks(to_enable=["rsyncd.service"], to_disable=[])
    transitionsystemdservicesstates.process()

    assert created_reports.called == 2
    assert api.produce.called
    assert api.produce.model_instances[0].to_enable == expected_tasks.to_enable
    assert api.produce.model_instances[0].to_disable == expected_tasks.to_disable


def test_new_target_unit_enabled_by_preset(monkeypatch):
    """
    A unit that does not exist on the source but is shipped enabled-by-preset on
    the target (e.g. logrotate.timer on EL8->EL9) must be enabled, even though it
    was left disabled by the package upgrade scriptlet.
    """
    service_info_source = SystemdServicesInfoSource(service_files=[
        SystemdServiceFile(name="test.service", state="enabled"),
    ])
    preset_info_source = SystemdServicesPresetInfoSource(presets=[
        SystemdServicePreset(service="test.service", state="enable"),
    ])

    services_target = [
        SystemdServiceFile(name="test.service", state="enabled"),
        # New unit, left disabled by the upgrade (preset not applied on upgrade)
        SystemdServiceFile(name="logrotate.timer", state="disabled"),
    ]
    service_info_target = SystemdServicesInfoTarget(service_files=services_target)
    preset_info_target = SystemdServicesPresetInfoTarget(presets=[
        SystemdServicePreset(service="test.service", state="enable"),
        SystemdServicePreset(service="logrotate.timer", state="enable"),
    ])

    monkeypatch.setattr(
        api,
        "current_actor",
        CurrentActorMocked(
            msgs=[
                service_info_source,
                service_info_target,
                preset_info_source,
                preset_info_target,
            ]
        ),
    )
    monkeypatch.setattr(api, "produce", produce_mocked())
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())

    transitionsystemdservicesstates.process()

    assert api.produce.called
    assert api.produce.model_instances[0].to_enable == ["logrotate.timer"]
    assert api.produce.model_instances[0].to_disable == []


@pytest.mark.parametrize(
    "tasks, expect_extended_summary",
    (
        (
            SystemdServicesTasks(
                to_enable=["test.service", "other.service"],
                to_disable=["another.service"],
            ),
            True,
        ),
        (SystemdServicesTasks(), False),
        (SystemdServicesTasks(to_enable=[], to_disable=["some.service"]), False),
    ),
)
def test_report_kept_enabled(monkeypatch, tasks, expect_extended_summary):
    created_reports = create_report_mocked()
    monkeypatch.setattr(reporting, "create_report", created_reports)

    transitionsystemdservicesstates._report_kept_enabled(tasks)

    extended_summary_str = (
        "The following services were originally disabled by preset on the"
        " upgraded system and Leapp attempted to enable them"
    )

    assert created_reports.called == 1
    if expect_extended_summary:
        assert extended_summary_str in created_reports.report_fields["summary"]
        all(s in created_reports.report_fields['summary'] for s in tasks.to_enable)
    else:
        assert extended_summary_str not in created_reports.report_fields["summary"]


def test_get_newly_enabled():
    services_source = {
        "test.service": "disabled",
        "other.service": "enabled",
        "another.service": "enabled",
    }
    desired_states = {
        "test.service": "enabled",
        "other.service": "enabled",
        "another.service": "disabled",
    }

    newly_enabled = transitionsystemdservicesstates._get_newly_enabled(
        services_source, desired_states
    )
    assert newly_enabled == ["test.service"]


@pytest.mark.parametrize(
    "newly_enabled, should_report",
    [
        (["test.service", "other.service"], True),
        ([], False),
    ]
)
def test_report_newly_enabled(monkeypatch, newly_enabled, should_report):
    created_reports = create_report_mocked()
    monkeypatch.setattr(reporting, "create_report", created_reports)

    transitionsystemdservicesstates._report_newly_enabled(newly_enabled)

    if should_report:
        assert created_reports.called == 1
        assert all(s in created_reports.report_fields["summary"] for s in newly_enabled)
    else:
        assert not created_reports.called


@pytest.mark.parametrize(
    "source_major_ver,expected", (
        (
            7,
            {
                'abc.service': 'enabled',
                'virtqemud.service': 'enabled',
                'virtlogd.service': 'disabled',
                'virtproxyd.service': 'masked',
            }
        ),
        (8, {'abc.service': 'enabled'}),
        (9, {'abc.service': 'enabled'}),
    )
)
def test_filter_ignored_services(monkeypatch, source_major_ver, expected):
    services = {
        'abc.service': 'enabled',
        'virtqemud.service': 'enabled',
        'virtlogd.service': 'disabled',
        'virtproxyd.service': 'masked',
    }
    services_before = dict(services)
    monkeypatch.setattr(
        version,
        "get_source_major_version",
        lambda: source_major_ver,
    )
    ignored = transitionsystemdservicesstates._filter_ignored_services(services)
    assert services == expected

    # The ignored names must be reported back, so target filtering can exclude
    # them too instead of mistaking them for units new on the target. The set
    # covers the whole libvirt group, not only the entries that happened to be
    # present in the source inventory.
    if int(source_major_ver) < 8:
        assert ignored == set()
    else:
        assert {
            'libvirtd.service',
            'virtqemud.service',
            'virtlogd.service',
            'virtproxyd.service',
            'libvirt-guests.service',
        }.issubset(ignored)
        # everything dropped from the inventory is accounted for
        assert not set(services_before) - set(services) - ignored


def test_ignored_libvirt_service_is_not_enabled_by_target_preset(monkeypatch):
    """
    Regression test for the CL8+ libvirt exclusion.

    virtqemud.service is excluded from handling on 8->9+ by removing it from the
    source inventory. It is present but disabled on the target, and the CL9
    vendor preset enables it, so it must still be left alone - enabling it would
    reinstate the invalid monolithic/modular libvirt combination the exclusion
    exists to prevent.
    """
    service_info_source = SystemdServicesInfoSource(service_files=[
        SystemdServiceFile(name="virtqemud.service", state="disabled"),
        SystemdServiceFile(name="test.service", state="enabled"),
    ])
    preset_info_source = SystemdServicesPresetInfoSource(presets=[
        SystemdServicePreset(service="virtqemud.service", state="disable"),
        SystemdServicePreset(service="test.service", state="enable"),
    ])
    service_info_target = SystemdServicesInfoTarget(service_files=[
        SystemdServiceFile(name="virtqemud.service", state="disabled"),
        SystemdServiceFile(name="test.service", state="enabled"),
    ])
    preset_info_target = SystemdServicesPresetInfoTarget(presets=[
        SystemdServicePreset(service="virtqemud.service", state="enable"),
        SystemdServicePreset(service="test.service", state="enable"),
    ])

    monkeypatch.setattr(version, "get_source_major_version", lambda: '8')
    monkeypatch.setattr(
        api,
        "current_actor",
        CurrentActorMocked(
            msgs=[
                service_info_source,
                service_info_target,
                preset_info_source,
                preset_info_target,
            ]
        ),
    )
    monkeypatch.setattr(api, "produce", produce_mocked())
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())

    transitionsystemdservicesstates.process()

    assert api.produce.called
    assert api.produce.model_instances[0].to_enable == []
    assert api.produce.model_instances[0].to_disable == []
