import os

from leapp import reporting
from leapp.libraries.actor import checkfstabgenerator as lib
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError
from leapp.models import LiveModeConfig

_HERE = os.path.dirname(os.path.abspath(__file__))
_UPSTREAM = os.path.join(_HERE, '..', '..', '..', '..', 'common', 'actors', 'initramfs',
                         'mount_units_generator', 'libraries', 'mount_unit_generator.py')

# What systemd-fstab-generator said on the cPanel CloudLinux 8 QA image, whose
# /etc/fstab lists the /usr/swpDSK swap file twice.
DUPLICATE_SWAP = ('Failed to create unit file /tmp/x/usr-swpDSK.swap, as it already exists.'
                  ' Duplicate entry in /etc/fstab?\n')


def _setup(monkeypatch, fail_with=None, livemode=False):
    calls = []

    def fake_run(cmd, **dummy):
        calls.append(cmd)
        assert os.path.isdir(cmd[1]), 'the generator writes into a directory that exists'
        if fail_with is not None:
            raise CalledProcessError('failed', cmd, {'exit_code': 1, 'stdout': '', 'stderr': fail_with})
        return {'stdout': '', 'stderr': ''}

    msgs = [LiveModeConfig(is_enabled=True, squashfs_fullpath='/x', url_to_load_squashfs_from=None,
                           dracut_network=None, setup_network_manager=False, additional_packages=[],
                           autostart_upgrade_after_reboot=True, setup_opensshd_with_auth_keys=None,
                           setup_passwordless_root=False, capture_upgrade_strace_into=None)] if livemode else []
    monkeypatch.setattr(lib, 'run', fake_run)
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(msgs=msgs))
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    return calls


def test_a_generator_failure_inhibits_with_its_message(monkeypatch):
    """0.24.0's mount_unit_generator runs the same generator inside 'leapp upgrade'
    and aborts it on any failure - after preupgrade has passed. Both cPanel
    CloudLinux 8 QA cells died there on a duplicated swap line."""
    _setup(monkeypatch, fail_with=DUPLICATE_SWAP)

    lib.process()

    assert reporting.create_report.called == 1
    report = reporting.create_report.report_fields
    assert reporting.Groups.INHIBITOR in report['groups']
    assert 'Duplicate entry in /etc/fstab' in report['summary']


def test_a_clean_fstab_does_not_inhibit(monkeypatch):
    _setup(monkeypatch)

    lib.process()

    assert reporting.create_report.called == 0


def test_the_generator_runs_as_mount_unit_generator_runs_it(monkeypatch):
    calls = _setup(monkeypatch)

    lib.process()

    (cmd,) = calls
    assert cmd[0] == '/usr/lib/systemd/system-generators/systemd-fstab-generator'
    assert cmd[1] == cmd[2] == cmd[3]


def test_the_scratch_directory_is_removed(monkeypatch):
    calls = _setup(monkeypatch, fail_with=DUPLICATE_SWAP)

    lib.process()

    assert not os.path.exists(calls[0][1])


def test_livemode_skips_the_check_as_mount_unit_generator_skips_the_generator(monkeypatch):
    calls = _setup(monkeypatch, fail_with=DUPLICATE_SWAP, livemode=True)

    lib.process()

    assert calls == []
    assert reporting.create_report.called == 0


def test_upstream_still_runs_the_generator_this_check_mirrors():
    """This check is only worth its inhibitor while upstream's actor fails the upgrade
    on the same command. If upstream stops calling it, or changes the call, revisit."""
    with open(_UPSTREAM) as fp:
        upstream = fp.read()

    assert lib.GENERATOR in upstream
    assert 'raise StopActorExecutionError' in upstream
