from leapp.actors import Actor
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag
from leapp import reporting
from leapp.reporting import Report
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.actor import enableyumspacewalkplugin


class EnableYumSpacewalkPlugin(Actor):
    name = "enable_yum_spacewalk_plugin"
    consumes = ()
    produces = (Report,)
    tags = (FirstBootPhaseTag, IPUWorkflowTag)
    config = enableyumspacewalkplugin.DEFAULT_CONFIG_PATH

    @run_on_cloudlinux
    def process(self):
        _, title = enableyumspacewalkplugin._enable_plugin(
            self.config, enableyumspacewalkplugin.ParserClass, self.log
        )
        if title:
            reporting.create_report([
                reporting.Title(title),
                reporting.Summary("DNF spacewalk plugin must be enabled for CLN channels. Config path: " + self.config),
                reporting.Severity(reporting.Severity.MEDIUM),
                reporting.Groups([reporting.Groups.SANITY])
            ])
