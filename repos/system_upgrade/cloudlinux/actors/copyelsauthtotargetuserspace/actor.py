from leapp.actors import Actor
from leapp.libraries.actor import copyelsauthtotargetuserspace
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import RpmTransactionTasks, TargetUserSpacePreupgradeTasks
from leapp.tags import FactsPhaseTag, IPUWorkflowTag


class CopyElsAuthToTargetUserspace(Actor):
    """
    Make the ALT-ELS repositories usable on a CloudLinux 10 target.

    CloudLinux 9 serves alt-php, alt-python, alt-ruby and alt-nodejs from the
    main CloudLinux channel; CloudLinux 10 serves them from per-language ALT-ELS
    repositories that authenticate with the CLN JWT. This copies that token into
    the target userspace, which otherwise receives only dnf.conf, and installs
    the els-*-release packages so the booted system keeps its own repofiles.

    Without it the upgrade completes with every alt-php package still at its el9
    build and no repository to update from.
    """

    name = 'copy_els_auth_to_target_userspace'
    consumes = ()
    produces = (RpmTransactionTasks, TargetUserSpacePreupgradeTasks)
    tags = (FactsPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        copyelsauthtotargetuserspace.process()
