import pytest

from leapp import reporting
from leapp.libraries.actor import checkclstacksurvives as lib
from leapp.libraries.common.testutils import create_report_mocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError
from leapp.models import InstalledRPM, RPM


def _rpm(name, version, release, epoch='0'):
    return RPM(name=name, version=version, release=release, epoch=epoch,
               packager='CloudLinux', arch='x86_64', pgpsig='RSA/SHA256')


def test_older_target_build_is_reported():
    """The CLOS-7051 case: alt-python-internal's el10 build is behind el9's.

    Installed 3.11.13-2.el9, best available 3.11.12-2.el10. dnf will not move a
    package backwards, so with allow_erasing it erases it instead - and every
    CloudLinux package resting on it goes with it. Exactly what a real
    CloudLinux 9 to 10 run did, removing lve-utils, cagefs and lvemanager.
    """
    installed = [_rpm('alt-python-internal', '3.11.13', '2.el9')]

    def query(name):
        assert name == 'alt-python-internal'
        return [('0', '3.11.12', '2.el10')]

    assert lib.find_unupgradable(installed, query, target_major='10') == [
        ('alt-python-internal', '0:3.11.13-2.el9', '0:3.11.12-2.el10')
    ]


def test_same_version_across_dist_tags_is_fine():
    """el10 at the same upstream version is the normal case and must not fire.

    rpm sorts 1.el10.cloudlinux above 1.el9.cloudlinux, so this is a genuine
    upgrade even though only the dist tag moved.
    """
    installed = [_rpm('lve-utils', '6.6.39', '1.el9.cloudlinux')]
    query = lambda name: [('0', '6.6.39', '1.el10.cloudlinux')]

    assert lib.find_unupgradable(installed, query, target_major='10') == []


def test_newer_target_build_is_fine():
    installed = [_rpm('cagefs', '7.6.45', '1.el9.cloudlinux')]
    query = lambda name: [('0', '7.6.47', '1.el10.cloudlinux')]

    assert lib.find_unupgradable(installed, query, target_major='10') == []


def test_highest_available_wins_not_the_first_returned():
    """repoquery lists every build; the comparison is against the best one."""
    installed = [_rpm('cagefs', '7.6.45', '1.el9.cloudlinux')]
    query = lambda name: [
        ('0', '7.6.27', '2.el10.cloudlinux'),
        ('0', '7.6.47', '1.el10.cloudlinux'),
        ('0', '7.6.30', '1.el10.cloudlinux'),
    ]

    assert lib.find_unupgradable(installed, query, target_major='10') == []


def test_no_target_build_at_all_is_reported():
    installed = [_rpm('lvemanager', '7.11.48', '1.el9.cloudlinux')]

    assert lib.find_unupgradable(installed, lambda name: [], target_major='10') == [
        ('lvemanager', '0:7.11.48-1.el9.cloudlinux', None)
    ]


def test_packages_not_installed_are_not_queried():
    """Only what the host actually runs is checked - a no-panel box has less."""
    queried = []

    def query(name):
        queried.append(name)
        return [('0', '9', '1.el10')]

    lib.find_unupgradable([_rpm('cagefs', '7.6.47', '1.el9.cloudlinux')], query, target_major='10')

    assert queried == ['cagefs']


def test_non_essential_packages_are_ignored():
    """The check is about the CloudLinux stack, not every package on the box.

    Leftover el9 packages are normal and already reported elsewhere; inhibiting
    on all of them would refuse every upgrade.
    """
    installed = [_rpm('alt-nodejs10-nodejs', '10.24.1', '6.el9')]

    assert lib.find_unupgradable(installed, lambda name: [], target_major='10') == []


def test_epoch_is_honoured():
    """An epoch bump outranks any version, so it must not read as a downgrade."""
    installed = [_rpm('lve-stats', '5.0.4', '1.el9', epoch='0')]
    query = lambda name: [('1', '4.2.13', '2.el10')]

    assert lib.find_unupgradable(installed, query, target_major='10') == []


def test_process_inhibits_and_names_every_offender(monkeypatch):
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(lib, 'get_target_major_version', lambda: '10')
    monkeypatch.setattr(
        api, 'consume',
        lambda *a, **k: iter([InstalledRPM(items=[
            _rpm('alt-python-internal', '3.11.13', '2.el9'),
            _rpm('cagefs', '7.6.47', '1.el9.cloudlinux'),
        ])])
    )
    monkeypatch.setattr(
        lib, '_repoquery',
        lambda installroot, name: [] if name == 'cagefs' else [('0', '3.11.12', '2.el10')]
    )

    lib.process('/installroot')

    assert reporting.create_report.called == 1
    report = reporting.create_report.report_fields
    assert reporting.Groups.INHIBITOR in report['groups']
    assert 'alt-python-internal' in report['summary']
    assert 'cagefs' in report['summary']


