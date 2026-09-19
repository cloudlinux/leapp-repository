from leapp.actors import Actor
from leapp.libraries.actor import checkclmysqltarget
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import InstalledMySqlTypes
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag


class CheckClMysqlTarget(Actor):
    """
    Inhibit when the Governor-managed database series has no target build.

    CloudLinux 8 and 9 publish nineteen cl-mysql series; CloudLinux 10 publishes
    six. On a host running one of the thirteen that were dropped, the upgrade
    would otherwise reach the target transaction with a cl-mysql repository that
    404s, leaving the database packages unreplaced under a moved OS.
    """

    name = 'check_cl_mysql_target'
    consumes = (InstalledMySqlTypes,)
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        checkclmysqltarget.process()
