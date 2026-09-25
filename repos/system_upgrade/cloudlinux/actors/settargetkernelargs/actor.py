from leapp.actors import Actor
from leapp.libraries.actor import settargetkernelargs
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import InstalledRPM, KernelCmdline, TargetKernelCmdlineArgTasks
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag


class SetTargetKernelArgs(Actor):
    """
    Put the CloudLinux 10 kernel arguments on the target kernel before it first boots.

    On CloudLinux the kernel arguments come from a TuneD profile, and TuneD writes
    them into the bootloader only once the upgraded system is running. So without
    this the first CloudLinux 10 boot - and every boot until the next reboot - runs
    on the source system's arguments, which lack two that CloudLinux 10 needs:

    - ibt=off: kmod-lve cannot operate while Indirect Branch Tracking is enabled,
      so on a CPU that supports it the system would come up without LVE.
    - SYSTEMD_CGROUP_ENABLE_LEGACY_FORCE=1: without it the systemd in CloudLinux 10
      ignores a cgroups-v1 request, waits 30 seconds, and boots on cgroups-v2.
    """

    name = 'set_target_kernel_args'
    consumes = (InstalledRPM, KernelCmdline)
    produces = (Report, TargetKernelCmdlineArgTasks)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        settargetkernelargs.process()
