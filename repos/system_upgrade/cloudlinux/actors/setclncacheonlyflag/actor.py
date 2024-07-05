from leapp.actors import Actor
from leapp.tags import PreparationPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_switch import get_cln_cacheonly_flag_path

class SetClnCacheOnlyFlag(Actor):
    """
    Set a flag for the dnf-spacewalk-plugin to not attempt to contact the CLN server during transaction,
    as it will fail and remove CLN-based package repos from the list.

    When this flag exists, the plugin will act as if there's no network connection,
    only using the local cache.
    """

    name = 'set_cln_cache_only_flag'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, PreparationPhaseTag)

    @run_on_cloudlinux
    def process(self):
        # TODO: Use a more reliable method to detect if we're running from the isolated userspace
        # Currently we're directly placing the file into the userspace directory '/var/lib/leapp/el{}userspace'
        # There should be better options
        with open(get_cln_cacheonly_flag_path(), 'w') as file:
            file.write('1')
