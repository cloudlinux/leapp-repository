from leapp.actors import Actor
from leapp.libraries.actor import checkdistrophptarget
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import FilteredRpmTransactionTasks, InstalledRPM
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag


class CheckDistroPhpTarget(Actor):
    """
    Inhibit when the upgrade would remove the operating system's PHP with no successor.

    On CloudLinux 9 to 10 the package data removes the whole php:8.1 and php:8.2
    module streams, because CloudLinux 10's own PHP is 8.3. With nothing else
    requiring PHP, that takes PHP Selector's "native" version with it; with a
    dependent such as mod_suphp, dnf silently installs AlmaLinux's php8.4 instead.
    Either way the system does not keep the PHP it chose. PHP Selector's own
    versions (alt-php) are separate packages and are not decided here.
    """

    name = 'check_distro_php_target'
    consumes = (FilteredRpmTransactionTasks, InstalledRPM)
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        checkdistrophptarget.process()
