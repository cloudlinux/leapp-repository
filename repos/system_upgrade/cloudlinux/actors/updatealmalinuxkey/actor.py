from leapp.actors import Actor
from leapp.libraries.actor import updatealmalinuxkey
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.reporting import Report
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag


class UpdateAlmaLinuxKey(Actor):
    """
    Import the target distribution's GPG keys so the upgrade packages verify.

    This used to fetch https://repo.almalinux.org/almalinux/RPM-GPG-KEY-AlmaLinux
    over the network. That URL is unversioned and serves the AlmaLinux 8 keys -
    it was added for the 2023 AlmaLinux 8 key rotation and never made
    version-aware - so on any other target it imports the wrong key.

    leapp already ships the right keys per target major, so they are imported
    from disk: no network dependency, and the keys are the ones this package was
    built against.
    """

    name = "update_almalinux_key"
    consumes = ()
    produces = (Report,)
    tags = (IPUWorkflowTag, DownloadPhaseTag.Before)

    @run_on_cloudlinux
    def process(self):
        updatealmalinuxkey.process()
