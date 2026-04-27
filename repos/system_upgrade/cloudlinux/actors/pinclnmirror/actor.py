import json
import os

from leapp.actors import Actor
from leapp.libraries.stdlib import api
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_package_channel_active
from leapp.libraries.common.cln_switch import get_target_userspace_path
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag
from leapp.libraries.common.config.version import get_target_major_version


class PinClnMirror(Actor):
    """
    Save CLN mirror that was used last time.
    """

    name = 'pin_cln_mirror'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, DownloadPhaseTag.Before)

    CLN_REPO_ID = "cloudlinux-x86_64-server-%s"
    DEFAULT_CLN_MIRROR = "https://xmlrpc.cln.cloudlinux.com/XMLRPC/"

    @run_on_cloudlinux
    def process(self):
        """Pin CLN mirror"""
        if not is_cln_package_channel_active():
            # CLOS-4056: pinning the CLN mirror is only meaningful when CLN
            # is delivering packages. On no-auth (SWNG) systems packages come
            # from cl-channel via mirrorlist, so there is nothing to pin —
            # registration may still be in place but is irrelevant here.
            api.current_logger().info(
                "CLN is not the active package channel; skipping mirror pinning"
            )
            return

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

        mirror_url = spacewalk_settings.get(
            self.CLN_REPO_ID % get_target_major_version(), {}
        ).get("url", [self.DEFAULT_CLN_MIRROR])[0]

        # pin mirror
        mirrorlist_path = os.path.join(target_userspace, 'etc/mirrorlist')
        with open(mirrorlist_path, 'w') as file:
            file.write(mirror_url + '\n')
        api.current_logger().info("Pin CLN mirror %s in %s", mirror_url, mirrorlist_path)

        up2date_path = os.path.join(target_userspace, 'etc/sysconfig/rhn/up2date')
        try:
            with open(up2date_path, 'a+') as file:
                file.write('\nmirrorURL[comment]=Set mirror URL to /etc/mirrorlist\nmirrorURL=file:///etc/mirrorlist\n')
            api.current_logger().info("Updated up2date_path %s", up2date_path)
        except (OSError, IOError) as e:
            api.current_logger().info(
                "Could not update %s: %s", up2date_path, e,
            )
