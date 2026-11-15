from leapp.actors import Actor
from leapp.libraries.actor import checkcgroupstunedprofile
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import KernelCmdline
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag


class CheckCgroupsTunedProfile(Actor):
    """
    Explain how to actually clear cgroups-v1 on CloudLinux.

    The upstream cgroups-v1 inhibitor tells the admin to remove the kernel
    arguments with grubby. On CloudLinux those arguments come from a TuneD
    profile and enter the command line through $tuned_params, so grubby has
    nothing to remove and the advice silently does nothing. This adds the
    remediation that works, without inhibiting a second time for one condition.
    """

    name = 'check_cgroups_tuned_profile'
    consumes = (KernelCmdline,)
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        checkcgroupstunedprofile.process()
