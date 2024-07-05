import os

from leapp.actors import Actor
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag

class UnpinClnMirror(Actor):
    """
    Remove pinned CLN mirror
    """

    name = 'unpin_cln_mirror'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, FirstBootPhaseTag)

    CLN_REPO_ID = "cloudlinux-x86_64-server-8"
    DEFAULT_CLN_MIRROR = "https://xmlrpc.cln.cloudlinux.com/XMLRPC/"
    MIRRORLIST_PATH = '/var/lib/leapp/el8userspace/etc/mirrorlist'
    UP2DATE_PATH = '/var/lib/leapp/el8userspace/etc/sysconfig/rhn/up2date'

    @run_on_cloudlinux
    def process(self):
        try:
            os.remove(self.MIRRORLIST_PATH)
        except FileNotFoundError:
            self.log.info('mirrorlist does not exist, doing nothing.')

        with open(self.UP2DATE_PATH, 'r') as file:
            lines = [
                line for line in file.readlines() if 'mirrorURL=file:///etc/mirrorlist' not in line
            ]
        with open(self.UP2DATE_PATH, 'w') as file:
            file.writelines(lines)
