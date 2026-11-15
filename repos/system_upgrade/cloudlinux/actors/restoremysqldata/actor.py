from leapp.actors import Actor
from leapp.libraries.actor import restoremysqldata
from leapp.models import Report
from leapp.tags import ThirdPartyApplicationsPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux


class RestoreMySqlData(Actor):
    """
    Restore cl-mysql configuration data from an external folder.
    """

    name = 'restore_my_sql_data'
    consumes = ()
    produces = (Report,)
    tags = (ThirdPartyApplicationsPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        restoremysqldata.process()
