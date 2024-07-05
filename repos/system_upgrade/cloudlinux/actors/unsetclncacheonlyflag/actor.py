from leapp.actors import Actor
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
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
        try:
            os.remove(get_cln_cacheonly_flag_path())
        except FileNotFoundError:
            self.log.info('CLN cache file marker does not exist, doing nothing.')
