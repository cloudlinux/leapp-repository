from leapp.actors import Actor
from leapp.libraries.actor import ignoreclstackexcludes
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import InstalledRPM, TargetUserSpaceInfo
from leapp.reporting import Report
from leapp.tags import IPUWorkflowTag, TargetTransactionFactsPhaseTag


class IgnoreClStackExcludes(Actor):
    """
    Keep host DNF excludes from holding back CloudLinux packages during the upgrade.

    The upgrade copies the host's dnf.conf into the target userspace, and its
    exclude list then filters the target repositories too. DirectAdmin excludes
    liblsapi and the CRIU tooling it requires; their source-system builds need the
    source's Python, so the transaction check fails. Drop those patterns from the
    copy only, after the userspace is created and before anything there runs dnf.
    """

    name = 'ignore_cl_stack_excludes'
    consumes = (InstalledRPM, TargetUserSpaceInfo)
    produces = (Report,)
    tags = (TargetTransactionFactsPhaseTag.After, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        ignoreclstackexcludes.process()
