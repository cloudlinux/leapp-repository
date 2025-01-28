import os
import json

from leapp.actors import Actor
from leapp.libraries.stdlib import api
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag
from leapp.libraries.stdlib import CalledProcessError
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_switch import cln_switch, get_target_userspace_path
from leapp import reporting
from leapp.reporting import Report
from leapp.libraries.common.config.version import get_target_major_version



CLN_REPO_ID = "cloudlinux-x86_64-server-8"
DEFAULT_CLN_MIRROR = "https://xmlrpc.cln.cloudlinux.com/XMLRPC/"


class SwitchClnChannelDownload(Actor):
    """
    Switch CLN channel from 7 to 8 to be able to download upgrade packages.
    """

    name = "switch_cln_channel_download"
    consumes = ()
    produces = (Report,)
    tags = (IPUWorkflowTag, DownloadPhaseTag.Before)

    @run_on_cloudlinux
    def process(self):
        try:
            cln_switch(target=int(get_target_major_version()))
        except CalledProcessError as e:
            reporting.create_report(
                [
                    reporting.Title(
                        "Failed to switch CloudLinux Network channel from 7 to 8."
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

        self._pin_cln_mirror()

    def _pin_cln_mirror(self):
        """Pin CLN mirror"""
        target_userspace = get_target_userspace_path()
        api.current_logger().info("Pin CLN mirror: target userspace=%s", target_userspace)

        # load last mirror URL from dnf spacewalk plugin cache
        spacewalk_settings = {}

        # find the mirror used in the last transaction
        # (expecting to find the one used in dnf_package_download actor)
        spacewalk_json_path = os.path.join(target_userspace, 'var/lib/dnf/_spacewalk.json')
        try:
            with open(spacewalk_json_path) as file:
                spacewalk_settings = json.load(file)
        except (OSError, IOError, ValueError):
            api.current_logger().error(
                "No spacewalk settings found in %s - can't identify the last used CLN mirror",
                spacewalk_json_path,
            )

        mirror_url = spacewalk_settings.get(CLN_REPO_ID, {}).get("url", [DEFAULT_CLN_MIRROR])[0]

        # pin mirror
        for mirrorlist_path in [
            '/etc/mirrorlist',
            os.path.join(target_userspace, 'etc/mirrorlist'),
        ]:
            with open(mirrorlist_path, 'w') as file:
                file.write(mirror_url + '\n')
            api.current_logger().info("Pin CLN mirror %s in %s", mirror_url, mirrorlist_path)

        for up2date_path in [
            '/etc/sysconfig/rhn/up2date',
            os.path.join(target_userspace, 'etc/sysconfig/rhn/up2date'),
        ]:
            # At some point up2date in `target_userspace` might be overwritten by a default one
            with open(up2date_path, 'a+') as file:
                file.write('\nmirrorURL[comment]=Set mirror URL to /etc/mirrorlist\nmirrorURL=file:///etc/mirrorlist\n')
            api.current_logger().info("Updated up2date_path %s", up2date_path)
