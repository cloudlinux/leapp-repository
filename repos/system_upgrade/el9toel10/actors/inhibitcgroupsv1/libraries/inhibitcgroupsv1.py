from leapp import reporting
from leapp.exceptions import StopActorExecutionError
from leapp.libraries.common.cgroups import requests_legacy_hierarchy
from leapp.libraries.common.config import get_source_distro_id
from leapp.libraries.stdlib import api
from leapp.models import KernelCmdline

# CloudLinux does not force the move to cgroups-v2.
#
# Upstream states that cgroups-v1 support "is removed in RHEL 10". Measured on a
# CloudLinux 10.2 box booted with systemd.unified_cgroup_hierarchy=0, it is
# deprecated and off by default, not removed: the el10 kernel carries
# CONFIG_MEMCG_V1=y and CONFIG_CPUSETS_V1=y, /proc/cgroups lists controllers on
# real v1 hierarchies, kmod-lve registers ("lve driver register status 0" - it
# autodetects the hierarchy and retains a full v1 path), and LVE and CageFS
# enforce exactly as they do under v2.
#
# So the inhibitor is policy, not a kernel limit, and carrying working software
# across a major upgrade is what this product is for. LVE on cgroups-v2 is also
# the less proven of the two today, so forcing the switch costs stability and
# buys nothing. The deprecation is still real, so the report remains - it just
# does not block.
_DISTRO_KEEPING_CGROUPS_V1 = 'cloudlinux'


def process():
    kernel_cmdline = next(api.consume(KernelCmdline), None)
    if not kernel_cmdline:
        # really unlikely
        raise StopActorExecutionError("Did not receive any KernelCmdline messages.")

    unified_hierarchy = not requests_legacy_hierarchy(kernel_cmdline.parameters)
    legacy_controller_present = False
    for param in kernel_cmdline.parameters:
        if param.key == "systemd.legacy_systemd_cgroup_controller":
            # no matter the value, it should be removed
            # it has no effect when unified hierarchy is enabled
            legacy_controller_present = True

    if unified_hierarchy:
        api.current_logger().debug("cgroups-v2 already in use, nothing to do, skipping.")
        return

    remediation_cmd_args = ["systemd.unified_cgroup_hierarchy"]
    if legacy_controller_present:
        remediation_cmd_args.append('systemd.legacy_systemd_cgroup_controller')

    if get_source_distro_id() == _DISTRO_KEEPING_CGROUPS_V1:
        reporting.create_report(
            [
                reporting.Title("cgroups-v1 enabled on the system"),
                reporting.Summary(
                    "Leapp detected cgroups-v1 is enabled on the system. Upstream"
                    " deprecated cgroups-v1 in RHEL 9 and disables it by default in"
                    " RHEL 10, but the kernel still supports it and CloudLinux keeps"
                    " it working: LVE and CageFS operate under either hierarchy, and"
                    " the cgroups-v1 TuneD profiles are still shipped.\n\n"
                    "The upgrade therefore continues and this system stays on"
                    " cgroups-v1. Third-party software that requires cgroups-v2"
                    " specifically may still need attention.\n\n"
                    "To move to cgroups-v2 by choice, switch to the cgroups-v2"
                    " counterpart of the active TuneD profile - the kernel arguments"
                    " come from the profile through /etc/tuned/bootcmdline, so"
                    " removing them with grubby has no effect."
                ),
                reporting.Severity(reporting.Severity.LOW),
                reporting.Groups([reporting.Groups.KERNEL]),
                reporting.RelatedResource("package", "systemd"),
            ]
        )
        return

    summary = (
        "Leapp detected cgroups-v1 is enabled on the system."
        " The support of cgroups-v1 was deprecated in RHEL 9 and is removed in RHEL 10."
        " Software requiring cgroups-v1 might not work correctly or at all on RHEL 10."
    )
    reporting.create_report(
        [
            reporting.Title("cgroups-v1 enabled on the system"),
            reporting.Summary(summary),
            reporting.Severity(reporting.Severity.HIGH),
            reporting.Groups([reporting.Groups.INHIBITOR, reporting.Groups.KERNEL]),
            reporting.RelatedResource("package", "systemd"),
            reporting.Remediation(
                hint="Make sure no third party software requires cgroups-v1 and switch to cgroups-v2.",
                # remove the args from commandline, the defaults are the desired values
                commands=[
                    [
                        "grubby",
                        "--update-kernel=ALL",
                        '--remove-args="{}"'.format(" ".join(remediation_cmd_args)),
                    ],
                ],
            ),
        ]
    )
