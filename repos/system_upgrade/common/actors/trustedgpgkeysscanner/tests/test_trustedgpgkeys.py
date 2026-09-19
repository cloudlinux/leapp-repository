import os

from leapp import reporting
from leapp.libraries.actor import trustedgpgkeys
from leapp.libraries.common.gpg import get_pubkeys_from_rpms
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import GpgKey, InstalledRPM, RPM, TrustedGpgKeys


def _get_test_installed_rmps(fps):
    # adding at least one rpm that is not gpg-pubkey
    rpms = [RPM(
        name='rpm',
        version='4.17.1',
        release='3.fc35',
        epoch='0',
        packager='Fedora Project',
        arch='x86_64',
        pgpsig='RSA/SHA256, Tue 02 Aug 2022 03:12:43 PM CEST, Key ID db4639719867c58f'
    )]
    for fp in fps:
        rpms.append(RPM(
            name='gpg-pubkey',
            version=fp,
            release='5e3006fb',
            epoch='0',
            packager='Fedora (33) <fedora-33-primary@fedoraproject.org>',
            arch='noarch',
            pgpsig=''
        ))
    return InstalledRPM(items=rpms)


class MockedGetGpgFromFile:
    def __init__(self, file_fps_tuples):
        # e.g. file_fps_tuple = [('/mydir/myfile', ['0000ff31', '0000ff32'])]
        self._data = {}
        for fname, fps in file_fps_tuples:
            self._data[fname] = fps

    def get_files(self):
        return self._data.keys()

    def __call__(self, fname):
        return self._data.get(fname, [])


def test_get_pubkeys(monkeypatch):
    """
    Very basic test of _get_pubkeys function
    """
    rpm_fps = ['9570ff31', '99900000']
    file_fps = ['0000ff31', '0000ff32']
    installed_rpms = _get_test_installed_rmps(rpm_fps)
    mocked_gpg_files = MockedGetGpgFromFile([('/mydir/myfile', ['0000ff31', '0000ff32'])])

    def _mocked_listdir(dummy):
        return [os.path.basename(i) for i in mocked_gpg_files.get_files()]

    monkeypatch.setattr(trustedgpgkeys.os, 'listdir', _mocked_listdir)
    monkeypatch.setattr(trustedgpgkeys.os.path, 'isdir', lambda path: True)
    monkeypatch.setattr(trustedgpgkeys, 'get_path_to_gpg_certs', lambda: ['/mydir/'])
    monkeypatch.setattr(trustedgpgkeys, 'get_gpg_fp_from_file', mocked_gpg_files)

    pubkeys = trustedgpgkeys._get_pubkeys(installed_rpms)
    assert len(pubkeys) == len(rpm_fps + file_fps)
    assert set(rpm_fps) == {pkey.fingerprint for pkey in pubkeys if pkey.rpmdb}
    assert set(file_fps) == {pkey.fingerprint for pkey in pubkeys if not pkey.rpmdb}
    assert list({pkey.filename for pkey in pubkeys if not pkey.rpmdb})[0] == '/mydir/myfile'


def test_process(monkeypatch):
    """
    Executes the "main" function
    """
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(
        msgs=[_get_test_installed_rmps(['9570ff31'])])
    )
    monkeypatch.setattr(api, 'produce', produce_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    monkeypatch.setattr(trustedgpgkeys, '_get_pubkeys', get_pubkeys_from_rpms)

    trustedgpgkeys.process()
    assert api.produce.called == 1
    assert isinstance(api.produce.model_instances[0], TrustedGpgKeys)
    assert reporting.create_report.called == 0


def test_missing_trusted_dir_is_skipped(monkeypatch):
    """A trusted-key directory that does not exist must not kill the actor.

    get_path_to_gpg_certs() returns a path per target distro and major version,
    and nothing guarantees the tree has one for every combination. Before this,
    os.listdir raised FileNotFoundError straight out of an actor - the CL9 -> CL10
    run died on distro/cloudlinux/rpm-gpg/10 with no report and no inhibitor,
    just a terminated actor.
    """
    monkeypatch.setattr(
        trustedgpgkeys, 'get_path_to_gpg_certs',
        lambda: ['/nonexistent/one', '/nonexistent/two']
    )
    monkeypatch.setattr(trustedgpgkeys, 'get_pubkeys_from_rpms', lambda rpms: [])

    assert trustedgpgkeys._get_pubkeys(None) == []
