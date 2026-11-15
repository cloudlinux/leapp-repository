from leapp.actors import Actor
from leapp.libraries.actor import refreshepel
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import InstalledRPM
from leapp.reporting import Report
from leapp.tags import ApplicationsPhaseTag, IPUWorkflowTag


class RefreshEPEL(Actor):
    """
    Leave the EPEL repositories on the new system version after the upgrade.

    When the source system's EPEL repo files had been edited, rpm keeps them and
    writes the target versions beside them as .rpmnew; the kept files still name
    the old release's repositories and GPG key. Put the target files in place,
    keeping each repository enabled or disabled as it was.

    This runs in the upgrade environment, which has no network: an epel-release
    the transaction did not upgrade is reported with the command that fixes it.
    InstalledRPM describes the source system, which is what tells whether EPEL
    was in use; the installed state now is read from rpm.
    """

    name = 'refresh_epel'
    consumes = (InstalledRPM,)
    produces = (Report,)
    tags = (ApplicationsPhaseTag.After, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        refreshepel.process()
