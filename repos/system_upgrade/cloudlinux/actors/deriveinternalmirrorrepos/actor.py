from leapp.actors import Actor
from leapp.libraries.actor import deriveinternalmirrorrepos
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import CustomTargetRepository, CustomTargetRepositoryFile, RepositoriesFacts
from leapp.tags import FactsPhaseTag, IPUWorkflowTag


class DeriveInternalMirrorRepos(Actor):
    """
    Derive target repositories from a system's own internal-mirror repo files.

    Some deployments do not install from the public CloudLinux
    and AlmaLinux mirrors but from an internal mirror of their own, reachable
    only from inside their network. Their repo files are version-templated -
    the baseurl carries $releasever - so the target-version URL can be derived
    from the source one instead of being hardcoded in leapp-data.

    Deriving rather than hardcoding also keeps the upgrade working across
    mirrors that differ per region, since each host's own repo files already
    name the mirror it can actually reach.

    Only the repositories needed to install the new OS are derived, and only
    when their baseurl is version-templated; systems using the standard public
    repositories are left untouched.
    """

    name = 'derive_internal_mirror_repos'
    consumes = (RepositoriesFacts,)
    produces = (CustomTargetRepository, CustomTargetRepositoryFile)
    tags = (FactsPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        deriveinternalmirrorrepos.process()
