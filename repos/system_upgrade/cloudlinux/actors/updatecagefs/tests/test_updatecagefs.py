
import pytest

from leapp import reporting
from leapp.libraries.actor import updatecagefs
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError

HOOK_INSTALL = [updatecagefs.CAGEFSCTL, '--hook-install']
FORCE_UPDATE = [updatecagefs.CAGEFSCTL, '--force-update']

PAM_SU_WITH_LVE = """#%PAM-1.0
auth\t\trequired\tpam_env.so
session\t\tinclude\t\tsystem-auth
session      required      pam_lve.so      500      1
"""
PAM_SU_STOCK = """#%PAM-1.0
auth\t\trequired\tpam_env.so
session\t\tinclude\t\tsystem-auth
"""


class _RunMocked(object):
    """
    Fake leapp `run` that records every cagefsctl invocation and can be told to
    fail for a chosen set of commands, with either exception `run` documents.
    """

    def __init__(self, failing=(), exc=CalledProcessError):
        self.failing = [list(cmd) for cmd in failing]
        self.exc = exc
        self.commands = []

    def __call__(self, cmd, checked=True):
        self.commands.append(cmd)
        if cmd in self.failing:
            if self.exc is OSError:
                raise OSError(2, 'No such file or directory', cmd[0])
            raise CalledProcessError(
                'boom', cmd, {'exit_code': 1, 'stdout': 'cagefsctl output', 'stderr': ''}
            )
        return {'stdout': ''}


def _setup(monkeypatch, tmp_path, run_mock, cagefsctl_present=True, pam_su=PAM_SU_WITH_LVE):
    """
    Point the library at a real /etc/pam.d/su stand-in, so the pam check runs
    for real rather than being stubbed out.
    """
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(updatecagefs, 'run', run_mock)
    monkeypatch.setattr(
        updatecagefs.os.path, 'exists',
        lambda path: cagefsctl_present if path == updatecagefs.CAGEFSCTL else False
    )
    if pam_su is not None:
        pam_file = tmp_path / 'su'
        pam_file.write_text(pam_su)
        monkeypatch.setattr(updatecagefs, 'PAM_SU_CONFIG', str(pam_file))
    else:
        monkeypatch.setattr(updatecagefs, 'PAM_SU_CONFIG', str(tmp_path / 'absent'))
    reports = create_report_mocked()
    monkeypatch.setattr(reporting, 'create_report', reports)
    return reports


def test_hooks_are_reinstalled_before_the_cage_rebuild(monkeypatch, tmp_path):
    """
    CageFS reinstalls its PAM hooks from its own %posttrans scriptlet, but
    cagefsctl cannot run inside the upgrade transaction, so on Plesk the
    pam_lve.so line that the CageFS plugin strips from /etc/pam.d/su is never
    put back and CageFS users stop entering the cage through `su`.

    The hooks have to be reinstalled before the cage rebuild, so that the
    corrected /etc/pam.d files are what gets copied into the cages.
    """
    run_mock = _RunMocked()
    reports = _setup(monkeypatch, tmp_path, run_mock)

    updatecagefs.process()

    assert run_mock.commands == [HOOK_INSTALL, FORCE_UPDATE]
    assert reports.called == 0


def test_nothing_runs_without_cagefsctl(monkeypatch, tmp_path):
    run_mock = _RunMocked()
    reports = _setup(monkeypatch, tmp_path, run_mock, cagefsctl_present=False)

    updatecagefs.process()

    assert not run_mock.commands
    assert reports.called == 0


@pytest.mark.parametrize('exc', [CalledProcessError, OSError])
def test_failed_hook_install_does_not_skip_the_cage_rebuild(monkeypatch, tmp_path, exc):
    """
    The cage rebuild reflects the whole upgrade and must not be lost because
    the far smaller hook reinstall failed. A cagefsctl that exists but is not
    executable - the shape of leapp's own zero-byte new-kernel-pkg stub - makes
    `run` raise OSError rather than CalledProcessError, and that must not abort
    the actor either.
    """
    run_mock = _RunMocked(failing=[HOOK_INSTALL], exc=exc)
    _setup(monkeypatch, tmp_path, run_mock, pam_su=PAM_SU_STOCK)

    updatecagefs.process()

    assert run_mock.commands == [HOOK_INSTALL, FORCE_UPDATE]


@pytest.mark.parametrize('exc', [CalledProcessError, OSError])
def test_a_failing_cage_rebuild_is_survived_and_logged(monkeypatch, tmp_path, exc):
    run_mock = _RunMocked(failing=[FORCE_UPDATE], exc=exc)
    _setup(monkeypatch, tmp_path, run_mock)

    updatecagefs.process()

    errors = '\n'.join(api.current_logger().errmsg)
    assert '--force-update' in errors


def test_silent_hook_install_failure_is_caught_by_the_outcome_check(monkeypatch, tmp_path):
    """
    `cagefsctl --hook-install` exits zero whatever happens: cagefsctl calls
    HooksInstall() and then sys.exit(0) unconditionally, and configure_pam_lve
    swallows IOError/OSError into a printed message. So an immutable or
    read-only /etc/pam.d/su leaves CageFS users uncaged with a clean exit code.
    Only checking the resulting configuration catches that.
    """
    run_mock = _RunMocked()
    reports = _setup(monkeypatch, tmp_path, run_mock, pam_su=PAM_SU_STOCK)

    updatecagefs.process()

    assert run_mock.commands == [HOOK_INSTALL, FORCE_UPDATE]
    assert reports.called == 1
    assert 'su' in reports.report_fields['title']
    assert reporting.Severity.HIGH == reports.report_fields['severity']
    errors = '\n'.join(api.current_logger().errmsg)
    assert '--hook-install' in errors


def test_commented_out_pam_lve_line_does_not_count_as_configured(monkeypatch, tmp_path):
    run_mock = _RunMocked()
    reports = _setup(
        monkeypatch, tmp_path, run_mock,
        pam_su=PAM_SU_STOCK + '#session      required      pam_lve.so      500      1\n'
    )

    updatecagefs.process()

    assert reports.called == 1


def test_unreadable_pam_config_is_reported_rather_than_assumed_fine(monkeypatch, tmp_path):
    run_mock = _RunMocked()
    reports = _setup(monkeypatch, tmp_path, run_mock, pam_su=None)

    updatecagefs.process()

    assert reports.called == 1
