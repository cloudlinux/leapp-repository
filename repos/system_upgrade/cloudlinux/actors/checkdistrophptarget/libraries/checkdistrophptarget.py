"""Inhibit when the settled transaction removes the operating system's PHP.

Only the operating system's packages are decided here. PHP Selector's alt-php and
a control panel's PHP have their own names and their own path to the target.
"""

from leapp import reporting
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.common.transactionplan import removed_without_successor
from leapp.libraries.stdlib import api
from leapp.models import FilteredRpmTransactionTasks, InstalledRPM

# The packages that run PHP: the Apache integration, /usr/bin/php - which is also
# PHP Selector's "native" version - and FPM.
_RUNTIME = ('php', 'php-cli', 'php-fpm')

# What takes PHP's place when another package requires it, keyed by target major.
# Measured on CloudLinux 9.8 on php:8.1 with mod_suphp: the el10 mod_suphp
# requires "php" and "php-cli", and AlmaLinux 10's php8.4 packages provide both.
_REPLACEMENTS = {
    '10': ' On CloudLinux 10 that is AlmaLinux\'s PHP 8.4, the php8.4 packages.',
}

# A route verified end to end, keyed by target major. On CloudLinux 9 the
# php:8.3 stream has no removal event and upgrades by name to CloudLinux 10's
# PHP 8.3, and the upgrade carries alt-php81 and alt-php82 to el10 builds.
_ROUTES = {
    '10': (
        ' On CloudLinux 9 that is PHP 8.3, available as the php:8.3 module stream, which the'
        ' upgrade carries to CloudLinux 10: run "dnf module switch-to php:8.3" and check the'
        ' sites before upgrading. Sites that must stay on PHP 8.1 or 8.2 can use those'
        ' versions from PHP Selector (alt-php), which the upgrade carries to CloudLinux 10.'
    ),
}


def _family(name):
    return 'php' if name in _RUNTIME else None


def _installed_version(names):
    for installed in api.consume(InstalledRPM):
        for pkg in installed.items:
            if pkg.name in names:
                return pkg.version
    return 'unknown'


def process():
    tasks = next(api.consume(FilteredRpmTransactionTasks), None)
    if not tasks:
        return
    removed = removed_without_successor(tasks, _RUNTIME, _family)
    if not removed:
        return

    target = get_target_major_version()
    reporting.create_report([
        reporting.Title('The operating system PHP cannot be upgraded to CloudLinux {0}'.format(target)),
        reporting.Summary(
            'This system runs PHP {version} from the operating system repositories'
            ' (packages {names}). CloudLinux {target} provides no successor for this'
            ' version, so the upgrade would remove these packages. Where nothing else'
            ' requires PHP, nothing takes their place, and PHP Selector\'s "native"'
            ' version, /usr/bin/php, is gone. Where something does, such as mod_suphp,'
            ' the package manager instead installs whichever PHP the target provides for'
            ' it, silently changing the PHP version.{replacement}\n\n'
            'PHP versions provided by PHP Selector (alt-php) are separate packages and are'
            ' not affected.'.format(version=_installed_version(removed),
                                    names=', '.join(removed), target=target,
                                    replacement=_REPLACEMENTS.get(target, ''))
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([reporting.Groups.SERVICES, reporting.Groups.INHIBITOR]),
        reporting.Remediation(
            hint='Before upgrading, move the operating system PHP to a version that CloudLinux'
                 ' {0} provides.{1}'.format(target, _ROUTES.get(target, ''))
        ),
    ] + [reporting.RelatedResource('package', name) for name in removed])
