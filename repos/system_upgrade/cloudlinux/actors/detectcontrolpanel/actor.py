from leapp.actors import Actor
from leapp import reporting
from leapp.reporting import Report
from leapp.models import InstalledControlPanel
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag
from leapp.exceptions import StopActorExecutionError

from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.common.detectcontrolpanel import panel_blocks_upgrade


class DetectControlPanel(Actor):
    """
    Inhibit the upgrade if an unsupported control panel is found.
    """

    name = "detect_control_panel"
    consumes = (InstalledControlPanel,)
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        panel = next(self.consume(InstalledControlPanel), None)
        if panel is None:
            raise StopActorExecutionError(message=("Missing information about the installed web panel."))

        target_major = get_target_major_version()

        if not panel_blocks_upgrade(panel.name, target_major):
            self.log.debug(
                '%s is supported for the upgrade to major version %s, upgrade proceeding',
                panel.name, target_major
            )
            return

        reporting.create_report(
            [
                reporting.Title(
                    "The installed control panel does not support the target system."
                ),
                reporting.Summary(
                    "The upgrade cannot proceed on a system with {panel} installed,"
                    " because {panel} does not support CloudLinux {major}."
                    " Leapp carries no package or repository data for that combination,"
                    " which makes loss of functionality after the upgrade extremely likely."
                    .format(panel=panel.name, major=target_major)
                ),
                reporting.Severity(reporting.Severity.HIGH),
                reporting.Groups([reporting.Groups.OS_FACTS]),
                reporting.Groups([reporting.Groups.INHIBITOR]),
            ]
        )