def test_process_is_silent_when_the_stack_can_follow(monkeypatch):
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(lib, 'get_target_major_version', lambda: '10')
    monkeypatch.setattr(
        api, 'consume',
        lambda *a, **k: iter([InstalledRPM(items=[_rpm('cagefs', '7.6.47', '1.el9.cloudlinux')])])
    )
    monkeypatch.setattr(lib, '_repoquery', lambda installroot, name: [('0', '7.6.47', '1.el10.cloudlinux')])

    lib.process('/installroot')

    assert not reporting.create_report.called


def test_source_major_builds_in_the_union_are_ignored():
    """The target userspace repoquery returns source AND target repos.

    Left unfiltered, the installed el9 build comes back as "available" and the
    check can never fire - it would compare a package against itself. Only
    builds carrying the target major's dist tag count as a target build.
    """
    installed = [_rpm('alt-python-internal', '3.11.13', '2.el9')]
    query = lambda name: [
        ('0', '3.11.13', '2.el9'),    # the installed one, from the source repo
        ('0', '3.11.12', '2.el10'),   # the only real target build
    ]

    assert lib.find_unupgradable(installed, query, target_major='10') == [
        ('alt-python-internal', '0:3.11.13-2.el9', '0:3.11.12-2.el10')
    ]


def test_only_source_builds_available_reads_as_no_target_build():
    """A package present solely in the source repos has no target build."""
    installed = [_rpm('lvemanager', '7.11.48', '1.el9.cloudlinux')]
    query = lambda name: [('0', '7.11.48', '1.el9.cloudlinux')]

    assert lib.find_unupgradable(installed, query, target_major='10') == [
        ('lvemanager', '0:7.11.48-1.el9.cloudlinux', None)
    ]


def test_cloudlinux_dist_suffix_still_counts_as_a_target_build():
    """CloudLinux releases carry .el10.cloudlinux, not a bare .el10."""
    installed = [_rpm('cagefs', '7.6.45', '1.el9.cloudlinux')]
    query = lambda name: [('0', '7.6.47', '1.el10.cloudlinux')]

    assert lib.find_unupgradable(installed, query, target_major='10') == []


def test_a_failed_query_is_not_evidence_of_a_missing_build():
    """A repoquery that errors says nothing about the package.

    On the validation box an unrelated stale repo (cl-mysql, whose baseurl
    interpolates $releasever and 404s on the target) made every repoquery exit
    1. Treating that as "no build in the target repositories" named all
    fourteen essential packages, when only one was genuinely behind - it would
    have sent someone to rebuild thirteen packages that were fine.
    """
    installed = [_rpm('cagefs', '7.6.47', '1.el9.cloudlinux')]

    assert lib.find_unupgradable(installed, lambda name: None, target_major='10') == []


def test_a_failed_query_is_reported_as_indeterminate():
    """The caller has to be able to say so rather than silently pass."""
    installed = [
        _rpm('cagefs', '7.6.47', '1.el9.cloudlinux'),
        _rpm('lve-utils', '6.6.39', '1.el9.cloudlinux'),
    ]

    offenders, indeterminate = lib.evaluate(
        installed, lambda name: None, target_major='10'
    )

    assert offenders == []
    assert sorted(indeterminate) == ['cagefs', 'lve-utils']


def test_an_empty_answer_still_means_no_target_build():
    """A successful query returning nothing is a real absence, unlike a failure."""
    installed = [_rpm('lvemanager', '7.11.48', '1.el9.cloudlinux')]

    offenders, indeterminate = lib.evaluate(installed, lambda name: [], target_major='10')

    assert offenders == [('lvemanager', '0:7.11.48-1.el9.cloudlinux', None)]
    assert indeterminate == []


def test_repoquery_tolerates_an_unavailable_repo(monkeypatch):
    """One broken repo must not take the whole query down with it."""
    seen = {}

    def fake_run(cmd, **dummy):
        seen['cmd'] = cmd
        return {'stdout': '0|7.6.47|1.el10.cloudlinux\n'}

    monkeypatch.setattr(lib, 'run', fake_run)
    monkeypatch.setattr(api, 'current_logger', logger_mocked())

    assert lib._repoquery('/installroot', 'cagefs') == [('0', '7.6.47', '1.el10.cloudlinux')]
    assert any('skip_if_unavailable=1' in arg for arg in seen['cmd'])


def test_repoquery_returns_none_when_the_command_fails(monkeypatch):
    def boom(cmd, **dummy):
        raise CalledProcessError('failed', cmd, {'exit_code': 1, 'stdout': '', 'stderr': ''})

    monkeypatch.setattr(lib, 'run', boom)
    monkeypatch.setattr(api, 'current_logger', logger_mocked())

    assert lib._repoquery('/installroot', 'cagefs') is None
