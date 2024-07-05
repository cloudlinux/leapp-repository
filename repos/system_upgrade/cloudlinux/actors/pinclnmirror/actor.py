import json
import os.path

from leapp.actors import Actor
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.stdlib import api
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag


class PinClnMirror(Actor):
    """
    Pin CLN mirror.

    In Spacewalk plugin new mirror (new repo URI) may be choosen on each `dnf` invocation.
    Dnf caches packages per repo URI. That all may lead to a situation when package is downloaded from a mirror
    but dnf can't find it in the cache on the next invocation. To fix that, we pin the mirror during the upgrade.
    Mirror is unpinned by UninClnMirror actor.
    """

    name = 'pin_cln_mirror'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, DownloadPhaseTag.Before)

    CLN_REPO_ID = "cloudlinux-x86_64-server-8"
    DEFAULT_CLN_MIRROR = "https://xmlrpc.cln.cloudlinux.com/XMLRPC/"
    NEW_ROOT = '/var/lib/leapp/el8userspace'

    @run_on_cloudlinux
    def process(self):
        # load last mirror URL from dnf spacewalk plugin cache
        spacewalk_settings = {}

        try:
            with open(os.path.join(self.NEW_ROOT, '/var/lib/dnf/_spacewalk.json')) as file:
                spacewalk_settings = json.load(file)
        except (OSError, IOError, json.JSONDecodeError):
            api.current_logger().error("No spacewalk settings found")

        mirror_url = spacewalk_settings.get(self.CLN_REPO_ID, {}).get("url", [self.DEFAULT_CLN_MIRROR])[0]
        api.current_logger().info("Pin CLN mirror: %s", mirror_url)

        # pin mirror
        with open(os.path.join(self.NEW_ROOT, '/etc/mirrorlist'), 'w') as file:
            file.write(mirror_url + '\n')

        with open(os.path.join(self.NEW_ROOT, '/etc/sysconfig/rhn/up2date'), 'a+') as file:
            file.write('\nmirrorURL=file:///etc/mirrorlist\n')
