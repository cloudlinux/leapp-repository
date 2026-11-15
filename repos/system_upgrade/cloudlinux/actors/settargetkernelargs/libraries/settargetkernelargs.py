from leapp import reporting
from leapp.exceptions import StopActorExecutionError
from leapp.libraries.common.cgroups import requests_legacy_hierarchy
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.common.rpms import has_package
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, KernelCmdline, KernelCmdlineArg, TargetKernelCmdlineArgTasks

# Both are what tuned-profiles-cloudlinux sets on el10: ibt=off comes from
# cloudlinux-default-base (the kmodlve fix), the FORCE flag from
# cloudlinux-default-cgv1. TuneD writes them into the bootloader only on the
# booted target, which is one boot too late.
IBT_OFF = ('ibt', 'off')
LEGACY_FORCE = ('SYSTEMD_CGROUP_ENABLE_LEGACY_FORCE', '1')

_WHY = {
    IBT_OFF: (
        'kmod-lve cannot operate while Indirect Branch Tracking is enabled, so on a'
        ' CPU that supports it the system would otherwise come up without LVE.'
    ),
    LEGACY_FORCE: (
        'this system runs cgroups-v1, and without this argument the systemd in'
        ' CloudLinux 10 ignores that request, waits 30 seconds, and boots on'
        ' cgroups-v2 instead.'
    ),
}


def required_args(parameters, lve_installed):
    """The CloudLinux 10 arguments the source command line does not carry yet."""
    wanted = []
    if lve_installed:
        wanted.append(IBT_OFF)
    if requests_legacy_hierarchy(parameters):
        wanted.append(LEGACY_FORCE)
    present = {(p.key, p.value) for p in parameters}
    return [arg for arg in wanted if arg not in present]


def _report(args):
    lines = ['- {0}={1}: {2}'.format(key, value, _WHY[(key, value)]) for key, value in args]
    reporting.create_report([
        reporting.Title('Kernel arguments will be added for the CloudLinux 10 kernel'),
        reporting.Summary(
            'The following arguments will be added to the CloudLinux 10 kernel command'
            ' line, so that its first boot already has them:\n{0}\n\n'
            'The CloudLinux TuneD profiles set the same arguments, but TuneD applies'
            ' them only once the upgraded system is running - too late for its first'
            ' boot, which would otherwise last until the next reboot. The arguments'
            ' stay on the kernel command line afterwards; with a CloudLinux TuneD'
            ' profile active they duplicate what the profile sets.'.format('\n'.join(lines))
        ),
        reporting.Severity(reporting.Severity.INFO),
        reporting.Groups([reporting.Groups.KERNEL, reporting.Groups.BOOT]),
        reporting.RelatedResource('package', 'kmod-lve'),
        reporting.RelatedResource('package', 'systemd'),
    ])


def process():
    if int(get_target_major_version()) < 10:
        return

    cmdline = next(api.consume(KernelCmdline), None)
    if not cmdline:
        raise StopActorExecutionError('Did not receive any KernelCmdline messages.')

    args = required_args(cmdline.parameters, has_package(InstalledRPM, 'kmod-lve'))
    if not args:
        return

    api.produce(TargetKernelCmdlineArgTasks(
        to_add=[KernelCmdlineArg(key=key, value=value) for key, value in args]))
    _report(args)
