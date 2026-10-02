from leapp.actors import Actor
from leapp.libraries.actor import checkclmysqltarget
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.models import FilteredRpmTransactionTasks, InstalledMySqlTypes, InstalledRPM
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag


class CheckClMysqlTarget(Actor):
    """
    Inhibit when the installed database cannot be carried to the target.

    Governor-managed series: CloudLinux 8 and 9 publish nineteen cl-mysql series,
    CloudLinux 10 six. On a host running one of the thirteen that were dropped,
    the upgrade would reach the target transaction with a cl-mysql repository
    that 404s, leaving the database packages unreplaced under a moved OS.

    The operating system's own server: when the target has no successor, the
    package data removes it and nothing installs a replacement - the default
    MySQL 8.0 on CloudLinux 9 to 10 - leaving the system without a database
    server. Leapp never switches it to a Governor build to get around that.
    """

    name = 'check_cl_mysql_target'
    consumes = (FilteredRpmTransactionTasks, InstalledMySqlTypes, InstalledRPM)
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        checkclmysqltarget.process()
