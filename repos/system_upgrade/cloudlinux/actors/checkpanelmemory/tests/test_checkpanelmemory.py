from leapp import reporting
from leapp.libraries.actor import checkmemory
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked
from leapp.libraries.stdlib import api
from leapp.models import MemoryInfo, InstalledControlPanel

from leapp.libraries.common.detectcontrolpanel import (
    UNKNOWN_NAME,
    INTEGRATED_NAME,
    CPANEL_NAME,
)


def test_check_memory_low(monkeypatch):
    minimum_req_error = []
    monkeypatch.setattr(api, "current_actor", CurrentActorMocked())
    minimum_req_error = checkmemory._check_memory(
        InstalledControlPanel(name=INTEGRATED_NAME), MemoryInfo(mem_total=1024)
    )
    assert minimum_req_error


def test_check_memory_high(monkeypatch):
    minimum_req_error = []
    monkeypatch.setattr(api, "current_actor", CurrentActorMocked())
    minimum_req_error = checkmemory._check_memory(
        InstalledControlPanel(name=CPANEL_NAME), MemoryInfo(mem_total=16273492)
    )
    assert not minimum_req_error


def test_report(monkeypatch):
    title_msg = "Minimum memory requirements for panel {} are not met".format(
        UNKNOWN_NAME
    )
    monkeypatch.setattr(api, "current_actor", CurrentActorMocked())
    monkeypatch.setattr(api, "consume", lambda x: iter([MemoryInfo(mem_total=129)]))
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())
    checkmemory.process()
    assert reporting.create_report.called
    assert title_msg == reporting.create_report.report_fields["title"]
    assert reporting.Flags.INHIBITOR in reporting.create_report.report_fields["flags"]
