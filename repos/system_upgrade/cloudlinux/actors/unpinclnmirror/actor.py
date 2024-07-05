import os

from leapp.actors import Actor
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_switch import get_target_userspace_path
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag

class UnpinClnMirror(Actor):
    """
    Remove the pinned CLN mirror.
    See the pin_cln_mirror actor for more details.
    """

    name = 'unpin_cln_mirror'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, FirstBootPhaseTag)

    CLN_REPO_ID = "cloudlinux-x86_64-server-8"
    DEFAULT_CLN_MIRROR = "https://xmlrpc.cln.cloudlinux.com/XMLRPC/"

    @run_on_cloudlinux
    def process(self):
        target_userspace = get_target_userspace_path()

        try:
            mirrorlist_path = os.path.join(target_userspace, 'etc/mirrorlist')
            os.remove(mirrorlist_path)
        except FileNotFoundError:
            self.log.info('mirrorlist does not exist, doing nothing.')

        uo2date_path = os.path.join(target_userspace, 'etc/sysconfig/rhn/up2date')
        with open(uo2date_path, 'r') as file:
            lines = [
                line for line in file.readlines() if 'mirrorURL=file:///etc/mirrorlist' not in line
            ]
        with open(uo2date_path, 'w') as file:
            file.writelines(lines)
