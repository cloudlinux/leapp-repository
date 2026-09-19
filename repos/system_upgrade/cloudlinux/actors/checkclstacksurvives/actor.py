from leapp.actors import Actor
from leapp.libraries.actor import checkclstacksurvives
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, TargetUserSpaceInfo
from leapp.reporting import Report
from leapp.tags import IPUWorkflowTag, TargetTransactionChecksPhaseTag


class CheckClStackSurvives(Actor):
    """
    Inhibit when the CloudLinux userland cannot be carried to the target system.

    A CloudLinux 9 to 10 run removed lve-utils, cagefs, lvemanager and lve-stats
    from a stock no-panel box and booted anyway. leapp had asked to upgrade all
    of them; dnf erased them because one package they rest on had no target build
    at the installed version. This refuses that upgrade instead of completing it.

    See the checkclstacksurvives library docstring for the full chain.
    """

    name = 'check_cl_stack_survives'
    consumes = (InstalledRPM, TargetUserSpaceInfo)
    produces = (Report,)
    tags = (IPUWorkflowTag, TargetTransactionChecksPhaseTag)

    @run_on_cloudlinux
    def process(self):
        info = next(api.consume(TargetUserSpaceInfo), None)
        if info is None:
            self.log.info(
                'No TargetUserSpaceInfo available; skipping the CloudLinux stack check.'
            )
            return
        checkclstacksurvives.process(installroot=info.path)
