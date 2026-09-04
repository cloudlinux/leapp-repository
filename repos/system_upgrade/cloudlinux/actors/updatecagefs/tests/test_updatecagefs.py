import pytest

from leapp.libraries.actor import updatecagefs
from leapp.libraries.common.testutils import CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError

HOOK_INSTALL = [updatecagefs.CAGEFSCTL, '--hook-install']
FORCE_UPDATE = [updatecagefs.CAGEFSCTL, '--force-update']


class _RunMocked(object):
    """
    Fake leapp `run` that records every cagefsctl invocation and can be told to
    fail for a chosen set of commands.
    """

    def __init__(self, failing=()):
        self.failing = [list(cmd) for cmd in failing]
        self.commands = []

    def __call__(self, cmd, checked=True):
        self.commands.append(cmd)
        if cmd in self.failing:
            raise CalledProcessError(
                'boom', cmd, {'exit_code': 1, 'stdout': 'cagefsctl output', 'stderr': ''}
            )
        return {'stdout': ''}


def _setup(monkeypatch, run_mock, cagefsctl_present=True):
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(updatecagefs, 'run', run_mock)
    monkeypatch.setattr(
        updatecagefs.os.path, 'exists',
        lambda path: cagefsctl_present if path == updatecagefs.CAGEFSCTL else False
    )


def test_hooks_are_reinstalled_before_the_cage_rebuild(monkeypatch):
    """
    CageFS reinstalls its PAM hooks from its own %posttrans scriptlet, but
    cagefsctl cannot run inside the upgrade transaction, so on Plesk the
    pam_lve.so line that the CageFS plugin strips from /etc/pam.d/su is never
    put back and CageFS users stop entering the cage through `su`.

    The hooks have to be reinstalled before the cage rebuild, so that the
    corrected /etc/pam.d files are what gets copied into the cages.
    """
    run_mock = _RunMocked()
    _setup(monkeypatch, run_mock)

    updatecagefs.process()

    assert run_mock.commands == [HOOK_INSTALL, FORCE_UPDATE]


def test_nothing_runs_without_cagefsctl(monkeypatch):
    run_mock = _RunMocked()
    _setup(monkeypatch, run_mock, cagefsctl_present=False)

    updatecagefs.process()

    assert not run_mock.commands


def test_failed_hook_install_does_not_skip_the_cage_rebuild(monkeypatch):
    """
    The cage rebuild reflects the whole upgrade and must not be lost because
    the far smaller hook reinstall failed.
    """
    run_mock = _RunMocked(failing=[HOOK_INSTALL])
    _setup(monkeypatch, run_mock)

    updatecagefs.process()

    assert run_mock.commands == [HOOK_INSTALL, FORCE_UPDATE]


@pytest.mark.parametrize('failing,command', [
    ([HOOK_INSTALL], '--hook-install'),
    ([FORCE_UPDATE], '--force-update'),
])
def test_a_failure_is_reported_with_the_command_to_rerun(monkeypatch, failing, command):
    run_mock = _RunMocked(failing=failing)
    _setup(monkeypatch, run_mock)

    updatecagefs.process()

    errors = '\n'.join(api.current_logger().errmsg)
    assert 'cagefsctl output' in errors
    assert command in errors


def test_both_failing_is_survived(monkeypatch):
    run_mock = _RunMocked(failing=[HOOK_INSTALL, FORCE_UPDATE])
    _setup(monkeypatch, run_mock)

    updatecagefs.process()

    assert run_mock.commands == [HOOK_INSTALL, FORCE_UPDATE]
