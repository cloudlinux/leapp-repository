import os

import pytest

from leapp import reporting
from leapp.libraries.actor import updatealmalinuxkey
from leapp.libraries.common.testutils import create_report_mocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError


def test_imports_the_shipped_key_for_the_target(monkeypatch, tmpdir):
    """
    The key that has to be imported is the target major's.

    The unversioned https://repo.almalinux.org/almalinux/RPM-GPG-KEY-AlmaLinux
    serves the AlmaLinux 8 keys and nothing else - it was added for the 2023
    AlmaLinux 8 key rotation and never made version-aware. Importing it before
    an upgrade to 10 puts the wrong key in the rpmdb, so target packages signed
    by the AlmaLinux 10 key are unverifiable.

    leapp already ships the right key per target major, so it is read from disk:
    no network, and the key is the one this package was built against.
    """
    certs_dir = tmpdir.mkdir('rpm-gpg').mkdir('10')
    key = certs_dir.join('RPM-GPG-KEY-AlmaLinux-10')
    key.write('-----BEGIN PGP PUBLIC KEY BLOCK-----\n')
    commands = _run_recorder(monkeypatch)
    monkeypatch.setattr(updatealmalinuxkey, 'get_path_to_gpg_certs', lambda: [str(certs_dir)])

    updatealmalinuxkey.process()

    assert commands == [['rpm', '--import', str(key)]]


def test_every_shipped_key_is_imported(monkeypatch, tmpdir):
    """Both the AlmaLinux and the CloudLinux key ship for a target; import each."""
    certs_dir = tmpdir.mkdir('both')
    for name in ('RPM-GPG-KEY-AlmaLinux-10', 'RPM-GPG-KEY-CloudLinux'):
        certs_dir.join(name).write('-----BEGIN PGP PUBLIC KEY BLOCK-----\n')
    commands = _run_recorder(monkeypatch)
    monkeypatch.setattr(updatealmalinuxkey, 'get_path_to_gpg_certs', lambda: [str(certs_dir)])

    updatealmalinuxkey.process()

    imported = sorted(os.path.basename(cmd[-1]) for cmd in commands)
    assert imported == ['RPM-GPG-KEY-AlmaLinux-10', 'RPM-GPG-KEY-CloudLinux']


def test_missing_directory_is_skipped_not_fatal(monkeypatch, tmpdir):
    """
    One of the directories get_path_to_gpg_certs() returns is
    /etc/leapp/files/vendors.d/rpm-gpg/, which exists only when a vendor ships
    keys. A absent directory is normal and must not raise.
    """
    present = tmpdir.mkdir('present')
    present.join('RPM-GPG-KEY-AlmaLinux-10').write('-----BEGIN PGP PUBLIC KEY BLOCK-----\n')
    commands = _run_recorder(monkeypatch)
    monkeypatch.setattr(
        updatealmalinuxkey, 'get_path_to_gpg_certs',
        lambda: [str(tmpdir.join('does-not-exist')), str(present)]
    )

    updatealmalinuxkey.process()

    assert len(commands) == 1


def test_failed_import_inhibits(monkeypatch, tmpdir):
    """A key that will not import is a target transaction that cannot verify."""
    certs_dir = tmpdir.mkdir('broken')
    certs_dir.join('RPM-GPG-KEY-AlmaLinux-10').write('not a key\n')

    def _boom(cmd, *dummy_args, **dummy_kwargs):
        raise CalledProcessError('failed', cmd, {'exit_code': 1, 'stdout': '', 'stderr': ''})

    monkeypatch.setattr(updatealmalinuxkey, 'run', _boom)
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(updatealmalinuxkey, 'get_path_to_gpg_certs', lambda: [str(certs_dir)])

    updatealmalinuxkey.process()

    assert reporting.create_report.called == 1
    assert reporting.Groups.INHIBITOR in reporting.create_report.report_fields['groups']


def test_no_keys_found_inhibits(monkeypatch, tmpdir):
    """
    Importing nothing at all is not success. If the shipped key tree is empty
    the download phase proceeds and fails later on signature verification, with
    an error that says nothing about the key never having been imported.
    """
    commands = _run_recorder(monkeypatch)
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    empty = str(tmpdir.mkdir('empty'))
    monkeypatch.setattr(updatealmalinuxkey, 'get_path_to_gpg_certs', lambda: [empty])

    updatealmalinuxkey.process()

    assert not commands
    assert reporting.create_report.called == 1
    assert reporting.Groups.INHIBITOR in reporting.create_report.report_fields['groups']


def _run_recorder(monkeypatch):
    commands = []

    def _run(cmd, *dummy_args, **dummy_kwargs):
        commands.append(cmd)
        return {'stdout': '', 'stderr': '', 'exit_code': 0}

    monkeypatch.setattr(updatealmalinuxkey, 'run', _run)
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    return commands
