from leapp.actors import Actor
from leapp.libraries.actor import updatecagefs
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.reporting import Report
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag


class UpdateCagefs(Actor):
    """
    Reinstall the CageFS hooks and force an update of cagefs.

    cagefs should reflect massive changes in system made in previous phases.

    The hooks need reinstalling because CageFS installs them from its own
    %posttrans scriptlet and cagefsctl cannot run inside the upgrade
    transaction, which on Plesk leaves CageFS users unable to enter the cage
    through 'su'. See the actor library for the detail.
    """

    name = 'update_cagefs'
    consumes = ()
    produces = (Report,)
    tags = (FirstBootPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        updatecagefs.process()
