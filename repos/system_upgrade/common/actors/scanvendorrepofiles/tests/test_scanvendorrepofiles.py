import os

from leapp.libraries.actor import scanvendorrepofiles
from leapp.libraries.common import repofileutils
from leapp.libraries.common.testutils import CurrentActorMocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import (
    ActiveVendorList,
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RepositoryData,
    RepositoryFile,
    VendorCustomTargetRepositoryList
)

_VENDOR = 'somevendor'
_REPOFILE_NAME = '{}.repo'.format(_VENDOR)
_REPOFILE_PATH = os.path.join(scanvendorrepofiles.VENDORS_DIR, _REPOFILE_NAME)

_REPODATA = [
    RepositoryData(repoid='repo1', name='repo1name', baseurl='repo1url', enabled=True),
    RepositoryData(repoid='repo2', name='repo2name', baseurl='repo2url', enabled=False),
]


def _mock_repofile(fpath):
    return RepositoryFile(file=fpath, data=_REPODATA)


def _setup(monkeypatch, listdir, active_vendors, isdir=True):
    monkeypatch.setattr(os.path, 'isdir', lambda dummy: isdir)
    monkeypatch.setattr(os, 'listdir', lambda dummy: listdir)
    monkeypatch.setattr(repofileutils, 'parse_repofile', _mock_repofile)
    monkeypatch.setattr(api, 'produce', produce_mocked())
    monkeypatch.setattr(
        api, 'current_actor',
        CurrentActorMocked(msgs=[ActiveVendorList(data=active_vendors)])
    )


def test_no_vendors_dir(monkeypatch):
    """With no vendors.d directory there is nothing to produce."""
    _setup(monkeypatch, [_REPOFILE_NAME], [_VENDOR], isdir=False)

    scanvendorrepofiles.process()

    assert api.produce.called == 0


def test_active_vendor_repofile_is_loaded(monkeypatch):
    """A repofile whose vendor is active produces the file message and its repos."""
    _setup(monkeypatch, [_REPOFILE_NAME], [_VENDOR])

    scanvendorrepofiles.process()

    assert CustomTargetRepositoryFile(file=_REPOFILE_PATH) in api.produce.model_instances

    produced_lists = [
        msg for msg in api.produce.model_instances if isinstance(msg, VendorCustomTargetRepositoryList)
    ]
    assert len(produced_lists) == 1
    assert produced_lists[0].vendor == _VENDOR
    assert produced_lists[0].repos == [
        CustomTargetRepository(repoid='repo1', name='repo1name', baseurl='repo1url', enabled=True),
        CustomTargetRepository(repoid='repo2', name='repo2name', baseurl='repo2url', enabled=False),
    ]


def test_inactive_vendor_repofile_is_skipped(monkeypatch):
    """A repofile present on disk but not in the active list must be ignored.

    This is the whole point of the actor: vendor repositories are only carried
    over when the vendor's source repositories were actually in use.
    """
    _setup(monkeypatch, [_REPOFILE_NAME], ['someothervendor'])

    scanvendorrepofiles.process()

    assert api.produce.called == 0


def test_non_repofile_is_ignored(monkeypatch):
    """Files in vendors.d that are not .repo files are not parsed."""
    _setup(monkeypatch, ['{}_map.json'.format(_VENDOR)], [_VENDOR])

    scanvendorrepofiles.process()

    assert api.produce.called == 0
