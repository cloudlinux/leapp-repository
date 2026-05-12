from leapp.actors import Actor
from leapp import reporting
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag
from leapp.libraries.stdlib import CalledProcessError, run, api
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_package_channel_active

from leapp.models import (
    TargetUserSpacePreupgradeTasks,
    TargetUserSpaceUpgradeTasks,
    CopyFile
)

import os


class CheckClLicense(Actor):
    """
    Check if the server has a CL license
    """

    name = 'check_cl_license'
    consumes = ()
    produces = (Report,)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    system_id_path = '/etc/sysconfig/rhn/systemid'
    rhn_check_bin = '/usr/sbin/rhn_check'

    @run_on_cloudlinux
    def process(self):
        # CLOS-4056: the rhn_check XML-RPC call only verifies licenses on
        # systems that use CLN as the package channel. Under no-auth (SWNG)
        # the license is conveyed by other means (IP-based licensing,
        # cloudlinux-release content) and the rhn_check round-trip is not a
        # meaningful gate - on rhn-client-tools 3.0+ it fails outright with
        # "Invalid System Credentials" against systemid files written by
        # clnreg_ks. Skip the check under no-auth.
        if not is_cln_package_channel_active():
            api.current_logger().info(
                "CLN is not the active package channel; skipping rhn_check"
                " license verification (no-auth systems use IP licensing,"
                " not the CLN XML-RPC roundtrip)."
            )
            return

        res = None
        if os.path.exists(self.system_id_path):
            try:
                res = run([self.rhn_check_bin])
                self.log.debug('rhn_check result: %s', res)
            except CalledProcessError as e:
                # The original implementation assigned `res = run(...)`
                # bare, but `run()` raises on non-zero exit codes - so
                # the "produce an inhibitor on non-zero / non-empty stderr"
                # branch below was dead code. Catch the failure and let
                # the existing reporting path take over.
                self.log.debug('rhn_check failed: %s', e)
                res = None
        if not res or res['exit_code'] != 0 or res['stderr']:
            title = 'Server does not have an active CloudLinux license'
            summary = 'Server does not have an active CloudLinux license. This renders key CloudLinux packages ' \
                      'inaccessible, inhibiting the upgrade process.'
            remediation = 'Activate a CloudLinux license on this machine before running Leapp again.'
            reporting.create_report([
                reporting.Title(title),
                reporting.Summary(summary),
                reporting.Severity(reporting.Severity.HIGH),
                reporting.Groups([reporting.Groups.OS_FACTS]),
                reporting.Groups([reporting.Groups.INHIBITOR]),
                reporting.Remediation(hint=remediation),
            ])
