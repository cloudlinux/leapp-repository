from leapp.actors import Actor
from leapp.tags import PreparationPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_package_channel_active
from leapp.libraries.stdlib import api
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
        if not is_cln_package_channel_active():
            # The flag exists only to stop dnf-spacewalk-plugin contacting CLN.
            # Where that plugin is not delivering packages - the no-auth scheme,
            # or CloudLinux 10, which ships no such plugin at all - there is
            # nothing to signal to.
            api.current_logger().info(
                "CLN is not the active package channel; not setting the cache-only flag"
            )
            return

        # TODO: Use a more reliable method to detect if we're running from the isolated userspace
        # Currently we're directly placing the file into the userspace directory '/var/lib/leapp/el{}userspace'
        # There should be better options
        with open(get_cln_cacheonly_flag_path(), 'w') as file:
            file.write('1')
