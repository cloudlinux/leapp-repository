import os

from leapp.libraries.actor import copyelsauthtotargetuserspace as lib
from leapp.libraries.common.testutils import logger_mocked, produce_mocked
from leapp.libraries.stdlib import api
from leapp.models import (
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RpmTransactionTasks,
    TargetUserSpacePreupgradeTasks,
)


def _setup(monkeypatch, target='10', jwt_exists=True, vars_present=None):
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(api, 'produce', produce_mocked())
    monkeypatch.setattr(lib, 'get_target_major_version', lambda: target)
    present = set(vars_present if vars_present is not None else lib.ELS_DNF_VARS)
    monkeypatch.setattr(lib.os.path, 'isfile', lambda p: p == lib.ELS_REPO_FILE)
    monkeypatch.setattr(lib.os.path, 'exists', lambda p: (
        p == lib.JWT_TOKEN if p == lib.JWT_TOKEN
        else os.path.basename(p) in present
    ) and (jwt_exists or p != lib.JWT_TOKEN))
    return api.produce


def test_the_jwt_and_its_dnf_vars_are_copied(monkeypatch):
    """The transaction authenticates against ALT-ELS with the CLN JWT.

    leapp copies only /etc/dnf/dnf.conf into the target userspace, so without
    this the $phpelstoken and friends resolve to nothing there and every ELS
    repository 401s - leaving alt-php at its el9 build with no repo to update
    from.
    """
    produce = _setup(monkeypatch)

    lib.process()

    tasks = [m for m in produce.model_instances
             if isinstance(m, TargetUserSpacePreupgradeTasks)]
    assert len(tasks) == 1
    copied = {c.src for c in tasks[0].copy_files}
    assert lib.JWT_TOKEN in copied
    for var in lib.ELS_DNF_VARS:
        assert os.path.join(lib.DNF_VARS_DIR, var) in copied


def test_nothing_is_copied_without_a_jwt(monkeypatch):
    """An unregistered or IP-licensed box has no token at all.

    Copying a non-existent path makes the userspace build fail, and such a box
    must still upgrade - just without ELS content, which skip_if_unavailable on
    the repositories takes care of.
    """
    produce = _setup(monkeypatch, jwt_exists=False)

    lib.process()

    assert not [m for m in produce.model_instances
                if isinstance(m, TargetUserSpacePreupgradeTasks)]


def test_only_the_dnf_vars_that_exist_are_copied(monkeypatch):
    """The four symlinks are created by rhn-client-tools, not guaranteed.

    An older rhn-client-tools predates some of them, and copying a missing one
    would fail the userspace build for a box that is otherwise fine.
    """
    produce = _setup(monkeypatch, vars_present=['phpelstoken'])

    lib.process()

    tasks = [m for m in produce.model_instances
             if isinstance(m, TargetUserSpacePreupgradeTasks)]
    copied = {c.src for c in tasks[0].copy_files}
    assert os.path.join(lib.DNF_VARS_DIR, 'phpelstoken') in copied
    assert os.path.join(lib.DNF_VARS_DIR, 'altrubyelstoken') not in copied


def test_the_els_release_packages_are_installed_on_the_target(monkeypatch):
    """The booted system needs its own repofiles, and the el10 builds at that.

    The el9 els-php-release hardcodes el/9 in the baseurl; only the el10 build
    uses $releasever. Carrying the el9 one across leaves a CloudLinux 10 box
    pointed at el9 PHP content.
    """
    produce = _setup(monkeypatch)

    lib.process()

    tasks = [m for m in produce.model_instances if isinstance(m, RpmTransactionTasks)]
    assert len(tasks) == 1
    assert sorted(tasks[0].to_install) == sorted(lib.ELS_RELEASE_PACKAGES)


def test_nothing_happens_on_targets_before_10(monkeypatch):
    """CloudLinux 9 serves the Selector runtimes from the main channel."""
    produce = _setup(monkeypatch, target='9')

    lib.process()

    assert not produce.model_instances


def test_the_els_repofile_is_pulled_in_only_when_the_token_exists(monkeypatch):
    """The repositories must not reach the target configuration without the JWT.

    Measured three times on an unregistered CloudLinux 9 box. scancustomrepofile
    emits a CustomTargetRepository for every section of
    /etc/leapp/files/leapp_upgrade_repositories.repo, unconditionally - so naming
    them there makes them target repositories whatever enabled= says and whatever
    the repomap does, and the target userspace build then dies on

        Status code: 403 for https://$phpelstoken:@repo.alt.tuxcare.com/...

    They live in their own repofile instead, which only this actor pulls in.
    """
    produce = _setup(monkeypatch)

    lib.process()

    files = [m for m in produce.model_instances
             if isinstance(m, CustomTargetRepositoryFile)]
    assert [f.file for f in files] == [lib.ELS_REPO_FILE]
    repos = [m for m in produce.model_instances if isinstance(m, CustomTargetRepository)]
    assert sorted(r.repoid for r in repos) == sorted(lib.ELS_TARGET_REPOS)


def test_no_token_means_the_repofile_is_never_pulled_in(monkeypatch):
    """An unregistered box upgrades without ELS content rather than failing."""
    produce = _setup(monkeypatch, jwt_exists=False)

    lib.process()

    assert not [m for m in produce.model_instances
                if isinstance(m, (CustomTargetRepositoryFile, CustomTargetRepository))]


def test_a_missing_repofile_warns_rather_than_breaking(monkeypatch):
    """An older leapp-data has no such file; the upgrade should still run."""
    produce = _setup(monkeypatch)
    monkeypatch.setattr(lib.os.path, 'isfile', lambda p: False)

    lib.process()

    assert not [m for m in produce.model_instances
                if isinstance(m, CustomTargetRepositoryFile)]
    assert any('cannot be configured' in m for m in api.current_logger().warnmsg)
