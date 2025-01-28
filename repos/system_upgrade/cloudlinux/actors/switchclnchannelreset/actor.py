from leapp.actors import Actor
from leapp.libraries.stdlib import api
from leapp.tags import IPUWorkflowTag, TargetTransactionChecksPhaseTag
from leapp.libraries.stdlib import CalledProcessError
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_switch import cln_switch
from leapp.libraries.common.config.version import get_source_major_version
from leapp import reporting
from leapp.reporting import Report


class SwitchClnChannelReset(Actor):
    """
    Reset the CLN channel to CL7 to keep the system state consistent before the main upgrade phase.
    """

    name = "switch_cln_channel_reset"
    consumes = ()
    produces = (Report,)
    tags = (IPUWorkflowTag, TargetTransactionChecksPhaseTag.After)

    @run_on_cloudlinux
    def process(self):
        try:
            cln_switch(target=get_source_major_version())
        except CalledProcessError as e:
            reporting.create_report(
                [
                    reporting.Title(
                        "Failed to switch CloudLinux Network channel."
                    ),
                    reporting.Summary(
                        "Command {} failed with exit code {}."
                        " The most probable cause of that is a problem with this system's"
                        " CloudLinux Network registration.".format(e.command, e.exit_code)
                    ),
                    reporting.Remediation(
                        hint="Check the state of this system's registration with \'rhn_check\'."
                        " Attempt to re-register the system with \'rhnreg_ks --force\'."
                    ),
                    reporting.Severity(reporting.Severity.HIGH),
                    reporting.Groups(
                        [reporting.Groups.OS_FACTS, reporting.Groups.AUTHENTICATION]
                    ),
                    reporting.Groups([reporting.Groups.INHIBITOR]),
                ]
            )
        except OSError as e:
            api.current_logger().error(
                "Could not call RHN command: Message: %s", str(e), exc_info=True
            )
