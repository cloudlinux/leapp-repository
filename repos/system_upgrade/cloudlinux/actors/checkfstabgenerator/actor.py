from leapp.actors import Actor
from leapp.libraries.actor import checkfstabgenerator
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import LiveModeConfig
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag


class CheckFstabGenerator(Actor):
    """
    Inhibit when systemd-fstab-generator cannot process /etc/fstab.

    mount_unit_generator runs systemd-fstab-generator during 'leapp upgrade' and
    aborts the upgrade on any failure, after preupgrade has passed. A duplicated
    fstab line is enough: systemd tolerates it at boot, the generator exits
    non-zero. This runs the same command during preupgrade, so the system is
    fixed before anything changes.
    """

    name = 'check_fstab_generator'
    consumes = (LiveModeConfig,)
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        checkfstabgenerator.process()
