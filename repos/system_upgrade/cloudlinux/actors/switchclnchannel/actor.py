from leapp.actors import Actor
from leapp.libraries.stdlib import api
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag
from leapp.libraries.stdlib import CalledProcessError
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_configured
from leapp.libraries.common.cln_switch import cln_switch
from leapp import reporting
from leapp.reporting import Report
from leapp.libraries.common.config.version import get_target_major_version


class SwitchClnChannel(Actor):
    """
    Permanently switch CLN channel to target os version
    when upgrade is complete.
    """

    name = "switch_cln_channel"
    consumes = ()
    produces = (Report,)
    tags = (FirstBootPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        if not is_cln_configured():
            # CLOS-4056: No-auth (SWNG) systems have no CLN plumbing. Skipping
            # the channel switch here is correct — the system receives CL9
            # packages via cl-channel / cloudlinux9-baseos instead.
            api.current_logger().info(
                "CLN is not configured on this system; skipping channel switch"
            )
            return

        try:
            cln_switch(target=int(get_target_major_version()))
        except CalledProcessError as e:
            # CLOS-4056: Do not inhibit. CLN may be partially configured (legacy
            # registration files present but no working registration) on systems
            # transitioning to the no-auth scheme, and a failed channel switch
            # there is expected — the no-auth repos still serve CL9 packages.
            reporting.create_report(
                [
                    reporting.Title(
                        "Failed to switch CloudLinux Network channel"
                    ),
                    reporting.Summary(
                        "Command {} failed with exit code {}."
                        " The most probable cause of that is a problem with this system's"
                        " CloudLinux Network registration. If this system now uses the"
                        " no-auth (SWNG) repository scheme, this failure is harmless —"
                        " CL9 packages come from cl-channel / cloudlinux9-baseos instead"
                        " of CLN.".format(e.command, e.exit_code)
                    ),
                    reporting.Remediation(
                        hint="If you rely on CLN: check registration with 'rhn_check' and"
                        " re-register with 'rhnreg_ks --force'. If you have migrated to"
                        " no-auth repos, this message can be ignored."
                    ),
                    reporting.Severity(reporting.Severity.MEDIUM),
                    reporting.Groups(
                        [reporting.Groups.OS_FACTS, reporting.Groups.AUTHENTICATION]
                    ),
                ]
            )
        except OSError as e:
            api.current_logger().error(
                "Could not call RHN command: Message: %s", str(e), exc_info=True
            )
