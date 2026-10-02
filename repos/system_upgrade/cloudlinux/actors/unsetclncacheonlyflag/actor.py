from leapp.actors import Actor
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_package_channel_active
from leapp.libraries.stdlib import api
from leapp.libraries.common.cln_switch import get_cln_cacheonly_flag_path

import os

class UnsetClnCacheOnlyFlag(Actor):
    """
    Remove the flag for the dnf-spacewalk-plugin to not attempt to contact the CLN server during transaction.
    """

    name = 'unset_cln_cache_only_flag'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, FirstBootPhaseTag)

    @run_on_cloudlinux
    def process(self):
        if not is_cln_package_channel_active():
            # Mirrors set_cln_cache_only_flag: when the flag was never set,
            # there is nothing to remove.
            api.current_logger().info(
                "CLN is not the active package channel; no cache-only flag to remove"
            )
            return

        try:
            os.remove(get_cln_cacheonly_flag_path())
        except OSError:
            self.log.info('CLN cache file marker does not exist, doing nothing.')
