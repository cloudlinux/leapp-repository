import os

from leapp import reporting
from leapp.libraries.stdlib import api

ACTIVE_PROFILE_FILE = '/etc/tuned/active_profile'
TUNED_PROFILE_DIRS = ('/etc/tuned', '/usr/lib/tuned')

CGV1_SUFFIX = '-cgv1'
CGV2_SUFFIX = '-cgv2'


def get_active_tuned_profile():
    """Return the active TuneD profile name, or None when there is none."""
    try:
        with open(ACTIVE_PROFILE_FILE) as fp:
            return fp.read().strip() or None
    except (OSError, IOError):
        return None


def cgv2_counterpart(profile):
    """Return the -cgv2 sibling of a -cgv1 profile, or None.

    CloudLinux ships its TuneD profiles in pairs - cloudlinux-default-cgv1 and
    cloudlinux-default-cgv2, and the same for latency-performance - differing only
    in which cgroup hierarchy they select.
    """
    if not profile or not profile.endswith(CGV1_SUFFIX):
        return None
    return profile[:-len(CGV1_SUFFIX)] + CGV2_SUFFIX


def profile_exists(profile):
    return any(os.path.isdir(os.path.join(d, profile)) for d in TUNED_PROFILE_DIRS)


def kernel_uses_cgroups_v1(parameters):
    """Whether the kernel command line selects the legacy hierarchy.

    Same condition upstream's inhibit_cgroupsv1 applies; the unified hierarchy is
    the default from RHEL 9 on, so only an explicit opt-out counts.
    """
    for param in parameters:
        key, _, value = param.partition('=')
        if key == 'systemd.unified_cgroup_hierarchy' and value.lower() in ('0', 'false', 'no'):
            return True
    return False


def check(kernel_parameters):
    """Report the CloudLinux-specific remediation when one applies."""
    if not kernel_uses_cgroups_v1(kernel_parameters):
        return

    profile = get_active_tuned_profile()
    replacement = cgv2_counterpart(profile)
    if not replacement:
        # Not a CloudLinux paired profile - upstream's grubby remediation is the
        # right advice there, and repeating ourselves would only add noise.
        return

    reporting.create_report([
        reporting.Title(
            'The cgroups-v1 kernel arguments come from a TuneD profile, not the bootloader'
        ),
        reporting.Summary(
            'The active TuneD profile is {profile}, which sets'
            ' systemd.unified_cgroup_hierarchy=0 and'
            ' systemd.legacy_systemd_cgroup_controller through'
            ' /etc/tuned/bootcmdline. Those arguments reach the kernel command line'
            ' via the $tuned_params variable referenced by the boot loader entry,'
            ' so they are not stored in the entry itself.\n\n'
            'This matters because the remediation offered with the "cgroups-v1'
            ' enabled on the system" inhibitor - grubby --update-kernel=ALL'
            ' --remove-args=... - has nothing to remove and leaves the system'
            ' booting exactly as before. Switching the TuneD profile is what'
            ' changes it: CloudLinux ships {replacement} as the cgroups-v2'
            ' counterpart of {profile}.'.format(profile=profile, replacement=replacement)
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([reporting.Groups.KERNEL]),
        reporting.RelatedResource('file', ACTIVE_PROFILE_FILE),
        reporting.RelatedResource('file', '/etc/tuned/bootcmdline'),
        reporting.Remediation(
            hint=(
                'Switch to the cgroups-v2 profile, regenerate the boot loader'
                ' configuration and reboot before starting the upgrade.'
            ),
            commands=[
                ['tuned-adm', 'profile', replacement],
                ['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'],
            ],
        ),
    ])


def process():
    from leapp.models import KernelCmdline  # noqa; pylint: disable=import-outside-toplevel

    cmdline = next(api.consume(KernelCmdline), None)
    if not cmdline:
        return
    parameters = [
        p.key if p.value is None else '{}={}'.format(p.key, p.value)
        for p in cmdline.parameters
    ]
    check(parameters)
