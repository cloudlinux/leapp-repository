import os
import json

from leapp.actors import Actor
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_switch import get_target_userspace_path
from leapp.libraries.stdlib import api
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag


class PinClnMirror(Actor):
    """
    Pin CLN mirror.

    In the Spacewalk plugin, used for CLN, new mirror (new repo URI) may be chooen individually for each `dnf` invocation.
    DNF caches packages separately per repo URI.
    That may lead to a situation when a package is downloaded from a mirror during the dnf_package_download actor,
    but dnf can't find it in the cache on the next invocation in dnf_dry_run.
    To fix that, we pin the mirror during the upgrade, making sure that all the actors refer to the same mirror -
    and, consequently, the same cache.
    Mirror is unpinned by the UninClnMirror actor.
    """

    name = 'pin_cln_mirror'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, DownloadPhaseTag.Before)

    CLN_REPO_ID = "cloudlinux-x86_64-server-8"
    DEFAULT_CLN_MIRROR = "https://xmlrpc.cln.cloudlinux.com/XMLRPC/"
    TARGET_USERSPACE = get_target_userspace_path()

    @run_on_cloudlinux
    def process(self):
        # load last mirror URL from dnf spacewalk plugin cache
        spacewalk_settings = {}

        # find the mirror used in the last transaction
        # (expecting to find the one used in dnf_package_download actor)
        try:
            with open(os.path.join(self.TARGET_USERSPACE, '/var/lib/dnf/_spacewalk.json')) as file:
                spacewalk_settings = json.load(file)
        except (OSError, IOError, json.JSONDecodeError):
            api.current_logger().error("No spacewalk settings found - can't identify the last used CLN mirror")

        mirror_url = spacewalk_settings.get(self.CLN_REPO_ID, {}).get("url", [self.DEFAULT_CLN_MIRROR])[0]
        api.current_logger().info("Pin CLN mirror: %s", mirror_url)

        # pin mirror
        with open(os.path.join(self.TARGET_USERSPACE, '/etc/mirrorlist'), 'w') as file:
            file.write(mirror_url + '\n')

        with open(os.path.join(self.TARGET_USERSPACE, '/etc/sysconfig/rhn/up2date'), 'a+') as file:
            file.write('\nmirrorURL=file:///etc/mirrorlist\n')
