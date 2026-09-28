import pytest

from leapp import reporting
from leapp.libraries.actor import checkdistrophptarget
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked
from leapp.libraries.stdlib import api
from leapp.models import FilteredRpmTransactionTasks, InstalledRPM, RPM


def _rpm(name, version):
    return RPM(name=name, epoch='0', packager='CloudLinux Packaging Team', version=version,
               release='1.module_el9.8.0+1+abcdef.cloudlinux.1', arch='x86_64',
               pgpsig='RSA/SHA256, Key ID 8c55a6628608cb71')


def _run(monkeypatch, installed, to_remove=(), to_install=(), with_tasks=True, target='10.2'):
    msgs = [InstalledRPM(items=[_rpm(n, v) for n, v in installed])]
    if with_tasks:
        msgs.append(FilteredRpmTransactionTasks(to_remove=list(to_remove), to_install=list(to_install)))
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(
        src_ver='9.8', dst_ver=target, msgs=msgs, src_distro='cloudlinux', dst_distro='cloudlinux'))
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    checkdistrophptarget.process()
    return reporting.create_report.reports


# The php:8.1 and php:8.2 streams on 9 -> 10: upstream PES removes the whole
# stream and nothing is installed in its place.
PHP81 = [('php', '8.1.34'), ('php-cli', '8.1.34'), ('php-common', '8.1.34'), ('php-fpm', '8.1.34')]
PHP81_REMOVED = ['php', 'php-cli', 'php-common', 'php-fpm', 'php-mbstring', 'php-xml']


def test_base_php_removed_without_successor_inhibits(monkeypatch):
    reports = _run(monkeypatch, PHP81, to_remove=PHP81_REMOVED)
    assert len(reports) == 1
    report = reports[0]
    assert reporting.Groups.INHIBITOR in report['groups']
    assert '8.1.34' in report['summary']
    for name in ('php', 'php-cli', 'php-fpm'):
        assert name in report['summary']
    assert 'PHP' in report['title']


def test_the_summary_states_both_outcomes(monkeypatch):
    # Measured on CloudLinux 9.8 on php:8.1 with mod_suphp: the plan removes the
    # stream, and dnf then satisfies the el10 mod_suphp's "php" and "php-cli"
    # with AlmaLinux's php8.4, which provides both. Without such a dependent,
    # nothing takes PHP's place.
    summary = _run(monkeypatch, PHP81, to_remove=PHP81_REMOVED)[0]['summary']
    assert '/usr/bin/php' in summary and 'mod_suphp' in summary
    assert 'php8.4' in summary
    assert 'would be gone, and so would' not in summary


def test_other_targets_name_no_cloudlinux_10_replacement(monkeypatch):
    summary = _run(monkeypatch, PHP81, to_remove=PHP81_REMOVED, target='9.8')[0]['summary']
    assert 'php8.4' not in summary


def test_one_report_for_the_whole_runtime(monkeypatch):
    # php, php-cli and php-fpm are one PHP, not three problems.
    assert len(_run(monkeypatch, PHP81, to_remove=PHP81_REMOVED)) == 1


def test_only_the_runtime_packages_actually_removed_are_named(monkeypatch):
    reports = _run(monkeypatch, [('php-cli', '8.2.30'), ('php-common', '8.2.30')],
                   to_remove=['php-cli', 'php-common'])
    summary = reports[0]['summary']
    assert 'php-cli' in summary and 'php-fpm' not in summary
    assert '8.2.30' in summary


def test_the_83_stream_is_carried_and_passes(monkeypatch):
    # php:8.3 has no removal event: the plan keeps it and it upgrades by name.
    assert _run(monkeypatch, [('php', '8.3.33'), ('php-cli', '8.3.33')], to_remove=[]) == []


def test_a_successor_in_the_plan_means_it_is_carried(monkeypatch):
    assert _run(monkeypatch, PHP81, to_remove=['php-cli'], to_install=['php-cli']) == []


@pytest.mark.parametrize('name', ['alt-php81-cli', 'ea-php81-php-cli', 'php-libguestfs'])
def test_selector_panel_and_other_php_packages_are_not_this_check(monkeypatch, name):
    # alt-php is PHP Selector's and keeps its own path to the target.
    assert _run(monkeypatch, [(name, '8.1.34')], to_remove=[name]) == []


def test_no_transaction_tasks_no_report(monkeypatch):
    assert _run(monkeypatch, PHP81, with_tasks=False) == []


def test_on_9_to_10_the_route_is_the_83_stream_or_php_selector(monkeypatch):
    report = _run(monkeypatch, PHP81, to_remove=PHP81_REMOVED)[0]
    hint = str(report['detail']['remediations'])
    assert 'dnf module switch-to php:8.3' in hint
    assert 'PHP Selector' in hint


def test_other_targets_get_no_cloudlinux_10_route(monkeypatch):
    report = _run(monkeypatch, PHP81, to_remove=PHP81_REMOVED, target='9.8')[0]
    assert 'php:8.3' not in str(report['detail']['remediations'])
